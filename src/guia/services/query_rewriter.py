"""Query rewriter — pipeline NLP híbrido (ADR-044).

Reescribe queries del usuario aplicando herramientas deterministas
especializadas. fast_llm solo se invoca cuando hay ambigüedad o
referencias al historial que requieren razonamiento.

~90% de las queries no invocan LLM. Latencia p50 < 15ms.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from guia.logging import get_logger
from guia.nlp.greetings import strip_greetings
from guia.nlp.acronyms import expand_acronyms
from guia.nlp.dater import extract_date_filters
from guia.nlp.ner import extract_entities
from guia.nlp.keywords import expand_keywords

_log = get_logger(__name__)

if TYPE_CHECKING:
    from sciback_core.ports.llm import LLMPort

_REFERENCE_MARKERS = frozenset({
    "anterior", "anteriores", "siguiente", "siguientes",
    "esos", "esas", "ese", "esa", "aquel", "aquella", "aquellos", "aquellas",
    "los del", "las del", "el del", "la del",
    "los mismos", "las mismas",
    "el mismo", "la misma",
    "los anteriores", "las anteriores",
    "mencionado", "mencionada", "mencionados", "mencionadas",
    "dicho", "dicha", "dichos", "dichas",
})


@dataclass(frozen=True)
class RewriteResult:
    """Resultado del pipeline de reescritura de query."""

    original: str
    cleaned: str
    date_filters: dict | None = None
    entity_filters: dict[str, list[str]] = field(default_factory=dict)
    is_search_query: bool = True
    used_llm: bool = False
    expanded_keywords: list[str] = field(default_factory=list)


class QueryRewriter:
    """Pipeline determinista + fast_llm fallback para preprocesamiento de queries.

    Integra: spell check → date extraction → NER → greeting strip →
             acronym expansion → LLM fallback (solo si hay anáforas).
    """

    def __init__(
        self,
        fast_llm: "LLMPort | None" = None,
        *,
        enable_llm_fallback: bool = True,
        max_history_turns: int = 4,
    ) -> None:
        self._fast_llm = fast_llm
        self._enable_llm_fallback = enable_llm_fallback
        self._max_history_turns = max_history_turns

    async def rewrite(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> RewriteResult:
        """Aplica el pipeline NLP a la query del usuario."""
        if not query or not query.strip():
            return RewriteResult(original=query, cleaned="", is_search_query=False)

        # 1. Spell fix (sync, <1ms si hay diccionario)
        try:
            from guia.nlp.speller import correct_typos
            corrected = await asyncio.to_thread(correct_typos, query)
        except Exception:
            _log.debug("speller_failed", exc_info=True)
            corrected = query

        # 2. Date extraction
        date_filters = extract_date_filters(corrected)

        # 3. NER
        entities = await asyncio.to_thread(extract_entities, corrected)

        # 4. Strip saludos y cortesías
        cleaned = strip_greetings(corrected)

        # 5. Expand siglas académicas
        cleaned = expand_acronyms(cleaned)

        # 6. ¿Solo cortesía? (query vacía tras strip)
        if not cleaned.strip():
            return RewriteResult(
                original=query,
                cleaned=query,
                is_search_query=False,
            )

        # 7. ¿Necesita LLM para resolver anáfora con historial?
        needs_llm = self._needs_llm_resolution(cleaned, history)
        used_llm = False
        if needs_llm and self._enable_llm_fallback and self._fast_llm is not None:
            try:
                cleaned = await self._resolve_with_llm(cleaned, history)
                used_llm = True
            except Exception:
                _log.debug("llm_anaphora_failed", exc_info=True)

        return RewriteResult(
            original=query,
            cleaned=cleaned.strip(),
            date_filters=date_filters,
            entity_filters=entities,
            is_search_query=True,
            used_llm=used_llm,
        )

    async def expand_on_zero_hits(self, cleaned: str) -> list[str]:
        """Expande keywords con YAKE cuando el retriever devuelve 0 hits."""
        try:
            return await asyncio.to_thread(expand_keywords, cleaned)
        except Exception:
            return []

    def _needs_llm_resolution(
        self,
        cleaned: str,
        history: list[dict] | None,
    ) -> bool:
        if not history:
            return False
        cleaned_lower = cleaned.lower()
        return any(marker in cleaned_lower for marker in _REFERENCE_MARKERS)

    async def _resolve_with_llm(
        self,
        cleaned: str,
        history: list[dict] | None,
    ) -> str:
        from sciback_core.ports.llm import LLMMessage

        recent = (history or [])[-self._max_history_turns * 2:]
        history_text = "\n".join(
            f"{turn.get('role', 'user').capitalize()}: {turn.get('content', '')}"
            for turn in recent
        )

        prompt = f"""Eres un asistente de reformulación de queries. Tu tarea es SOLO reescribir la query del usuario para que sea independiente del historial de conversación, expandiendo las referencias implícitas.

Historial reciente:
{history_text}

Query con referencia implícita: "{cleaned}"

Reescribe la query como una búsqueda completa y autocontenida en español. Responde SOLO con la query reescrita, sin explicaciones ni comillas."""

        messages = [LLMMessage(role="user", content=prompt)]
        result = await asyncio.to_thread(
            self._fast_llm.complete, messages, max_tokens=128, temperature=0.0
        )
        rewritten = result.content.strip().strip('"\'')
        return rewritten if rewritten else cleaned
