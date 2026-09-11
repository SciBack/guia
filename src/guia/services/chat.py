"""ChatService — núcleo del asistente GUIA.

M4: answer() es async end-to-end.
    - embed_query, store.search, llm.complete → asyncio.to_thread() (son sync)
    - search_adapter.hybrid_dicts() → await directo (async nativo)
    - cache.get / cache.set → asyncio.to_thread() (Redis sync, rápido)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sciback_core.ports.llm import LLMMessage, LLMPort, LLMResponse
from sciback_privacy import PrivacyRouter, PrivacyVerdict, redact, restore

from guia.audit import AuditLogEntry, AuditLogRepository, hash_query
from guia.domain.chat import ChatRequest, ChatResponse, Intent, Source
from guia.routing import CascadeRouter, IntentCategory, RouteDecision, Tier, category_to_intent
from guia.services._bucket import assign_bucket
from guia.services.lector_de_peticion import LectorDePeticion, hay_peticion
from guia.services.orientacion import orientar
from guia.services.horario_de_clases import HorarioDeClases, redactar_horario
from guia.services.identidad_institucional import DirectorioInstitucional
from guia.services.agenda_academica import (
    Agenda,
    AgendaAcademica,
    es_consulta_sobre_uno_mismo,
    redactar,
    redactar_identidad,
)
from guia.services.intent import IntentClassifier
from guia.services.router import ModelRouter, QueryTier

if TYPE_CHECKING:
    from sciback_adapter_koha import KohaAdapter
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter

    from guia.config import GUIASettings
    from guia.routing.gates import LanguageGate, ToxicityGate
    from guia.search.backend import SearchAdapter
    from guia.services.agent_orchestrator import AgentOrchestrator
    from guia.services.cache import SemanticCache
    from guia.services.query_rewriter import QueryRewriter

def koha_opac_url(doc_id: str, base_url: str) -> str | None:
    """Construye el link al OPAC de Koha desde un doc_id `koha:<biblionumber>`.

    El index no guarda URL para libros físicos de Koha, así que la derivamos
    determinísticamente del biblionumber. Es el sistema quien arma la URL —
    nunca el LLM — para evitar enlaces alucinados.

    Devuelve None si el doc_id no es de Koha o no hay base_url configurada.
    """
    if not base_url or not doc_id.startswith("koha:"):
        return None
    biblio_id = doc_id.split(":", 1)[1]
    if not biblio_id:
        return None
    return f"{base_url.rstrip('/')}/cgi-bin/koha/opac-detail.pl?biblionumber={biblio_id}"


def _encabezado_listado(sources: list[Source]) -> str:
    """Texto de reserva para las respuestas que se renderizan como listado.

    El canal lo sustituye por el listado con enlaces, así que casi nunca se ve.
    Existe para quien consuma la API en crudo: sin esto recibiría una respuesta
    con fuentes y el campo ``answer`` vacío, que parece un fallo.
    """
    total = len(sources)
    return (
        f"Encontré {total} resultado{'s' if total != 1 else ''} relacionado"
        f"{'s' if total != 1 else ''} con tu consulta."
    )


#: Formas de pedir una explicación. Cuando la consulta empieza por una de
#: estas, el usuario quiere prosa aunque el buscador devuelva veinte fuentes:
#: "explícame qué es la quinua" no se contesta con una lista de tesis sobre
#: derivados de quinua. Se comparan sin tildes y en minúsculas.
_PIDE_EXPLICACION = (
    "explica", "explicame", "que es", "que son", "que significa",
    "como funciona", "como se", "por que", "porque",
    "resume", "resumen", "resumeme", "diferencia", "diferencias",
    "compara", "comparacion", "en que consiste", "para que sirve",
    "cuentame sobre", "hablame de", "definicion",
)


def _pide_explicacion(query: str) -> bool:
    """¿La consulta está redactada como pregunta, no como búsqueda?"""
    import unicodedata

    texto = unicodedata.normalize("NFKD", query.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = " ".join(texto.split())
    return any(texto.startswith(p) or f" {p}" in texto for p in _PIDE_EXPLICACION)


#: Palabras con las que se pide algo, pero que no dicen SOBRE QUÉ. Si al
#: quitarlas no queda nada, la consulta no tiene tema que buscar.
_ANDAMIAJE_DE_PETICION = frozenset("""
busco buscando buscar quiero quisiera necesito necesitaba deseo dame damos
ayuda ayudame ayudarme apoyo recomienda recomiendame recomendacion sugiere
sugerencia informacion info datos material materiales recurso recursos
bibliografia fuente fuentes documento documentos libro libros texto textos
tesis tesina articulo articulos paper papers publicacion publicaciones
trabajo trabajos investigacion investigaciones estudio estudios lectura
academico academica academicos academicas cientifico cientifica
algo alguna alguno algunas algunos cosa tema temas
hacer haciendo elaborar redactar escribir presentar preparar avanzar
tarea tareas deber deberes practica practicas ejercicio ejercicios
monografia monografias ensayo ensayos informe informes exposicion
proyecto proyectos curso cursos clase clases examen examenes
final finales grado titulacion sustentacion
si claro ok vale bueno gracias por favor porfavor hola
sabes sabe saber
""".split())

#: Familias de la misma petición, por prefijo.
#:
#: La lista de arriba es de palabras exactas y por eso se le escapan variantes:
#: tenía "ayuda", "ayudame" y "ayudarme", pero no "ayudar", y ningún modal. El
#: 10-sep-2026, en producción, "me puedes ayudar en mi investigacion?" dejó
#: "puedes" y "ayudar" como si fueran el tema, y GUIA contestó cinco libros
#: sobre *cómo* investigar — el mismo fallo que ya se había arreglado para
#: "algo para mi tesis", reaparecido por otra conjugación.
#:
#: Enumerar conjugaciones es perder siempre: quedan "podrías ayudarme",
#: "sabrías recomendarme", "me ayudarías". Los prefijos cubren la familia
#: entera de una vez.
#:
#: Van deliberadamente largos. "dar" comería "Darwin"; "est" se comería medio
#: diccionario. Ante la duda, prefijo largo: dejar pasar una petición y buscar
#: de más es recuperable —el usuario reformula—, comerse un tema real no.
_FAMILIAS_DE_PETICION = (
    "ayud", "busc", "necesit", "recomend", "suger", "sugier", "investig",
    "pued", "podr", "quier", "quisier", "muestr", "mostrar", "ensen",
    "indic", "orient", "asesor", "apoy", "consegu", "consig", "encontr",
    "encuentr", "facilit", "proporcion", "brind", "explic", "coment",
    "prest", "sirv", "servir", "utiliz", "elabor", "realiz", "avanz", "sabr",
)

#: Palabras sin carga semántica propia.
_VACIAS = frozenset("""
a al ante bajo con contra de del desde durante en entre hacia hasta para por
segun sin sobre tras y o u e ni que qué cual cuales como cuando donde
el la los las un una unos unas lo mi mis tu tus su sus me te se nos les
es son era eran esta estan estoy estamos estas ese esa eso este esta estos
hay tiene tienen tengo mas menos muy tambien pero
""".split())


def _sin_tema(query: str) -> bool:
    """¿La consulta pide algo pero no dice sobre qué?

    Existe por un caso real del 09-sep-2026. El usuario escribió "estoy
    buscando algo para mi tesis" y GUIA fue al catálogo con la palabra "tesis",
    devolviendo cinco libros sobre *cómo redactar una tesis* — "Guía para
    elaborar una tesis", "7 Pasos para elaborar una tesis"—. Ninguno tenía que
    ver con lo que esa persona investiga, porque nunca dijo de qué trata.

    La comprobación es por vaciado: se quitan las palabras con las que se pide
    algo y las vacías; si no queda ninguna palabra de contenido, no hay tema
    que buscar y lo correcto es preguntar.
    """
    import unicodedata

    texto = unicodedata.normalize("NFKD", query.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    palabras = [p.strip(".,;:¿?¡!()\"'") for p in texto.split()]
    # Sin filtro por longitud: descartar palabras cortas se comía las siglas
    # ("¿qué tesis hay sobre IA?" quedaba sin tema, y con ella ADN, TI o 5G).
    # Las palabras cortas sin carga ya están en _VACIAS.
    def es_andamiaje(palabra: str) -> bool:
        return (
            palabra in _ANDAMIAJE_DE_PETICION
            or palabra in _VACIAS
            or palabra.startswith(_FAMILIAS_DE_PETICION)
        )

    return not [p for p in palabras if p and not es_andamiaje(p)]


def _pregunta_por_el_tema() -> str:
    """Lo que GUIA responde cuando le piden algo sin decir sobre qué."""
    return (
        "Con mucho gusto — pero necesito saber **sobre qué tema**. "
        "Puedo buscar en el catálogo de la biblioteca, en las tesis del "
        "repositorio, en los artículos de las revistas de la UPeU y en los "
        "eventos académicos.\n\n"
        "¿De qué trata lo que buscas? Por ejemplo: *nutrición infantil*, "
        "*contaminación del lago Titicaca* o *hábitos de estudio*."
    )


def _classify_answer_type(
    intent: "Intent",
    sources: list[Source],
    query: str = "",
) -> str:
    """Deriva el tipo de respuesta para el render de citas.

    Heurística determinista (punto único para agente + legacy): es un LISTADO
    cuando hay varios resultados de búsqueda enlazables; si no, NARRATIVA.
    El umbral (4) es conservador para no convertir respuestas narrativas con
    pocas citas de soporte en listas.

    El umbral por sí solo miraba **cuántas** fuentes hay, no **qué** se
    preguntó, y eso se tragaba también las preguntas: medido el 2026-09-09,
    "explícame en dos frases qué es la quinua" devolvía cinco tesis sobre
    derivados de quinua. Por eso una consulta redactada como pregunta gana al
    umbral y va a prosa.

    Se mantiene el listado como comportamiento por defecto: ante una consulta
    que es solo un tema ("nutrición infantil"), la lista de lo que hay es mejor
    respuesta que un párrafo, y además no cuesta ni una llamada al modelo.
    """
    if intent in (Intent.RESEARCH, Intent.GENERAL) and len(sources) >= 4:
        if query and _pide_explicacion(query):
            return "narrative"
        return "list"
    return "narrative"


_DEFAULT_SOURCES_INVENTORY = """\
FUENTES ACTUALMENTE DISPONIBLES (las únicas que puedes consultar):
- Koha UPeU — catálogo de la biblioteca, ~34,900 libros físicos indexados
  (puedes buscar libros, autores, materias y disponibilidad de ejemplares).
