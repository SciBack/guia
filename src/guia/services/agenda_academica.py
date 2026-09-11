"""Las clases de quien está preguntando, y de nadie más.

Consulta ``GET /academic-identity/lookup`` de Indico, que resuelve un
identificador —correo institucional, ``id_persona``, eduPerson— a la persona
y a los eventos en los que está inscrita: qué clase tiene ahora y cuál sigue.

**Por qué la firma no acepta un identificador.** Esa ruta se autentica con un
token de servicio, y un token de servicio dice "soy GUIA", no "soy Fulano
preguntando por Fulano": con él se puede consultar a cualquiera. Indico no
tiene forma de saber si quien pregunta es el titular, así que esa regla vive
entera aquí, y la forma de que aguante es que no exista el parámetro por el
que colarse.

De ahí ``de_quien_ha_iniciado_sesion(correo_verificado)``. Solo se le pasa el
correo que devolvió Keycloak tras el login de M365. Si mañana alguien quiere
consultar por otra persona tiene que cambiar esta firma, que es justo la clase
de cambio que se ve en una revisión — a diferencia de un argumento de más en
una llamada, que no se ve.

Importa porque el que consulta es un modelo de lenguaje. Si la herramienta
admitiera un identificador, bastaría con escribir «¿qué clases tiene María
Quispe hoy?» para que el modelo lo rellenara con lo que le pidieran. El
guardarraíl no puede ser una instrucción en el prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx

from guia.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Clase:
    """Un evento de Indico en el que la persona está inscrita."""

    titulo: str
    inicio: datetime | None
    fin: datetime | None
    lugar: str | None

    def cuando(self) -> str:
        """La franja en formato legible, o cadena vacía si no hay horas."""
        if self.inicio is None:
            return ""
        hora_inicio = self.inicio.strftime("%H:%M")
        if self.fin is None:
            return hora_inicio
        return f"{hora_inicio}–{self.fin.strftime('%H:%M')}"  # noqa: RUF001 — rango de horas, va con guion largo


@dataclass(frozen=True)
class Agenda:
    """Lo que Indico sabe de la persona que ha iniciado sesión."""

    id_persona: str | None
    edu_person_principal_name: str | None
    edu_person_unique_id: str | None
    ahora: Clase | None
    siguiente: Clase | None
    proximas: list[Clase] = field(default_factory=list)

    @property
    def tiene_clases(self) -> bool:
        return bool(self.proximas or self.ahora or self.siguiente)


def _fecha(valor: object) -> datetime | None:
    """ISO-8601 de Indico a datetime; None si viene vacío o ilegible."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        logger.warning("agenda_fecha_ilegible", valor=valor)
        return None


def _clase(crudo: object) -> Clase | None:
    if not isinstance(crudo, dict):
        return None
    titulo = crudo.get("title")
    if not isinstance(titulo, str) or not titulo.strip():
        return None
    lugar = crudo.get("location")
    return Clase(
        titulo=titulo.strip(),
        inicio=_fecha(crudo.get("start")),
        fin=_fecha(crudo.get("end")),
        lugar=lugar.strip() if isinstance(lugar, str) and lugar.strip() else None,
    )


