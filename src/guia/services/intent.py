"""IntentClassifier — clasifica la intención del usuario.

Usa el LLMPort (Qwen 2.5 3B en modo LOCAL/HYBRID, Claude en CLOUD) para
mapear el texto de la consulta a uno de los 4 intents definidos.
"""

from __future__ import annotations

from sciback_core.ports.llm import LLMMessage, LLMPort

from guia.domain.chat import Intent

_SYSTEM_PROMPT = """\
Eres un clasificador de intenciones para el asistente universitario GUIA.
Dado el mensaje del usuario, responde ÚNICAMENTE con una de estas palabras:
research, campus, general, out_of_scope

- research: consultas sobre investigación, tesis, artículos, publicaciones, repositorio.
- campus: consultas sobre biblioteca, notas, matrícula, pagos, horarios, servicios.
- general: consultas generales sobre la universidad que no son research ni campus.
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

    Diseñado para usar un modelo ligero (Qwen 2.5 3B) en modo LOCAL/HYBRID
    para minimizar latencia y costo. En modo CLOUD usa el mismo LLM principal.

    Args:
        llm: Implementación de LLMPort.
    """

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def classify(self, query: str) -> Intent:
        """Clasifica la intención de la query.

        Args:
            query: Texto del usuario.

        Returns:
            Intent detectado. Retorna GENERAL si el LLM responde algo inesperado.
        """
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=query.strip()),
        ]
        response = self._llm.complete(messages, max_tokens=10, temperature=0.0)
        raw = response.content.strip().lower().rstrip(".,;")
        return _INTENT_MAP.get(raw, Intent.GENERAL)