- DSpace repositorio.upeu.edu.pe — ~10,000 tesis y trabajos de investigación
  del repositorio institucional (tesis de pregrado, maestría y doctorado).
- OJS revistas.upeu.edu.pe — ~12,500 artículos científicos publicados por la UPeU.
- Indico UPeU — ~550 eventos académicos y sus contribuciones.

FUENTES NO DISPONIBLES AÚN (NO las menciones como si las tuvieras):
- ALICIA / RENATI — pendiente de integración."""


_SYSTEM_PROMPT = """\
Eres GUIA, el asistente universitario de {institution}.

# Quién eres y cómo te comportas
Eres un asistente académico — no un buscador mecánico. Tu trabajo es entender
lo que el usuario realmente necesita, no solo procesar sus palabras literales.
Razonas, infiere contexto, pides aclaración cuando hace falta, y reconoces
honestamente los límites de lo que tienes.

No te presentes ni saludas en cada turno. Continúa la conversación de forma
natural. Adapta el tono al del usuario: si escribe informal, responde informal;
si es formal, responde formal. Responde siempre en español, de forma concisa.

# Fuentes que tienes
{sources_inventory}

Cuando el usuario pregunte qué puedes hacer o qué tienes disponible, describe
este inventario. Eres tú quien tiene acceso — no derives al usuario a ningún
otro servicio.

# Cómo interpretar la intención del usuario
Antes de responder, identifica qué quiere realmente el usuario, no solo qué
escribió. Ejemplos:

- "libros de excel" → probablemente quiere aprender Excel, no literatura sobre
  el software. Busca manuales, guías prácticas, tutoriales.
- "nutrición" → demasiado amplio. Pregunta: ¿infantil, deportiva, clínica?
- "tesis de IA" → quiere investigaciones recientes sobre inteligencia artificial
  aplicada a algún campo. Busca y muestra lo que haya.
- "el libro ese de White" → infiere por contexto del historial. Si ya mencionó
  a Ellen White antes, sigue el hilo.
- "hay algo nuevo" → interpreta como "¿tienes contenido reciente sobre el tema
  que estamos hablando?" — usa el historial para deducir el tema.

Nunca tomes la pregunta más literalmente de lo necesario.

# Cuándo pedir clarificación (y cuándo no)
Pide clarificación SOLO si la consulta es tan vaga que cualquier resultado
sería inútil — normalmente cuando es 1 o 2 palabras sin contexto:

  Usuario: "libros"
  GUIA: "¿Sobre qué tema buscas? Por ejemplo: nutrición, administración,
  teología, ingeniería... Así te doy resultados más útiles."

REGLA DE UNA SOLA VUELTA: si ya pediste clarificación en el turno anterior
y el usuario respondió con cualquier cosa (aunque siga siendo vago), busca
y muestra resultados. No pidas clarificación dos veces seguidas.

NO pidas clarificación cuando:
- La consulta tiene 3+ palabras o un tema reconocible.
- El usuario acaba de responder a tu pregunta anterior.
- El usuario insiste en ver resultados generales — muéstralos.

# Cómo razonar sobre los resultados recuperados
El sistema te entrega los documentos más relevantes encontrados en el índice.

