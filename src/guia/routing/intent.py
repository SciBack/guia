"""LLMIntentCategoryClassifier — Gate 3 de la cascada (P1.2 paso 4c).

Implementación concreta del Protocol IntentLLMClassifier definido en
cascade.py. Solo se invoca cuando Gate 2 (embedding similarity) tiene
confidence < threshold (~ambiguo entre múltiples centroides).

Diseño:
- Prompt corto y determinístico que lista las 8 categorías de IntentCategory
- LLM responde con UNA de esas categorías exactas
- Parsing case-insensitive con normalización
- Fallback a IntentCategory.UNKNOWN si respuesta no reconocida
- Latencia ~150-300ms con qwen2.5:3b local

Mantiene la API del Protocol (sync), corre en thread pool desde el
CascadeRouter.decide() que sí está en contexto async.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from guia.routing.decision import IntentCategory

if TYPE_CHECKING:
    from sciback_core.ports.llm import LLMPort

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
Eres un clasificador de intents para GUIA, asistente universitario UPeU.

Clasifica la siguiente consulta del usuario en UNA categoría exacta:

- greeting: saludos y meta-preguntas sobre el asistente (hola, gracias, quién
    eres, qué puedes hacer, cómo te llamas, qué fuentes tienes).
- command: comandos directos del sistema (/help, /reset, /lang).
- campus_personal: datos personales del USUARIO (mis notas, mi deuda, mi
    promedio, mis préstamos, mi horario, mi correo institucional).
- campus_generico: información institucional administrativa (calendario
    académico, eventos, reglamentos, becas, ubicaciones, titulación).
- research_simple: cualquier consulta sobre un TEMA académico, científico,
    educativo, profesional o cultural. Esto incluye:
    - Búsquedas explícitas: "tesis sobre X", "libros de Y", "artículos de Z"
    - Temas sueltos (1-5 palabras): "nutrición infantil", "machine learning",
      "filosofía", "ética profesional", "energías renovables"
    - Preguntas de conocimiento sobre cualquier campo: "qué es la mitosis",
      "cómo funciona blockchain", "historia del Perú"
    - Áreas de estudio o disciplinas mencionadas sin más contexto
    Cualquier sustantivo o frase nominal que pueda corresponder a un libro,
    artículo, tesis o material académico → research_simple.
- research_deep: análisis profundo o síntesis explícita de múltiples
    documentos (comparar metodologías, análisis bibliométrico, marco teórico,
    estado del arte, evolución temporal, redes de colaboración).
- out_of_scope: SOLO cosas claramente NO académicas y NO institucionales:
    chistes, deportes, farándula, política diaria, tareas personales sin
    contexto educativo, contenido inapropiado.
- unknown: no se entiende qué pide el usuario.

REGLA CRÍTICA: ante la duda entre research_simple y out_of_scope, elige
research_simple. El costo de buscar un tema sin resultados es mínimo; el
costo de rechazar una consulta válida es alto.

EJEMPLOS:
- "nutrición en la niñez" → research_simple (es un tema académico)
- "algo de filosofía" → research_simple (área de estudio)
- "cuál es la capital de Francia" → research_simple (conocimiento general)
- "chistes de Pepito" → out_of_scope
- "quién ganó el partido de ayer" → out_of_scope
- "mis notas del semestre" → campus_personal
- "calendario de matrícula" → campus_generico

Responde SOLO con el código exacto de la categoría en minúsculas, sin
puntuación ni explicación.
"""


_CATEGORY_MAP: dict[str, IntentCategory] = {
    "greeting": IntentCategory.GREETING,
    "command": IntentCategory.COMMAND,
    "campus_personal": IntentCategory.CAMPUS_PERSONAL,
    "campus_generico": IntentCategory.CAMPUS_GENERICO,
    "campus_genérico": IntentCategory.CAMPUS_GENERICO,  # tolerancia tilde
    "research_simple": IntentCategory.RESEARCH_SIMPLE,
    "research_deep": IntentCategory.RESEARCH_DEEP,
    "out_of_scope": IntentCategory.OUT_OF_SCOPE,
    "unknown": IntentCategory.UNKNOWN,
}


class LLMIntentCategoryClassifier:
    """Gate 3 — clasificador LLM en 8 categorías (IntentCategory).

    Args:
        llm: Implementación de LLMPort (típicamente Qwen 2.5 3B local).
        max_tokens: Tokens máximos para la respuesta. 10 es suficiente
            para una sola palabra-categoría. Default 10.
        temperature: 0.0 para máxima determinismo (clasificación).
    """

    def __init__(
        self,
        llm: LLMPort,
        *,
        max_tokens: int = 10,
        temperature: float = 0.0,
    ) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self._temperature = temperature

    def classify_category(self, query: str) -> IntentCategory:
        """Clasifica la query en una IntentCategory.

        Implementa el Protocol IntentLLMClassifier que CascadeRouter usa
        en su Gate 3. Llama al LLM síncrono — el caller (CascadeRouter
        async) ya envuelve esto en thread pool.

        Si el LLM responde algo no reconocido, retorna UNKNOWN para
        que la cascada caiga al fallback conservador.
        """
        from sciback_core.ports.llm import LLMMessage

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=query.strip()),
        ]
        try:
            response = self._llm.complete(
                messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:
            logger.warning("gate3_llm_classify_failed", extra={"exc": str(exc)})
            return IntentCategory.UNKNOWN

        raw = response.content.strip().lower().rstrip(".,;:")
        # Algunos LLMs envuelven con espacios o agregan prefijos como "category: "
        for token in raw.replace(":", " ").split():
            cleaned = token.strip().rstrip(".,;:")
            if cleaned in _CATEGORY_MAP:
                return _CATEGORY_MAP[cleaned]

        logger.info(
            "gate3_unrecognized_category",
            extra={"raw_response": raw[:80]},
        )
        return IntentCategory.UNKNOWN
