"""ChatService — núcleo del asistente GUIA.

M4: answer() es async end-to-end.
    - embed_query, store.search, llm.complete → asyncio.to_thread() (son sync)
    - search_adapter.hybrid_dicts() → await directo (async nativo)
    - cache.get / cache.set → asyncio.to_thread() (Redis sync, rápido)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sciback_core.ports.llm import LLMMessage, LLMPort

from guia.domain.chat import ChatRequest, ChatResponse, Intent, Source
from guia.services.intent import IntentClassifier
from guia.services.router import ModelRouter, QueryTier

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter

    from guia.search.backend import SearchAdapter
    from guia.services.cache import SemanticCache

_SYSTEM_PROMPT = """\
Eres GUIA, el asistente universitario de {institution}. Ayudas a estudiantes,
docentes e investigadores a encontrar información académica e institucional.

Responde en español de manera clara y concisa. Cita las fuentes cuando sea relevante.
Si no encuentras información suficiente en el contexto, indícalo honestamente.
No inventes datos ni referencias.

Contexto de documentos relevantes:
{context}"""

_CAMPUS_UNAVAILABLE = (
    "Los servicios de campus (biblioteca, notas, matrícula) estarán disponibles "
    "próximamente. Por ahora puedo ayudarte con búsquedas en el repositorio "
    "institucional y publicaciones académicas."
)

_OUT_OF_SCOPE = (
    "Esa consulta está fuera de mi alcance como asistente universitario. "
    "Puedo ayudarte con información académica, investigación y servicios "
    "institucionales de la universidad."
)


def _hits_to_context(hits: list[dict[str, Any]]) -> tuple[str, list[Source]]:
    """Convierte hits de OpenSearch/pgvector a texto de contexto y fuentes."""
    sources: list[Source] = []
    lines: list[str] = []

    for i, hit in enumerate(hits, 1):
        title = str(hit.get("title", f"Documento {i}"))
        abstract = str(hit.get("abstract", ""))
        authors = hit.get("authors", [])
        year = hit.get("year")
        url = hit.get("url")

        lines.append(f"[{i}] {title}")
        if abstract:
            lines.append(f"    {abstract[:300]}...")
        lines.append("")

        sources.append(
            Source(
                id=str(hit.get("id", str(i))),
                title=title,
                url=str(url) if url else None,
                authors=[str(a) for a in authors] if isinstance(authors, list) else [],
                year=int(year) if year else None,
                score=float(hit.get("score", 0.0)),
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
        cache: SemanticCache | None = None,
        institution: str = "la universidad",
        search_adapter: SearchAdapter | None = None,
    ) -> None:
        self._synthesis_llm = synthesis_llm
        self._fast_llm = fast_llm
        self._router = router
        self._store = store
        self._embedder = embedder
        self._classifier = IntentClassifier(classifier_llm or synthesis_llm)
        self._cache = cache
        self._institution = institution
        self._search_adapter = search_adapter

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """Genera una respuesta para el ChatRequest del usuario (async).

        Todas las operaciones bloqueantes se ejecutan en un thread pool
        via asyncio.to_thread() para no bloquear el event loop.
        """
        query = request.query

        # 1. Embed query (sync HTTP → thread)
        query_vector: list[float] = await asyncio.to_thread(
            self._embedder.embed_query, query
        )

        # 2. Caché hit (sync Redis → thread)
        if self._cache is not None:
            cached = await asyncio.to_thread(
                self._cache.get, query, query_vector=query_vector
            )
            if cached is not None:
                return ChatResponse(
                    answer=cached.answer,
                    intent=cached.intent,
                    sources=cached.sources,
                    model_used=cached.model_used,
                    cached=True,
                    tokens_used=0,
                )

        # 3. Clasificar intent (async — LLM en thread)
        intent = request.intent_hint or await self._classifier.classify(query)

        # 4. Respuestas directas sin RAG
        if intent == Intent.OUT_OF_SCOPE:
            response = ChatResponse(
                answer=_OUT_OF_SCOPE,
                intent=intent,
                sources=[],
                model_used="none",
                cached=False,
            )
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.set, query, response, query_vector=query_vector
                )
            return response

        if intent == Intent.CAMPUS:
            response = ChatResponse(
                answer=_CAMPUS_UNAVAILABLE,
                intent=intent,
                sources=[],
                model_used="none",
                cached=False,
            )
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.set, query, response, query_vector=query_vector
                )
            return response

        # 5. RAG: OpenSearch hybrid async o pgvector en thread
        if self._search_adapter is not None:
            # M4: await directo, sin asyncio.run() bridge
            hits = await self._search_adapter.hybrid_dicts(
                text=query,
                vector=query_vector,
                limit=5,
            )
            context_text, sources = _hits_to_context(hits)
        else:
            records = await asyncio.to_thread(
                self._store.search, query_vector, limit=5, min_score=0.3
            )
            context_text, sources = _records_to_context(records)

        # 6. Elegir LLM de síntesis según complejidad de la query
        # RESEARCH siempre usa el modelo completo (RAG + razonamiento complejo).
        # GENERAL: el router decide según similitud semántica — reutiliza query_vector.
        if (
            intent != Intent.RESEARCH
            and self._fast_llm is not None
            and self._router is not None
            and self._router.ready
        ):
            tier = self._router.route(query_vector)
            synthesis_llm = self._fast_llm if tier == QueryTier.FAST else self._synthesis_llm
        else:
            synthesis_llm = self._synthesis_llm

        # 7. Síntesis LLM (sync → thread)
        system = _SYSTEM_PROMPT.format(
            institution=self._institution,
            context=context_text if context_text else "No se encontraron documentos relevantes.",
        )
        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=query),
        ]
        llm_response = await asyncio.to_thread(
            synthesis_llm.complete, messages, max_tokens=1024, temperature=0.1
        )

        response = ChatResponse(
            answer=llm_response.content,
            intent=intent,
            sources=sources,
            model_used=llm_response.model,
            cached=False,
            tokens_used=llm_response.input_tokens + llm_response.output_tokens,
        )

        # 8. Guardar en caché (sync Redis → thread)
        if self._cache is not None:
            await asyncio.to_thread(
                self._cache.set, query, response, query_vector=query_vector
            )

        return response
