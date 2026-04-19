"""ChatService — núcleo del asistente GUIA."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sciback_core.ports.llm import LLMMessage, LLMPort

from guia.domain.chat import ChatRequest, ChatResponse, Intent, Source
from guia.services.intent import IntentClassifier

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter

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


def _records_to_context(records: list[VectorRecord]) -> tuple[str, list[Source]]:
    """Convierte VectorRecord en texto de contexto y lista de fuentes."""
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

    Args:
        synthesis_llm: LLM para síntesis de respuesta.
        store: Vector store para búsqueda semántica.
        embedder: E5 para generar embeddings de queries.
        classifier_llm: LLM ligero para clasificación de intents.
        cache: Caché semántico opcional (Redis).
        institution: Nombre de la institución (para el system prompt).
    """

    def __init__(
        self,
        synthesis_llm: LLMPort,
        store: VectorStorePort,
        embedder: E5EmbeddingAdapter,
        *,
        classifier_llm: LLMPort | None = None,
        cache: SemanticCache | None = None,
        institution: str = "la universidad",
    ) -> None:
        self._synthesis_llm = synthesis_llm
        self._store = store
        self._embedder = embedder
        self._classifier = IntentClassifier(classifier_llm or synthesis_llm)
        self._cache = cache
        self._institution = institution

    def answer(self, request: ChatRequest) -> ChatResponse:
        """Genera una respuesta para el ChatRequest del usuario."""
        query = request.query

        # 1. Embed query
        query_vector = self._embedder.embed_query(query)

        # 2. Caché hit
        if self._cache is not None:
            cached = self._cache.get(query, query_vector=query_vector)
            if cached is not None:
                return ChatResponse(
                    answer=cached.answer,
                    intent=cached.intent,
                    sources=cached.sources,
                    model_used=cached.model_used,
                    cached=True,
                    tokens_used=0,
                )

        # 3. Clasificar intent
        intent = request.intent_hint or self._classifier.classify(query)

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
                self._cache.set(query, response, query_vector=query_vector)
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
                self._cache.set(query, response, query_vector=query_vector)
            return response

        # 5. RAG para RESEARCH y GENERAL
        records = self._store.search(query_vector, limit=5, min_score=0.3)
        context_text, sources = _records_to_context(records)

        system = _SYSTEM_PROMPT.format(
            institution=self._institution,
            context=context_text if context_text else "No se encontraron documentos relevantes.",
        )

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=query),
        ]

        llm_response = self._synthesis_llm.complete(
            messages,
            max_tokens=1024,
            temperature=0.1,
        )

        response = ChatResponse(
            answer=llm_response.content,
            intent=intent,
            sources=sources,
            model_used=llm_response.model,
            cached=False,
            tokens_used=llm_response.input_tokens + llm_response.output_tokens,
        )

        if self._cache is not None:
            self._cache.set(query, response, query_vector=query_vector)

        return response
