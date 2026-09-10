"""Qué decir sobre los resultados, además de listarlos.

Cuando la respuesta era un listado, GUIA no llamaba al modelo: enviaba
"Encontré 5 resultados relacionados con tu consulta" y debajo los enlaces. La
decisión estaba medida y tenía dos motivos buenos, anotados el 08-sep-2026:

1. El canal sustituía la prosa por el render con enlaces, así que sintetizar
   era pagar la espera por un texto que se tiraba — entre 48 y 107 segundos en
   las consultas más frecuentes del piloto.
2. Esa prosa repetía los títulos uno a uno, sin enlace. Duplicaba el listado y
   además peor.

Los dos motivos se caen si el modelo escribe **otra cosa**. El listado ya dice
qué salió; lo que falta es lo que haría alguien en el mostrador de la
biblioteca: decir qué clase de material es, cuál sirve para qué, y avisar
cuando lo encontrado no es exactamente lo que se pidió. Eso no compite con los
enlaces, va encima de ellos.

Y los 48-107 segundos eran del modelo del Mac Mini a 13 tokens/s. Medido el
10-sep-2026 con Claude, esto son 2,4-2,7 s, que además se emiten por
fragmentos: el texto empieza a aparecer mucho antes de estar terminado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sciback_core.ports.llm import LLMMessage

from guia.domain.chat import Source
from guia.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

_SYSTEM = """\
Eres GUIA, el asistente de la biblioteca de la Universidad Peruana Unión.

El usuario verá DEBAJO de tu texto la lista de resultados, cada uno con su
enlace. Escribe 2 o 3 frases que le ayuden a usarla.

NO repitas los títulos: ya los va a ver, y con enlace. Di qué clase de material
salió y para qué le sirve. Si algo no encaja con lo que pidió, dilo y sugiere
cómo afinar la búsqueda — es más útil que fingir que todo vale.

NO te refieras a los resultados por su número ("el número 5"): el usuario los
verá agrupados por fuente y en otro orden. Para señalar uno, descríbelo en
tres o cuatro palabras: "la tesis sobre estrés académico".

Español de Perú, tuteando: "tienes", "puedes". Nunca vosees: ni "tenés" ni
"podés". Sin saludos ni preámbulos. Prosa corrida: nada de listas ni viñetas.
Dos o tres frases; no te alargues."""


def _resumen_de_fuentes(sources: list[Source]) -> str:
    """Los resultados en texto plano, para que el modelo sepa qué hay.

    Va el tipo, el año y el título. El título es lo único que puede tentarle a
    repetirse, pero sin él no puede decir si lo encontrado encaja o no, que es
    justo lo que se le pide; el prompt se encarga de que no los liste.
    """
    lineas: list[str] = []
    for i, s in enumerate(sources[:10], 1):
        partes = [s.title]
        if s.source_type:
            partes.append(s.source_type)
        if s.year:
            partes.append(str(s.year))
        lineas.append(f"{i}. {' · '.join(str(p) for p in partes)}")
    return "\n".join(lineas)


def mensajes_de_orientacion(query: str, sources: list[Source]) -> list[LLMMessage]:
    """El prompt para orientar sobre estos resultados."""
    return [
        LLMMessage(role="system", content=_SYSTEM),
        LLMMessage(
            role="user",
            content=f"Consulta: {query}\n\nResultados:\n{_resumen_de_fuentes(sources)}",
        ),
    ]


async def orientar(
    llm: object,
    query: str,
    sources: list[Source],
    *,
    de_reserva: str,
    stream: Callable[[list[LLMMessage], Callable[[str], Awaitable[None]]], Awaitable[object]]
    | None = None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Texto que acompaña al listado; ``de_reserva`` si el modelo no responde.

    Args:
        llm: El modelo de síntesis.
        query: Lo que preguntó el usuario.
        sources: Los resultados que va a ver.
        de_reserva: Qué enviar si esto falla. Es el encabezado de siempre —un
            listado sin una línea encima sigue siendo una respuesta útil, así
            que aquí no se rompe nada, solo se pierde la orientación.
        stream: El emisor por fragmentos del ChatService, si hay a quién
            emitir.
        on_token: Dónde emitirlos.
    """
    mensajes = mensajes_de_orientacion(query, sources)

    try:
        if stream is not None and on_token is not None:
            respuesta = await stream(mensajes, on_token)
            texto = getattr(respuesta, "content", "") or ""
        else:
            import asyncio

            respuesta = await asyncio.to_thread(llm.complete, mensajes, max_tokens=160)  # type: ignore[attr-defined]
            texto = respuesta.content or ""
    except Exception as exc:
        logger.warning("orientacion_no_disponible", error=str(exc))
        return de_reserva

    texto = texto.strip()
    if len(texto) < 20:
        logger.warning("orientacion_demasiado_corta", texto=texto[:60])
        return de_reserva

    return texto