SI hay documentos relevantes:
- Lista los más útiles con título, autor si lo hay, y una línea de resumen.
- Si hay muchos resultados similares, agrúpalos ("encontré 5 libros sobre
  nutrición infantil; los más recientes son...").
- Sé honesto si los resultados son parcialmente relevantes: "encontré libros
  sobre nutrición en general, no específicamente infantil".

SI los resultados son irrelevantes o el contexto está vacío:
1. Reconoce que la búsqueda específica no dio resultados útiles.
2. NUNCA digas "ve a la biblioteca" — tú eres ese servicio.
3. Sugiere 2-3 términos alternativos concretos y ofrece intentar con ellos.
   Ejemplos: "IA" → "inteligencia artificial", "machine learning";
   "excel" → "hojas de cálculo", "ofimática", "Microsoft Office".
4. Si el usuario insiste, muestra lo que hay aunque sea imperfecto.

NUNCA inventes títulos, autores ni datos que no estén en el contexto.
Si no sabes, dilo directamente: "No encontré eso en el índice disponible."

# Estructura de respuesta
- Respuesta corta cuando la pregunta es simple o conversacional.
- Lista numerada cuando hay múltiples resultados.
- Una pregunta de seguimiento al final solo si añade valor real (no por
  protocolo). Ejemplo: si encontraste 10 libros de nutrición, preguntar
  "¿te interesa alguno en particular para darte más detalle?" tiene sentido.
- Si encontraste 0 resultados, termina con una sugerencia accionable,
  no con una disculpa vacía.

# Contexto recuperado para esta consulta
{context}"""

_CAMPUS_UNAVAILABLE = (
    "Los servicios de campus (notas, matrícula, horarios) aún no están disponibles. "
    "Por ahora puedo ayudarte con el catálogo de la biblioteca Koha (~34,900 libros), "
    "las tesis del repositorio institucional DSpace (~10,000) y los artículos de las "
    "revistas académicas OJS de UPeU (~12,500 artículos)."
)

_OUT_OF_SCOPE = (
    "Esa consulta está fuera de mi alcance como asistente universitario. "
    "Puedo ayudarte con información académica, investigación y servicios "
    "institucionales de la universidad."
)


def _detect_llm_provider(model_name: str) -> str:
    """Heurística para clasificar el LLM en local vs cloud (audit)."""
    if not model_name or model_name == "none":
        return "none"
    name = model_name.lower()
    if "claude" in name:
        return "anthropic-cloud"
    if name.startswith(("qwen", "deepseek", "llama", "gemma", "mistral")):
        return "ollama-local"
    if name == "koha":  # respuesta directa sin LLM
        return "none"
    return "unknown"


def _hits_to_context(
    hits: list[dict[str, Any]],
    koha_opac_base_url: str = "",
) -> tuple[str, list[Source]]:
    """Convierte hits de OpenSearch/pgvector a texto de contexto y fuentes.

    Lee los nombres canónicos de los campos del index sciback-publication:
    `publication_year`, `external_resource_uri`, `source`. Si el hit es de
    Koha y se pasó `koha_opac_base_url`, construye un link al OPAC.
    """
    sources: list[Source] = []
    lines: list[str] = []

    for i, hit in enumerate(hits, 1):
        title = str(hit.get("title", f"Documento {i}"))
        abstract = str(hit.get("abstract", ""))
        authors = hit.get("authors", [])
        year = hit.get("publication_year") or hit.get("year")
        url = hit.get("external_resource_uri") or hit.get("url")
        source_type = str(hit.get("source") or hit.get("source_type") or "")
        hit_id = str(hit.get("id", str(i)))

        # Para libros de Koha sin URL en el index, construir link al OPAC
        if not url and source_type == "koha":
            url = koha_opac_url(hit_id, koha_opac_base_url)

        # Contexto para el LLM — incluir autores y año para diferenciar libros homónimos
        ctx_line = f"[{i}] {title}"
        meta_parts = []
        if isinstance(authors, list) and authors:
            meta_parts.append(", ".join(str(a) for a in authors[:3]))
        if year:
            meta_parts.append(str(year))
        if meta_parts:
            ctx_line += f" — {' · '.join(meta_parts)}"
        lines.append(ctx_line)
        if abstract:
            lines.append(f"    {abstract[:300]}...")
        lines.append("")

        sources.append(
            Source(
                id=hit_id,
                title=title,
                url=str(url) if url else None,
                authors=[str(a) for a in authors] if isinstance(authors, list) else [],
                year=int(year) if year else None,
                score=float(hit.get("score", 0.0)),
                source_type=source_type or None,
            )
        )

    return "\n".join(lines), sources


def _records_to_context(records: list[VectorRecord]) -> tuple[str, list[Source]]:
    """Convierte VectorRecord de pgvector a texto de contexto y fuentes."""
    sources: list[Source] = []
    lines: list[str] = []

    for i, record in enumerate(records, 1):
        meta = record.metadata
        title = str(meta.get("title", f"Documento {i}"))
        abstract = str(meta.get("abstract", ""))
        authors = meta.get("authors", [])
        year = meta.get("year")
        url = meta.get("url")

        lines.append(f"[{i}] {title}")
        if abstract:
            lines.append(f"    {abstract[:300]}...")
        lines.append("")

        sources.append(
            Source(
                id=record.id,
                title=title,
                url=str(url) if url else None,
                authors=[str(a) for a in authors] if isinstance(authors, list) else [],
                year=int(year) if year else None,
                score=record.score,
            )
        )

    return "\n".join(lines), sources


class ChatService:
    """Servicio central de chat de GUIA.

    M4: answer() es async — no bloquea el event loop.

    Args:
        synthesis_llm: LLM completo para queries complejas (ej: qwen2.5:7b / Claude).
        store: Vector store para búsqueda semántica (pgvector).
        embedder: E5 para generar embeddings de queries.
        classifier_llm: LLM ligero para clasificación de intents.
        fast_llm: LLM rápido para queries simples/conversacionales (ej: qwen2.5:3b).
        router: ModelRouter para elegir el LLM según complejidad de la query.
        cache: Caché semántico opcional (Redis).
        institution: Nombre de la institución (para el system prompt).
        search_adapter: SearchAdapter OpenSearch (usa hybrid_dicts async).
    """

    def __init__(
        self,
        synthesis_llm: LLMPort,
        store: VectorStorePort,
        embedder: E5EmbeddingAdapter,
        *,
        classifier_llm: LLMPort | None = None,
        fast_llm: LLMPort | None = None,
        router: ModelRouter | None = None,
        cascade_router: CascadeRouter | None = None,
        cache: SemanticCache | None = None,
        institution: str = "la universidad",
        sources_inventory: str | None = None,
        koha_opac_base_url: str = "",
        search_adapter: SearchAdapter | None = None,
        koha_adapter: KohaAdapter | None = None,
        audit_repo: AuditLogRepository | None = None,
        privacy_router: PrivacyRouter | None = None,
        query_rewriter: "QueryRewriter | None" = None,
        language_gate: "LanguageGate | None" = None,
        toxicity_gate: "ToxicityGate | None" = None,
        settings: "GUIASettings | None" = None,
        agent_orchestrator: "AgentOrchestrator | None" = None,
        agenda: "AgendaAcademica | None" = None,
        directorio: "DirectorioInstitucional | None" = None,
        horario: "HorarioDeClases | None" = None,
        lector_de_peticion: "LectorDePeticion | None" = None,
    ) -> None:
        self._synthesis_llm = synthesis_llm
        self._fast_llm = fast_llm
        self._router = router
        self._cascade = cascade_router
        self._store = store
        self._embedder = embedder
        self._classifier = IntentClassifier(classifier_llm or synthesis_llm)
        self._cache = cache
        self._institution = institution
        self._sources_inventory = sources_inventory or _DEFAULT_SOURCES_INVENTORY
        self._koha_opac_base_url = koha_opac_base_url
        self._search_adapter = search_adapter
        self._koha = koha_adapter
        self._audit_repo = audit_repo
        # P2.2: PrivacyRouter — si no se inyecta, se construye uno por default.
        # Es stateless y barato (regex + tabla lookup), no tiene sentido tenerlo opcional.
        self._privacy_router = privacy_router or PrivacyRouter()
        self._query_rewriter = query_rewriter
        self._language_gate = language_gate
        self._toxicity_gate = toxicity_gate
        self._settings = settings  # opcional: habilita discovery layer si está
        # ADR-050: AgentOrchestrator — None = legacy siempre (flag ignorado)
        self._agent_orchestrator = agent_orchestrator
        # Agenda personal de Indico. None = el despliegue no la tiene
        # configurada y las consultas sobre uno mismo caen al mensaje de
        # siempre, sin romperse.
        self._agenda = agenda
        # MidPoint (quién es) y el portal de horarios (qué clase tiene hoy).
        # None = este despliegue no los tiene configurados.
        self._directorio = directorio
        self._horario = horario
        # Gate 3 de "¿dice sobre qué buscar?". None = solo la lista, como antes.
        self._lector = lector_de_peticion

    async def _synthesize_streaming(
        self,
        synthesis_llm: object,
        messages: list[LLMMessage],
        on_token: Callable[[str], Awaitable[None]],
    ) -> LLMResponse:
        """Sintetiza emitiendo cada fragmento y devuelve la respuesta completa.

        El generador del adapter es síncrono y bloqueante, así que se consume
        en un thread y los fragmentos se van pasando al bucle de eventos con
        ``run_coroutine_threadsafe``. Lo que se devuelve es un LLMResponse
        equivalente al de ``complete()``, para que el resto de ``answer()``
        —auditoría, caché, historial, render de fuentes— no distinga.

        Un fallo a mitad de emisión se propaga: el usuario ya ha visto texto
        parcial, y fingir que todo fue bien sería peor que decirlo.
        """
        bucle = asyncio.get_running_loop()
        trozos: list[str] = []

        def consumir() -> None:
            for trozo in synthesis_llm.stream(  # type: ignore[attr-defined]
                messages, max_tokens=1024, temperature=0.1
            ):
                trozos.append(trozo)
                asyncio.run_coroutine_threadsafe(on_token(trozo), bucle).result()

        await asyncio.to_thread(consumir)

        texto = "".join(trozos)
        return LLMResponse(
            content=texto,
            model=getattr(getattr(synthesis_llm, "config", None), "default_model", "stream"),
            input_tokens=0,
            output_tokens=0,
        )

    async def _que_le_falta_a_la_consulta(self, query: str) -> str | None:
        """``None`` si hay tema que buscar; si no, qué preguntarle al usuario.

        Dos decisiones separadas, y conviene no mezclarlas:

        **Si falta el tema** lo deciden, en cascada por coste —la misma idea
        que el router de intención—: la lista despacha lo evidente en 0 ms
        ("necesito hacer mi tarea" no deja ni una palabra de contenido al
        vaciarla; "contaminación del lago Titicaca" no pide nada, nombra algo)
        y lo dudoso lo decide el modelo. La zona gris —pide algo Y nombra
        cosas— es donde la lista falló dos veces en producción, y es justo
        donde un modelo lee bien.

        **Cómo se pregunta** lo escribe siempre el modelo. Antes había un
        texto fijo, igual para todos, y es lo que hacía que GUIA pareciera un
        formulario en el momento en que más falta hace parecer alguien que
        ayuda. El texto fijo queda de red de seguridad para cuando el modelo
        no conteste, que es lo que debe ser una plantilla: el plan B.

        Cuando la lista está segura de que no hay tema, su criterio manda
        aunque el modelo diga lo contrario: si tras vaciar la frase no queda
        nada, no hay nada que buscar, y eso no es opinable.
        """
        seguro_que_falta = _sin_tema(query)

        if not seguro_que_falta and not hay_peticion(query):
            return None

        if self._lector is None:
            return _pregunta_por_el_tema() if seguro_que_falta else None

        escrito = await self._lector.que_le_falta(query)
        if escrito is not None:
            return escrito

        # El modelo dice que sí hay tema, o no contestó a tiempo.
        return _pregunta_por_el_tema() if seguro_que_falta else None

    async def _responder_sobre_uno_mismo(self, request: ChatRequest) -> ChatResponse | None:
        """Contesta con los datos del que pregunta, si es que se sabe quién es.

        Tres fuentes, cada una para lo suyo, y en este orden:

        1. **MidPoint** resuelve el correo de la sesión a la persona: código
           universitario, nombre, rol y nivel. Es la fuente canónica y tiene a
           todo el mundo — frente a las 298 de 8.364 que tenía el plugin de
           Indico, que es lo que hacía que GUIA no supiera nada del 96% de la
           gente.
        2. **El portal de horarios** convierte ese código en las clases de
           hoy, con aula y hora. Es lo único que responde de verdad a "¿qué
           clases tengo hoy?": los eventos de Indico son cursos de 103 días.
        3. **Indico** queda para los cursos del semestre, cuando no hay
           horario del día que dar.

        Devuelve ``None`` si este despliegue no tiene ninguna configurada, para
        que el flujo siga por donde iba.
        """
        if self._directorio is None and self._horario is None and self._agenda is None:
            return None

        correo = request.identidad_verificada
        if not correo:
            # Anónimo. Aquí no se cae al ``user_id`` del cuerpo de la petición
            # ni a nada que venga del cliente: si no hubo login, no hay
            # titular que valga.
            return ChatResponse(
                answer=(
                    "Para eso necesito saber quién eres. Inicia sesión con tu cuenta "
                    "UPeU y te digo tus clases y tus datos.\n\n"
                    "Solo puedo mostrarte lo tuyo: no consulto los datos de otras "
                    "personas."
                ),
                intent=Intent.CAMPUS,
                sources=[],
                model_used="none",
                cached=False,
            )

        # El correo de la sesión es el ÚNICO identificador que entra. El texto
        # de la consulta no interviene: si alguien escribe el correo o el
        # código de otra persona, se ignora, porque no llega hasta aquí.
        identidad = None
        if self._directorio is not None:
            identidad = await asyncio.to_thread(
                self._directorio.de_quien_ha_iniciado_sesion, correo
            )

        nombre = (identidad.nombre_completo if identidad else None) or request.nombre_verificado
        pregunta_por_identidad = any(
            marca in request.query.lower()
            for marca in ("sabes de m", "quién soy", "quien soy", "mis datos",
                          "mi perfil", "mi información", "mi informacion")
        )

        if pregunta_por_identidad:
            agenda = await self._agenda_de(correo)
            texto = redactar_identidad(
                agenda, correo=correo, nombre=nombre, identidad=identidad
            )
            return self._respuesta_personal(texto, "midpoint")

        # "¿Qué clases tengo hoy?" — el horario del día, si se puede.
        if self._horario is not None and identidad is not None and identidad.codigo:
            horario = await asyncio.to_thread(
                self._horario.del_dia, identidad.codigo, datetime.now().date()
            )
            if horario is not None:
                return self._respuesta_personal(
                    redactar_horario(horario, nombre=nombre), "horarios"
                )

        # Sin horario del día, los cursos del semestre siguen sirviendo.
        agenda = await self._agenda_de(correo)
        if agenda is not None:
            return self._respuesta_personal(redactar(agenda, nombre=nombre), "indico")

        return self._respuesta_personal(
            f"{nombre.split()[0] + ', n' if nombre else 'N'}o encuentro clases tuyas. "
            "Si ya te matriculaste, puede que el horario aún no esté publicado — "
            "revísalo en https://indico.upeu.edu.pe/student/",
            "none",
        )

    async def _agenda_de(self, correo: str) -> "Agenda | None":
        """Los cursos del semestre en Indico, si ese servicio está puesto."""
        if self._agenda is None:
            return None
        return await asyncio.to_thread(self._agenda.de_quien_ha_iniciado_sesion, correo)

    @staticmethod
    def _respuesta_personal(texto: str, fuente: str) -> ChatResponse:
        """Envoltorio común. Nunca se cachea: ver el paso 1c de ``answer``."""
        return ChatResponse(
            answer=texto,
            intent=Intent.CAMPUS,
            sources=[],
            model_used=fuente,
            cached=False,
        )

    async def answer(
        self,
        request: ChatRequest,
        on_token: Callable[[str], Awaitable[None]] | None = None,
    ) -> ChatResponse:
        """Genera una respuesta para el ChatRequest del usuario (async).

        Args:
            request: La consulta y su contexto.
            on_token: Si se pasa y el proveedor de síntesis sabe emitir por
                fragmentos, se le entrega cada trozo según se genera. La
                respuesta devuelta es la misma con o sin él — el callback es
                un canal adicional, no un sustituto —, así que auditoría,
                caché e historial siguen funcionando igual.


        Todas las operaciones bloqueantes se ejecutan en un thread pool
        via asyncio.to_thread() para no bloquear el event loop.
        """
        import time

        t_start = time.perf_counter()
        query = request.query
        route_decision: RouteDecision | None = None  # se setea en paso 3
        sources_used_names: list[str] = []  # ['dspace', 'koha', ...] para audit
        privacy_verdict: PrivacyVerdict | None = None  # se setea en paso 5b

        # 0. ToxicityGate — bloquear antes de procesar
        if self._toxicity_gate is not None:
            tox_result = self._toxicity_gate.evaluate(query)
            if not tox_result.passed:
                response = ChatResponse(
                    answer=tox_result.user_message or "Consulta no procesable.",
                    intent=Intent.OUT_OF_SCOPE,
                    sources=[],
                    model_used="none",
                    cached=False,
                )
                await self._emit_audit(
                    request, response, route_decision, sources_used_names, t_start
                )
                return response

        # 1. Embed query (sync HTTP → thread)
        query_vector: list[float] = await asyncio.to_thread(
            self._embedder.embed_query, query
        )

        # 0b. LanguageGate — detectar idioma para contexto adicional
        language_hint: str | None = None
        if self._language_gate is not None:
            lang_result = self._language_gate.evaluate(query)
            if lang_result.user_message:
                language_hint = lang_result.user_message

        # 1c. ¿Pregunta por sus propios datos? Se decide aquí arriba, antes de
        # la caché, y no dentro de la rama CAMPUS, porque de esto depende que
        # se salte la caché.
        #
        # La caché es global por consulta y además SEMÁNTICA: guarda la
        # respuesta bajo el vector de la pregunta, no bajo el texto exacto ni
        # bajo quién preguntó. Si el horario de alguien entrara ahí, la
        # siguiente persona que escribiera algo parecido a "¿qué clases tengo
        # hoy?" recibiría el horario del anterior — que es exactamente lo que
        # no puede pasar. Así que estas consultas ni leen ni escriben caché.
        personal = es_consulta_sobre_uno_mismo(query)

        # 2. Caché hit (sync Redis → thread)
        if self._cache is not None and not personal:
            cached = await asyncio.to_thread(
                self._cache.get, query, query_vector=query_vector
            )
            if cached is not None:
                response = ChatResponse(
                    answer=cached.answer,
                    intent=cached.intent,
                    sources=cached.sources,
                    model_used=cached.model_used,
                    cached=True,
                    tokens_used=0,
                    source_buckets=getattr(cached, "source_buckets", []),
                    explore_in=getattr(cached, "explore_in", []),
                    related_terms=getattr(cached, "related_terms", []),
                    answer_type=getattr(cached, "answer_type", "narrative"),
                )
                await self._emit_audit(
                    request, response, route_decision, sources_used_names, t_start
                )
                return response

        # 2b. Sus propios datos, antes de clasificar la intención.
        #
        # Estaba dentro de la rama CAMPUS y ahí no servía: medido en producción
        # el 10-sep-2026, "¿qué sabes de mí?" lo clasifica como RESEARCH y se
        # iba a buscar al catálogo, y "que sabes de mi" con identidad en el
        # cuerpo salía OUT_OF_SCOPE. Hacer depender de una llamada al modelo el
        # camino por el que se entregan datos personales es frágil por partida
        # doble: falla como aquí, y cambia si cambia el modelo.
        #
        # La detección de arriba es determinista, así que decide ella.
        if personal:
            respuesta_personal = await self._responder_sobre_uno_mismo(request)
            if respuesta_personal is not None:
                # Sin caché, ni de lectura ni de escritura: ver el paso 1c.
                await self._emit_audit(
                    request, respuesta_personal, route_decision,
                    [*sources_used_names, "indico"], t_start,
                )
                return respuesta_personal

        # 3. Clasificar intent + tier
        # Si el CascadeRouter está disponible (P1.2), preferirlo: ahorra
        # ~150-300ms en queries triviales que resuelve en Gate 1 o Gate 2.
        # El intent_hint (test override) sigue teniendo precedencia.
        route_decision = None
        if request.intent_hint is not None:
            intent = request.intent_hint
        elif self._cascade is not None:
            # El historial va a Gate 3: sin él, un turno de continuación
            # ("sí, quiero información académica") se clasifica por sus
            # palabras sueltas en vez de por lo que significa en la conversación.
            route_decision = self._cascade.decide(
                query,
                query_vector,
                history=[
                    LLMMessage(role=t.role, content=t.content)
                    for t in request.history
                ],
            )
            intent = category_to_intent(route_decision.intent)
        else:
            intent = await self._classifier.classify(query)

        # 4. Respuestas directas sin RAG
        if intent == Intent.OUT_OF_SCOPE:
            response = ChatResponse(
                answer=_OUT_OF_SCOPE,
                intent=intent,
                sources=[],
                model_used="none",
                cached=False,
            )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        if intent == Intent.CAMPUS:
            # Si hay Koha conectado, buscar en el catálogo y enriquecer con disponibilidad
            if self._koha is not None:
                koha_results = await asyncio.to_thread(self._koha.search, query, per_page=5)
                if koha_results:
                    sources: list[Source] = []
                    avail_lines: list[str] = []
                    for pub in koha_results:
                        biblio_id = next(
                            (
                                int(eid.value.split(":")[1])
                                for eid in getattr(pub, "external_ids", [])
                                if "koha:" in str(eid.value)
                            ),
                            None,
                        )
                        avail = (
                            await asyncio.to_thread(self._koha.get_availability, biblio_id)
                            if biblio_id is not None
                            else {}
                        )
                        title = pub.title.primary_value if pub.title else "Sin título"
                        total_copies = avail.get("total", 0)
                        available = avail.get("available", 0)
                        avail_str = (
                            f"{available}/{total_copies} ejemplares disponibles"
                            if total_copies
                            else "sin ejemplares registrados"
                        )
                        avail_lines.append(f"- **{title}** — {avail_str}")
                        sources.append(
                            Source(
                                id=str(biblio_id or pub.title.primary_value[:20]),
                                title=title,
                                source_type="book",
                            )
                        )
                    answer = (
                        f"Encontré estos libros en el catálogo de la biblioteca:\n\n"
                        + "\n".join(avail_lines)
                    )
                    sources_used_names.append("koha")
                    response = ChatResponse(
                        answer=answer,
                        intent=intent,
                        sources=sources,
                        model_used="koha",
                        cached=False,
                    )
                    if self._cache is not None:
                        await asyncio.to_thread(
                            self._cache.set, query, response, query_vector=query_vector
                        )
                    await self._emit_audit(
                        request, response, route_decision, sources_used_names, t_start
                    )
                    return response

            response = ChatResponse(
                answer=_CAMPUS_UNAVAILABLE,
                intent=intent,
                sources=[],
                model_used="none",
                cached=False,
            )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        # 4b. GREETING: respuesta conversacional directa sin RAG
        if route_decision is not None and route_decision.intent == IntentCategory.GREETING:
            greeting_llm = self._fast_llm or self._synthesis_llm
            greeting_system = (
                f"Eres GUIA, el asistente universitario de {self._institution}. "
                "Responde de forma breve, amigable y directa. No hagas búsquedas "
                "en el catálogo. No inventes información.\n\n"
                f"{self._sources_inventory}\n\n"
                "Si el usuario pregunta qué puedes hacer, qué fuentes tienes o si "
                "tienes acceso a alguna fuente, describe el inventario anterior de "
                "forma conversacional (qué tienes y qué aún no). Tú eres quien tiene "
                "acceso a esas fuentes — no derives al usuario a otro servicio."
            )
            g_messages = [LLMMessage(role="system", content=greeting_system)]
            for turn in request.history:
                g_messages.append(LLMMessage(role=turn.role, content=turn.content))
            g_messages.append(LLMMessage(role="user", content=query))
            g_response = await asyncio.to_thread(
                greeting_llm.complete, g_messages, max_tokens=350, temperature=0.3
            )
            response = ChatResponse(
                answer=g_response.content,
                intent=intent,
                sources=[],
                model_used=g_response.model,
                cached=False,
            )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        # 4c. Sin tema no hay nada que buscar: preguntar en vez de adivinar.
        #
        # Caso real del 09-sep-2026: "estoy buscando algo para mi tesis" fue al
        # catálogo con la palabra "tesis" y devolvió cinco libros sobre cómo
        # redactar una tesis. Ninguno servía, porque el usuario nunca dijo de
        # qué trata la suya. Buscar sin tema no es dar un resultado imperfecto:
        # es dar uno que no responde a nada.
        # Se LANZA aquí y se recoge en 5c, después de buscar. Las dos cosas son
        # independientes —una mira el texto, la otra el índice— y esperarlas en
        # fila costaba los 0,9 s de la llamada al modelo en toda búsqueda
        # normal: medido el 10-sep-2026, "libros sobre nutrición infantil"
        # pasaba por el modelo solo para que confirmara que sí, que hay tema.
        #
        # Si resulta que faltaba el tema, la búsqueda hecha se descarta. Sale a
        # cuenta: descartar una búsqueda es barato y ocurre pocas veces;
        # esperar a preguntar era caro y ocurría siempre.
        tarea_falta: asyncio.Task[str | None] | None = None
        if intent in (Intent.RESEARCH, Intent.GENERAL):
            tarea_falta = asyncio.create_task(self._que_le_falta_a_la_consulta(query))
            # Si la búsqueda revienta antes de que lleguemos a recogerla, nadie
            # miraría su excepción y asyncio lo avisaría por consola. Esto la
            # consume: la tarea es prescindible, no debe ensuciar el log de un
            # fallo que viene de otro sitio.
            tarea_falta.add_done_callback(
                lambda t: t.cancelled() or t.exception()
            )

        # 5. RAG: reescribir query con pipeline NLP (ADR-044) antes del retrieval
        search_text = query
        if self._query_rewriter is not None:
            try:
                rewrite = await self._query_rewriter.rewrite(
                    query,
                    [{"role": t.role, "content": t.content} for t in request.history],
                )
                if rewrite.is_search_query and rewrite.cleaned:
                    search_text = rewrite.cleaned
            except Exception:
                pass

        hits: list[dict[str, Any]] = []
        if self._search_adapter is not None:
            # M4: await directo, sin asyncio.run() bridge
            hits = await self._search_adapter.hybrid_dicts(
                text=search_text,
                vector=query_vector,
                limit=5,
            )
            context_text, sources = _hits_to_context(hits, self._koha_opac_base_url)
            sources_used_names.append("opensearch")
        else:
            records = await asyncio.to_thread(
                self._store.search, query_vector, limit=5, min_score=0.3
            )
            context_text, sources = _records_to_context(records)
            if records:
                sources_used_names.append("pgvector")

        # 5c. Ahora sí: ¿la consulta decía sobre qué buscar?
        #
        # Caso real del 09-sep-2026: "estoy buscando algo para mi tesis" fue al
        # catálogo con la palabra "tesis" y devolvió cinco libros sobre cómo
        # redactar una tesis. Ninguno servía, porque el usuario nunca dijo de
        # qué trata la suya. Buscar sin tema no es dar un resultado imperfecto:
        # es dar uno que no responde a nada, y por eso los hits se tiran.
        falta = await tarea_falta if tarea_falta is not None else None
        if falta is not None:
            response = ChatResponse(
                answer=falta,
                intent=intent,
                sources=[],
                model_used="pregunta_por_el_tema",
                cached=False,
            )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        # 5a. Discovery layer (serendipia controlada) — solo en RESEARCH/GENERAL
        # con settings disponible. CAMPUS/OUT_OF_SCOPE/GREETING ya retornaron antes.
        source_buckets: list = []
        explore_in: list = []
        related_terms: list[str] = []
        if self._settings is not None and intent in (Intent.RESEARCH, Intent.GENERAL):
            from guia.services.discovery import (
                build_explore_links,
                build_source_buckets,
                extract_related_terms,
            )

            source_buckets = build_source_buckets(hits, query, self._settings)
            explore_in = build_explore_links(query, source_buckets, self._settings)
            related_terms = extract_related_terms(hits, query)

        # 5b. PrivacyRouter (P2.2) — combina sources + PII en query/docs.
        # MAX-LEVEL-WINS: si final_level >= L2_PERSONAL → force_local.
        privacy_verdict = self._privacy_router.evaluate(
            query=query,
            sources_used=sources_used_names,
            retrieved_docs_text=context_text,
        )

        # 6. Punto de bifurcación: AgentOrchestrator vs pipeline legacy (ADR-050).
        # Condiciones para activar el agente:
        # - flag agent_mode_enabled=True en settings
        # - _agent_orchestrator inyectado (no None)
        # - intent es RESEARCH o GENERAL (no triviales)
        # - sin PII que obligue a Mac Mini local (force_local bloquea cloud agent)
        # - user_id cae en el bucket agent según rollout_pct
        _rollout_pct = getattr(self._settings, "agent_mode_rollout_pct", 0)
        _agent_enabled = getattr(self._settings, "agent_mode_enabled", False)

        # Construir historial como LLMMessage para el orquestador
        history_as_llm_messages = [
            LLMMessage(role=turn.role, content=turn.content)
            for turn in request.history
        ]

        use_agent = (
            _agent_enabled
            and self._agent_orchestrator is not None
            and intent in (Intent.RESEARCH, Intent.GENERAL)
            and not privacy_verdict.force_local
            and assign_bucket(request.user_id, _rollout_pct) == "agent"
        )

        # ── Rama agente (con techo de tiempo → fallback a legacy) ─────────
        # Guarda crítica: el orquestador hace hasta max_iter llamadas LLM
        # secuenciales a NIM (cloud) sin cota propia; un proveedor lento podía
        # producir respuestas de >5 min. wait_for acota y, si expira, caemos al
        # path legacy estable en vez de dejar al usuario esperando.
        orch_result = None
        if use_agent:
            try:
                orch_result = await asyncio.wait_for(
                    self._agent_orchestrator.run(  # type: ignore[union-attr]
                        query=query,
                        history=history_as_llm_messages,
                        privacy_verdict=privacy_verdict,
                    ),
                    timeout=getattr(self._settings, "agent_timeout_s", 25.0),
                )
            except (TimeoutError, asyncio.TimeoutError):
                __import__("logging").getLogger(__name__).warning(
                    "agent_orchestrator_timeout_fallback_legacy timeout_s=%s",
                    getattr(self._settings, "agent_timeout_s", 25.0),
                )
                use_agent = False  # fallthrough al pipeline legacy de abajo

        if use_agent and orch_result is not None:
            answer_text = orch_result.answer
            # Convertir VectorRecord del orquestador a Source del dominio
            def _rec_to_source(rec: "VectorRecord") -> Source:
                meta: dict[str, Any] = rec.metadata or {}
                raw_authors = meta.get("authors")
                authors_list: list[str] = (
                    [str(a) for a in raw_authors]
                    if isinstance(raw_authors, list)
                    else []
                )
                raw_year = meta.get("year")
                year_int: int | None = int(str(raw_year)) if raw_year else None
                raw_url = meta.get("url")
                url_str: str | None = str(raw_url) if raw_url else None
                src_type = str(meta.get("source") or "") or None
                # Libros físicos de Koha no traen URL en el index: derivar el OPAC
                # desde el doc_id (mismo helper que el path legacy, sin alucinación).
                if not url_str and src_type == "koha":
                    url_str = koha_opac_url(rec.id, self._koha_opac_base_url)
                return Source(
                    id=rec.id,
                    title=str(meta.get("title") or rec.id),
                    url=url_str,
                    authors=authors_list,
                    year=year_int,
                    score=rec.score,
                    source_type=src_type,
                )
            sources = [_rec_to_source(rec) for rec in orch_result.sources]
            agent_actions_list = [t.action for t in orch_result.trace]
            response = ChatResponse(
                answer=answer_text,
                intent=intent,
                sources=sources,
                model_used="agent",
                cached=False,
                tokens_used=0,
                source_buckets=source_buckets,
                explore_in=explore_in,
                related_terms=related_terms,
                answer_type=_classify_answer_type(intent, sources, query),
            )
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.set, query, response, query_vector=query_vector
                )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start,
                privacy_verdict, pii_redacted=False,
                orchestrator_mode="agent",
                agent_iterations=orch_result.iterations,
                agent_actions=agent_actions_list,
                agent_fallback=orch_result.fallback,
                agent_forced_synthesis=orch_result.forced_synthesis,
            )
            return response

        # ── Rama legacy (pipeline original — NO TOCAR) ────────────────────

        # 6b. Elegir LLM de síntesis según privacidad + complejidad.
        # Prioridad 1: privacy_verdict.force_local fuerza fast_llm si es local.
        # Prioridad 2: tier de RouteDecision (CascadeRouter).
        # Prioridad 3: ModelRouter legacy.
        # Prioridad 4: synthesis_llm directo.
        if privacy_verdict.force_local and self._fast_llm is not None:
            # GUARDRAIL DE PRIVACIDAD: datos L2/L3 nunca van a cloud
            synthesis_llm = self._fast_llm
        elif route_decision is not None and self._fast_llm is not None:
            synthesis_llm = (
                self._fast_llm
                if route_decision.tier == Tier.T0_FAST
                else self._synthesis_llm
            )
        elif (
            intent != Intent.RESEARCH
            and self._fast_llm is not None
            and self._router is not None
            and self._router.ready
        ):
            tier_legacy = self._router.route(query_vector)
            synthesis_llm = (
                self._fast_llm if tier_legacy == QueryTier.FAST else self._synthesis_llm
            )
        else:
            synthesis_llm = self._synthesis_llm

        # 6c. PII redaction (P2.3) — segunda capa de defensa.
        # Si vamos a cloud (no force_local) Y hay PII en query/contexto,
        # reemplazar por placeholders antes de enviar; re-hidratar después.
        # Si vamos a local (force_local=True), no redactamos: el LLM local
        # ya está en infraestructura controlada.
        going_to_cloud = synthesis_llm is self._synthesis_llm and not (
            privacy_verdict and privacy_verdict.force_local
        )
        pii_replacements: dict[str, str] = {}
        query_for_llm = query
        context_for_llm = context_text
        if going_to_cloud:
            d_query = redact(query)
            d_context = redact(context_text) if context_text else redact("")
            if d_query.has_pii or d_context.has_pii:
                query_for_llm = d_query.redacted_text
                context_for_llm = d_context.redacted_text
                pii_replacements = {**d_query.replacements, **d_context.replacements}

        # 7. Síntesis LLM (sync → thread)
        #
        # Salvo cuando la respuesta va a ser un LISTADO. En ese caso el canal
        # sustituye la prosa del modelo por el render con enlaces
        # (render_results_list), así que sintetizar es pagar la espera entera
        # por un texto que se descarta: medido el 2026-09-08, entre 48 y 107
        # segundos tirados en las consultas más frecuentes del piloto.
        #
        # Se puede decidir aquí porque _classify_answer_type solo mira el intent
        # y las fuentes, y ambos ya están resueltos en este punto. La respuesta
        # que se devuelve lleva un texto de reserva: el canal lo reemplaza, y
        # quien consuma la API sin ese render sigue recibiendo algo legible.
        if _classify_answer_type(intent, sources, query) == "list":
            # El listado con enlaces lo pone el canal. Lo que se le pide al
            # modelo es lo que ese listado no dice: qué clase de material es,
            # cuál sirve para qué, y si algo no encaja con lo que se pidió.
            #
            # Antes aquí no se llamaba al modelo, y por dos razones buenas: el
            # canal descartaba la prosa, y esa prosa repetía los títulos. Las
            # dos se caen cuando lo que escribe es orientación en vez de
            # repetición, y el canal la antepone en vez de sustituirla.
            emisor = None
            if on_token is not None and hasattr(synthesis_llm, "stream"):
                async def emisor(  # type: ignore[misc]
                    mensajes: list[LLMMessage],
                    emitir: Callable[[str], Awaitable[None]],
                ) -> LLMResponse:
                    return await self._synthesize_streaming(synthesis_llm, mensajes, emitir)

            texto = await orientar(
                synthesis_llm,
                query,
                sources,
                de_reserva=_encabezado_listado(sources),
                stream=emisor,
                on_token=on_token,
            )
            return ChatResponse(
                answer=texto,
                intent=intent,
                sources=sources,
                model_used="listado_con_orientacion",
                cached=False,
                tokens_used=0,
                source_buckets=source_buckets,
                answer_type="list",
            )

        context_block = (
            context_for_llm
            if context_for_llm
            else (
                "(la búsqueda no devolvió documentos relevantes — sigue las "
                "instrucciones de la sección 'Cómo razonar sobre el contexto "
                "recuperado' para sugerir reformular con sinónimos)"
            )
        )
        context_block_final = context_block
        if language_hint:
            context_block_final = f"[Nota: {language_hint}]\n\n{context_block}"
        system = _SYSTEM_PROMPT.format(
            institution=self._institution,
            sources_inventory=self._sources_inventory,
            context=context_block_final,
        )
        messages = [LLMMessage(role="system", content=system)]
        for turn in request.history:
            messages.append(LLMMessage(role=turn.role, content=turn.content))
        messages.append(LLMMessage(role="user", content=query_for_llm))

        # Techo de tiempo de la síntesis legacy. El LLM sync no tiene cota propia;
        # un modelo lento/saturado producía cuelgues de minutos (histórico p95 254s)
        # que dejaban al usuario esperando indefinidamente → causa raíz de la baja
        # adopción del piloto. Al expirar devolvemos una respuesta honesta con las
        # fuentes que SÍ recuperamos, en vez de colgar.
        _legacy_timeout = getattr(self._settings, "legacy_synthesis_timeout_s", 45.0)
        try:
            if on_token is not None and hasattr(synthesis_llm, "stream"):
                llm_response = await asyncio.wait_for(
                    self._synthesize_streaming(synthesis_llm, messages, on_token),
                    timeout=_legacy_timeout,
                )
            else:
                llm_response = await asyncio.wait_for(
                    asyncio.to_thread(
                        synthesis_llm.complete, messages, max_tokens=1024, temperature=0.1
                    ),
                    timeout=_legacy_timeout,
                )
        except (TimeoutError, asyncio.TimeoutError):
            __import__("logging").getLogger(__name__).warning(
                "legacy_synthesis_timeout query_hash=%s timeout_s=%s sources=%d",
                hash_query(query), _legacy_timeout, len(sources),
            )
            if sources:
                fallback_answer = (
                    "La consulta está tardando más de lo normal y no pude redactar "
                    "una respuesta a tiempo. De todos modos encontré estas fuentes que "
                    "pueden ayudarte — revísalas mientras tanto, o reformula la pregunta "
                    "de forma más específica e inténtalo de nuevo."
                )
            else:
                fallback_answer = (
                    "La consulta está tardando más de lo normal y no pude responder a "
                    "tiempo. Por favor reformúlala de forma más específica e inténtalo "
                    "de nuevo en un momento."
                )
            timeout_response = ChatResponse(
                answer=fallback_answer,
                intent=intent,
                sources=sources,
                model_used="legacy_timeout",
                cached=False,
                tokens_used=0,
                source_buckets=source_buckets,
                explore_in=explore_in,
                related_terms=related_terms,
                answer_type=_classify_answer_type(intent, sources, query),
            )
            # No cacheamos un timeout: la próxima vez puede sintetizar bien.
            await self._emit_audit(
                request, timeout_response, route_decision, sources_used_names,
                t_start, privacy_verdict, pii_redacted=bool(pii_replacements),
                orchestrator_mode="legacy",
            )
            return timeout_response

        # 7b. Re-hidratar la respuesta del LLM (si redactamos antes)
        answer_text = llm_response.content
        if pii_replacements:
            answer_text = restore(answer_text, pii_replacements)

        response = ChatResponse(
            answer=answer_text,
            intent=intent,
            sources=sources,
            model_used=llm_response.model,
            cached=False,
            tokens_used=llm_response.input_tokens + llm_response.output_tokens,
            source_buckets=source_buckets,
            explore_in=explore_in,
            related_terms=related_terms,
            answer_type=_classify_answer_type(intent, sources, query),
        )

        # 8. Guardar en caché (sync Redis → thread)
        if self._cache is not None:
            await asyncio.to_thread(
                self._cache.set, query, response, query_vector=query_vector
            )

        await self._emit_audit(
            request, response, route_decision, sources_used_names, t_start,
            privacy_verdict, pii_redacted=bool(pii_replacements),
            orchestrator_mode="legacy",
        )
        return response

    async def _emit_audit(
        self,
        request: ChatRequest,
        response: ChatResponse,
        route_decision: RouteDecision | None,
        sources_used: list[str],
        t_start: float,
        privacy_verdict: PrivacyVerdict | None = None,
        pii_redacted: bool = False,
        orchestrator_mode: str | None = None,
        agent_iterations: int | None = None,
        agent_actions: list[str] | None = None,
        agent_fallback: bool = False,
        agent_forced_synthesis: bool = False,
    ) -> None:
        """Emite entrada de audit_log fire-and-forget.

        No-op si no hay audit_repo configurado. La query original NUNCA
        se persiste — solo sha256(query). Errores se loguean pero no se
        propagan: el audit no debe romper la respuesta al usuario.
        """
        if self._audit_repo is None:
            return

        import time

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        # P2.2: privacidad final = privacy_verdict si existe (más preciso),
        # sino route_decision.privacy del CascadeRouter, sino default cloud_ok.
        if privacy_verdict is not None:
            privacy_level = (
                "always_local" if privacy_verdict.force_local else "cloud_ok"
            )
            pii_detected = privacy_verdict.pii_in_query or privacy_verdict.pii_in_docs
        elif route_decision is not None:
            privacy_level = route_decision.privacy.value
            pii_detected = False
        else:
            privacy_level = "cloud_ok"
            pii_detected = False

        gate_used = (
            route_decision.gate_used.value if route_decision is not None else "unknown"
        )

        from typing import Literal as _Literal
        _orch_mode: _Literal["legacy", "agent"] | None = None
        if orchestrator_mode == "agent":
            _orch_mode = "agent"
        elif orchestrator_mode == "legacy":
            _orch_mode = "legacy"

        entry = AuditLogEntry(
            user_id=request.user_id or "anonymous",
            session_id=request.session_id,
            query_hash=hash_query(request.query),
            intent=response.intent.value,
            privacy_level=privacy_level,
            sources_used=list(sources_used),
            llm_model=response.model_used or "none",
            llm_provider=_detect_llm_provider(response.model_used or ""),
            gate_used=gate_used,
            pii_detected=pii_detected,
            pii_redacted=pii_redacted,
            latency_ms=latency_ms,
            cached=response.cached,
            orchestrator_mode=_orch_mode,
            agent_iterations=agent_iterations,
            agent_actions=agent_actions,
            agent_fallback=agent_fallback,
            agent_forced_synthesis=agent_forced_synthesis,
        )
        try:
            await self._audit_repo.record(entry)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("audit_emit_failed", exc_info=True)