class AgendaAcademica:
    """Cliente de la ruta de identidad de Indico.

    Args:
        base_url: Raíz de Indico (``https://indico.upeu.edu.pe``).
        token: El token de servicio, el mismo valor que
            ``ACADEMIC_IDENTITY_SYNC_TOKEN`` en el servidor de Indico. Sin él
            la ruta responde 401 y este cliente no sirve para nada, así que se
            comprueba al construirlo y no en cada consulta.
        timeout: Techo por petición. Corto a propósito: esto está en el camino
            de una respuesta de chat, y es mejor decir "no pude consultarlo"
            que dejar a alguien esperando.
    """

    def __init__(self, base_url: str, token: str, *, timeout: float = 3.0) -> None:
        self._url = base_url.rstrip("/") + "/academic-identity/lookup"
        self._token = token
        self._http = httpx.Client(timeout=timeout)

    @property
    def configurada(self) -> bool:
        """¿Hay base y token? Sin las dos cosas no se consulta nada."""
        return bool(self._token) and self._url.startswith("http")

    def de_quien_ha_iniciado_sesion(  # noqa: PLR0911 — un return por cada motivo de no tener dato; fundirlos los haría indistinguibles en el registro
        self, correo_verificado: str
    ) -> Agenda | None:
        """La agenda del titular de ese correo.

        Args:
            correo_verificado: El correo que devolvió Keycloak tras el login
                de M365. **Nunca** un dato sacado del texto del chat: ese es
                el único punto por el que se podría pedir la agenda de otra
                persona.

        Returns:
            La agenda, o ``None`` si Indico no conoce a esa persona, si no
            está configurado el acceso o si el servicio no responde. Los tres
            casos se tratan igual de cara al usuario —no hay dato que dar— y
            se distinguen en el registro, que es donde importa la diferencia.
        """
        if not self.configurada:
            logger.warning("agenda_sin_configurar")
            return None

        correo = (correo_verificado or "").strip()
        if not correo:
            return None

        try:
            r = self._http.get(
                self._url,
                params={"identifier": correo},
                headers={"X-Academic-Identity-Token": self._token},
            )
        except Exception as exc:
            logger.warning("agenda_indico_no_responde", error=str(exc))
            return None

        if r.status_code == 404:
            # Indico no tiene a esa persona en el libro de identidades. Es lo
            # normal para el personal que no está inscrito en nada.
            return None
        if r.status_code == 401:
            # El token no vale. Se registra aparte porque el remedio es otro:
            # aquí no falta el dato, falta la credencial.
            logger.error("agenda_token_rechazado")
            return None
        if r.status_code != 200:
            logger.warning("agenda_respuesta_inesperada", codigo=r.status_code)
            return None

        try:
            datos = r.json()
        except ValueError:
            logger.warning("agenda_respuesta_no_es_json")
            return None

        if not isinstance(datos, dict) or not datos.get("found"):
            return None

        identidad = datos.get("identity") or {}
        if not isinstance(identidad, dict):
            identidad = {}

        def _texto(clave: str) -> str | None:
            valor = identidad.get(clave)
            return valor if isinstance(valor, str) and valor.strip() else None

        proximas = [c for c in (_clase(x) for x in datos.get("classes") or []) if c]
        return Agenda(
            id_persona=_texto("id_persona"),
            edu_person_principal_name=_texto("eduPersonPrincipalName"),
            edu_person_unique_id=_texto("eduPersonUniqueId"),
            ahora=_clase(datos.get("current")),
            siguiente=_clase(datos.get("next")),
            proximas=proximas,
        )

    def cerrar(self) -> None:
        """Cierra el pool HTTP. La llama el container al apagarse."""
        self._http.close()


def redactar(agenda: Agenda, *, nombre: str | None = None) -> str:
    """Pasa la agenda a texto para el chat.

    Se redacta aquí y no se le pide al modelo que lo haga: son datos personales
    del propio usuario y no hay nada que interpretar, así que pasarlos por una
    síntesis solo añade latencia y una ocasión de que se inventen detalles.
    """
    saludo = f"{nombre}, " if nombre else ""

    if not agenda.tiene_clases:
        return (
            f"{saludo}no tienes clases registradas por delante en Indico. "
            "Si esperabas ver alguna, revisa tu inscripción en "
            "https://indico.upeu.edu.pe/"
        )

    lineas: list[str] = []

    if agenda.ahora is not None:
        donde = f" en {agenda.ahora.lugar}" if agenda.ahora.lugar else ""
        lineas.append(f"**Ahora mismo:** {agenda.ahora.titulo}{donde} ({agenda.ahora.cuando()})")

    if agenda.siguiente is not None:
        donde = f" en {agenda.siguiente.lugar}" if agenda.siguiente.lugar else ""
        cuando = agenda.siguiente.cuando()
        if agenda.siguiente.inicio is not None:
            cuando = f"{agenda.siguiente.inicio.strftime('%d/%m')} {cuando}"
        lineas.append(f"**Después:** {agenda.siguiente.titulo}{donde} ({cuando})")

    restantes = [c for c in agenda.proximas if c not in (agenda.ahora, agenda.siguiente)]
    if restantes:
        lineas.append("\n**Más adelante:**")
        for clase in restantes[:5]:
            donde = f" — {clase.lugar}" if clase.lugar else ""
            fecha = clase.inicio.strftime("%d/%m") if clase.inicio else ""
            lineas.append(f"- {fecha} {clase.cuando()} · {clase.titulo}{donde}")

    cabecera = (
        f"{saludo}esto es lo que tienes en Indico:"
        if saludo
        else "Esto es lo que tienes en Indico:"
    )
    return cabecera + "\n\n" + "\n".join(lineas)


