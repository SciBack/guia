"""IntentClassifier — clasifica la intención del usuario.

M4: classify() es async, usa asyncio.to_thread() para no bloquear el event loop.
"""

from __future__ import annotations

import asyncio

from sciback_core.ports.llm import LLMMessage, LLMPort

from guia.domain.chat import Intent

_SYSTEM_PROMPT = """\
Eres un clasificador de intenciones para el asistente universitario GUIA.
Dado el mensaje del usuario, responde ÚNICAMENTE con una de estas palabras:
research, campus, general, out_of_scope

- research: buscar libros, buscar en la biblioteca, catálogo bibliográfico, préstamos de libros, \
investigación, tesis, artículos, publicaciones, repositorio, revistas académicas, \
autores, ISBN, referencias bibliográficas.
- campus: notas, calificaciones, matrícula, pagos, horarios, aulas, servicios administrativos, \
trámites, constancias, carnet, servicios de campus NO relacionados con libros.
- general: consultas generales sobre la universidad, facultades, procesos académicos.
- out_of_scope: consultas fuera del ámbito universitario institucional.

Responde solo la palabra, sin puntuación ni explicación."""

_INTENT_MAP: dict[str, Intent] = {
    "research": Intent.RESEARCH,
    "campus": Intent.CAMPUS,
    "general": Intent.GENERAL,
    "out_of_scope": Intent.OUT_OF_SCOPE,
}


class IntentClassifier:
    """Clasifica la intención del usuario usando un LLM.

    M4: classify() es async — usa asyncio.to_thread() para el LLM sync.
    Diseñado para usar un modelo ligero (Qwen 2.5 3B) en LOCAL/HYBRID.

    Args:
        llm: Implementación de LLMPort.
    """

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def classify(self, query: str) -> Intent:
        """Clasifica la intención de la query (async).

        Args:
            query: Texto del usuario.

        Returns:
            Intent detectado. Retorna GENERAL si el LLM responde algo inesperado.
        """
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=query.strip()),
        ]
        response = await asyncio.to_thread(
            self._llm.complete, messages, max_tokens=10, temperature=0.0
        )
        raw = response.content.strip().lower().rstrip(".,;")
        return _INTENT_MAP.get(raw, Intent.GENERAL)

    def classify_sync(self, query: str) -> Intent:
        """Versión sync — solo para contextos sin event loop (tests, Celery)."""
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=query.strip()),
        ]
        response = self._llm.complete(messages, max_tokens=10, temperature=0.0)
        raw = response.content.strip().lower().rstrip(".,;")
        return _INTENT_MAP.get(raw, Intent.GENERAL)
