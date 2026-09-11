"""Cuando la lista de palabras no sabe, que decida el modelo.

Por qué existe. GUIA tenía una lista de palabras para saber si una consulta
decía sobre qué buscar. Falló dos días seguidos con la misma pregunta escrita
de dos formas: "estoy buscando algo para mi tesis" (09-sep-2026) y "me puedes
ayudar en mi investigación?" (10-sep). La segunda se coló porque la lista tenía
"ayuda" y "ayudame", pero no "ayudar". Se arregló con familias por prefijo, y
esa sigue siendo la parte barata — pero adivinar de antemano cómo escribe la
gente es perder a plazo: siempre queda una forma más.

Entender qué pide alguien es justo lo que un modelo hace bien. Aquí se le
pregunta a él, siguiendo la cascada por coste que ya usa el router (reglas →
embeddings → LLM):

1. Si al vaciar la frase no queda ninguna palabra de contenido, no hay tema y
   se sabe sin preguntar a nadie. 0 ms.
2. Si no hay ninguna palabra de petición, es un tema dicho directamente
   —"contaminación del lago Titicaca"— y se busca. 0 ms.
3. Lo que queda es la zona gris: pide algo Y nombra cosas. Ahí decide el
   modelo. Medido sobre 21 consultas reales, cae aquí el 38%.

Qué modelo, y por qué no el rápido. Se midieron los dos contra las mismas 21
consultas el 10-sep-2026:

    ollama (Mac Mini)   18/22 en 0,09 s — decía FALTA a "necesito artículos de
                        energías renovables", que es una consulta normal
    claude              21/22 en 0,83 s

El barato se equivocaba en la dirección cara: preguntar el tema a quien ya lo
había dicho. Como solo se invoca en la zona gris, Claude sale a 0,44 s de
media, y las consultas que ya nombran su tema no pagan nada.

Y responde él. Antes había un texto fijo pidiendo el tema; ahora la repregunta
la escribe el mismo modelo, que ha leído lo que la persona escribió y puede
recoger lo que sí entendió. El texto fijo sigue ahí como red de seguridad para
cuando el modelo no conteste, que es lo que debe ser una plantilla: el plan B.
"""

from __future__ import annotations

import asyncio
import unicodedata

from sciback_core.ports.llm import LLMMessage, LLMPort

from guia.logging import get_logger

logger = get_logger(__name__)

#: Marca de que la consulta ya trae su tema. El modelo responde esto y nada más.
_HAY_TEMA = "TEMA"

_SYSTEM = """\
Eres GUIA, el asistente de la Universidad Peruana Unión. Conoces el catálogo
de la biblioteca, las tesis del repositorio, la producción científica, los
artículos de las revistas UPeU, los eventos académicos y la propia
universidad: qué áreas tiene y de qué responde cada una.

Tu única tarea ahora: decidir si el mensaje dice SOBRE QUÉ TEMA buscar.

Si lo dice, responde exactamente: TEMA
Un tema es la materia, el asunto, un autor, un lugar o una cosa concreta.
También lo es un área o un proceso de la universidad: "qué áreas hay",
"de qué se encarga la DTI" o "quién lleva la matrícula" ya dicen sobre qué,
y no hay que preguntar nada más.
"con estadística inferencial", "sobre la quinua" o "Ellen White" son temas,
aunque la frase empiece pidiendo ayuda.

Si NO lo dice, no respondas TEMA: escríbele directamente en español, tuteando,
en dos frases como mucho. Recoge lo que sí entendiste de su mensaje y
pregúntale de qué trata lo que busca. Sin saludos ni preámbulos.

Los formatos no son temas, son el envase: libro, tesis, artículo, paper,
investigación, material, bibliografía, información, tarea, trabajo. Pedir
ayuda tampoco es un tema."""


#: Verbos y sustantivos con los que se pide algo. Distinto del vaciado de
#: ``_sin_tema``: aquí no entran "por", "favor", "gracias" ni "hola", porque
#: son cortesía y no convierten una consulta en petición — con ellos dentro,
#: "¿qué es la kiwicha y por qué es importante?" acababa consultando al modelo
#: por culpa del "por".
_PIDE_ALGO = frozenset("""
busco buscando buscar quiero quisiera necesito necesitaba deseo dame
ayuda ayudame ayudarme apoyo recomienda recomiendame recomendacion sugiere
sugerencia informacion info material materiales recurso recursos
bibliografia fuente fuentes documento documentos libro libros
tesis tesina articulo articulos paper papers publicacion publicaciones
trabajo trabajos investigacion investigaciones estudio estudios
tarea tareas monografia monografias ensayo ensayos informe informes
tienes tiene hay dispones consulta pregunta duda
""".split())


def hay_peticion(query: str) -> bool:
    """¿La frase pide algo, en vez de nombrar un tema a secas?

    Sirve para no molestar al modelo con consultas que claramente ya traen su
    tema: "contaminación del lago Titicaca" no pide nada, nombra algo.
    """
    from guia.services.chat import _FAMILIAS_DE_PETICION

    texto = unicodedata.normalize("NFKD", query.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    for palabra in (p.strip(".,;:¿?¡!()\"'") for p in texto.split()):
        if palabra in _PIDE_ALGO or palabra.startswith(_FAMILIAS_DE_PETICION):
            return True
    return False


class LectorDePeticion:
    """Le pregunta al modelo si la consulta dice sobre qué buscar.

    Args:
        llm: El modelo que decide. Se le pasa el de síntesis a propósito —ver
            la medición en el docstring del módulo—, no el rápido.
        timeout: Techo. Si el modelo tarda más, se sigue como si hubiera tema:
            buscar de más es recuperable, dejar a alguien esperando no.
    """

    def __init__(self, llm: LLMPort, *, timeout: float = 4.0) -> None:
        self._llm = llm
        self._timeout = timeout

    async def que_le_falta(self, query: str) -> str | None:
        """``None`` si la consulta ya trae su tema; si no, qué preguntarle.

        Returns:
            ``None`` cuando hay tema —se busca y ya—, o el texto que el modelo
            ha escrito para pedirle el tema, listo para enviar tal cual.
        """
        mensajes = [
            LLMMessage(role="system", content=_SYSTEM),
            LLMMessage(role="user", content=query.strip()),
        ]
        try:
            respuesta = await asyncio.wait_for(
                asyncio.to_thread(self._llm.complete, mensajes, max_tokens=120),
                timeout=self._timeout,
            )
        except Exception as exc:  # incluye TimeoutError
            # Degrada hacia buscar, no hacia preguntar: si el modelo no está,
            # es mejor dar resultados imperfectos que dejar la consulta sin
            # respuesta esperando a un servicio caído.
            logger.warning("lector_de_peticion_no_responde", error=str(exc))
            return None

        texto = (respuesta.content or "").strip()

        if texto.upper().startswith(_HAY_TEMA):
            return None

        if len(texto) < 15:
            # Una respuesta demasiado corta no es una pregunta al usuario; es
            # el modelo saliéndose del formato. Se prefiere buscar.
            logger.warning("lector_de_peticion_respuesta_rara", texto=texto[:60])
            return None

        return texto