def redactar_identidad(
    agenda: Agenda | None,
    *,
    correo: str,
    nombre: str | None = None,
    identidad: object | None = None,
) -> str:
    """Responde a "¿qué sabes de mí?" con los datos del propio titular.

    Se responde con lo que hay en la sesión aunque Indico no conozca a la
    persona: el correo y el nombre vienen del login de M365 y son suyos, así
    que negárselos no protege a nadie. Lo que falte se dice que falta, en vez
    de dejar el hueco.
    """
    lineas = [f"- **Correo institucional:** {correo}"]
    if nombre:
        lineas.insert(0, f"- **Nombre:** {nombre}")

    # Lo que sabe MidPoint, que es la fuente canónica y cubre a todo el mundo.
    # La allow-list de su cuenta de servicio deja fuera DNI, fecha de
    # nacimiento y foto, así que aquí no puede aparecer nada de eso.
    if identidad is not None:
        for etiqueta, atributo in (
            ("Código universitario", "codigo"),
            ("Condición", "rol"),
            ("Nivel", "nivel"),
        ):
            valor = getattr(identidad, atributo, None)
            if valor:
                lineas.append(f"- **{etiqueta}:** {valor}")

        unidades = getattr(identidad, "unidades", ()) or ()
        if unidades:
            lineas.append(f"- **Unidad:** {', '.join(unidades)}")

    if agenda is not None:
        if agenda.id_persona:
            lineas.append(f"- **Código de persona (Oracle):** {agenda.id_persona}")
        if agenda.edu_person_principal_name:
            lineas.append(f"- **Identificador académico:** {agenda.edu_person_principal_name}")
        if agenda.tiene_clases:
            cuantas = len(agenda.proximas)
            lineas.append(
                f"- **Clases registradas:** {cuantas} por delante en Indico"
                if cuantas
                else "- **Clases registradas:** sí, en Indico"
            )

    cuerpo = "\n".join(lineas)
    cierre = (
        "\n\nEsto es lo que veo de ti porque iniciaste sesión con tu cuenta UPeU. "
        "Solo puedo mostrarte tus propios datos: no consulto los de otras personas."
    )
    return "Esto es lo que sé de ti:\n\n" + cuerpo + cierre


#: Se mira el texto en vez de preguntárselo al modelo por dos razones: está en
#: el camino de cada consulta y una llamada más cuesta latencia, y sobre todo
#: porque de esta decisión depende que se salte la caché compartida — conviene
#: que sea determinista y se pueda leer de un vistazo, no que dependa de cómo
#: respondió el modelo esa vez.
#:
#: Hacen falta DOS señales, y esto es lo importante: hablar de uno mismo no
#: basta. "Bibliografía para mi tesis", "libros para mi tarea" o "artículos
#: para mi investigación" son búsquedas de catálogo de toda la vida, y son
#: además de las consultas más frecuentes. Con la primera persona a secas se
#: habrían desviado a Indico, que no tiene libros. Por eso también tiene que
#: aparecer algo de agenda o de identidad.
_PRIMERA_PERSONA = (
    "mi ", "mis ", "tengo", "me toca", "estoy", "soy ", " me ",
)

_ASUNTO_PERSONAL = (
    "clase", "clases", "curso", "cursos", "horario", "horarios", "aula",
    "aulas", "salón", "salon", "matrícula", "matricula", "matriculado",
    "inscrito", "inscrita", "datos", "perfil", "identidad", "código",
    "codigo", "información personal", "informacion personal",
)

#: Frases que ya no necesitan la segunda señal: son inequívocas.
_INEQUIVOCAS = (
    "sabes de mí", "sabes de mi", "sabes sobre mí", "sabes sobre mi",
    "quién soy", "quien soy", "mis datos", "mi perfil", "mi horario",
    "mis clases", "mis cursos", "mi próxima clase", "mi proxima clase",
)


def es_consulta_sobre_uno_mismo(texto: str) -> bool:
    """¿Está preguntando por sus propios datos académicos?

    Falso negativo: responde el camino normal, que ya funcionaba. Falso
    positivo: se salta la caché y se consulta Indico de más, y peor, una
    búsqueda de biblioteca acaba contestada con un horario. De ahí que se pida
    la doble señal en vez de fiarse de la primera persona.
    """
    minusculas = f" {texto.lower().strip()} "

    if any(frase in minusculas for frase in _INEQUIVOCAS):
        return True

    habla_de_si_mismo = any(marca in minusculas for marca in _PRIMERA_PERSONA)
    asunto_personal = any(marca in minusculas for marca in _ASUNTO_PERSONAL)
    return habla_de_si_mismo and asunto_personal


def lo_que_hay_del_personal(
    identidad: object, correo: str, *, tambien_estudia: bool | None = None
) -> str:
    """Respuesta para quien trabaja aquí. Puede que además estudie.

    Se separa de la de estudiante porque lo que interesa es distinto —puesto y
    condición, no clases— y porque el mensaje genérico invitaba a "revisar tu
    matrícula", que para un trabajador no significa nada.

    Args:
        tambien_estudia: Si consta matrícula suya. **Se comprueba contra el
            portal de horarios, no se deduce de la afiliación.** Esa deducción
            era el fallo: MidPoint declara una sola ``primaryAffiliation``, y
            de que diga ``staff`` no se sigue que la persona no estudie. Un
            practicante matriculado recibía "Condición: personal de la
            universidad, no estudiante" y "no te muestro horario porque no
            estás matriculado" — las dos cosas falsas, y sobre él mismo.
            ``None`` cuando no se pudo comprobar: entonces no se afirma nada.

    Lo que **no** está y se dice en voz alta: MidPoint no guarda fechas de
    contrato, vacaciones ni nada de planilla —comprobado el 11-sep-2026 sobre
    la ficha completa—, y la cuenta de servicio que usa GUIA solo alcanza 12
    campos. Decir qué falta es más útil que callarlo, porque si no el usuario
    no sabe si el dato no existe o si GUIA no supo buscarlo.
    """
    nombre = getattr(identidad, "nombre_completo", None)
    lineas = []
    if nombre:
        lineas.append(f"- **Nombre:** {nombre}")
    lineas.append(f"- **Correo institucional:** {correo}")
    for etiqueta, atributo in (
        ("Puesto", "rol"),
        ("Código de trabajador", "codigo"),
        ("Campus", "campus"),
    ):
        valor = getattr(identidad, atributo, None)
        if valor:
            lineas.append(f"- **{etiqueta}:** {valor}")

    unidades = getattr(identidad, "unidades", ()) or ()
    if unidades:
        etiqueta = "Área" if len(unidades) == 1 else "Áreas"
        lineas.append(f"- **{etiqueta}:** {', '.join(unidades)}")

    if tambien_estudia:
        lineas.append(
            "- **Condición:** trabajas en la universidad y además estás "
            "matriculado como estudiante"
        )
    elif tambien_estudia is False:
        lineas.append("- **Condición:** personal de la universidad")

    sobre_las_clases = ""
    if tambien_estudia:
        sobre_las_clases = (
            "\n\nComo también estás matriculado, puedo decirte qué clases "
            "tienes: pregúntame por tu horario."
        )
    elif tambien_estudia is False:
        sobre_las_clases = "\n\nNo me consta ninguna matrícula tuya como estudiante."

    return (
        "Esto es lo que sé de ti:\n\n"
        + "\n".join(lineas)
        + sobre_las_clases
        + "\n\nLo que **no** puedo ver: las fechas de tu contrato ni tus "
        "vacaciones. Eso no está en el directorio institucional —vive en el "
        "sistema de personal— y GUIA aún no lo consulta."
    )
