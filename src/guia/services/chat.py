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

from guia.audit import AuditLogEntry, AuditLogRepository, hash_query
from guia.domain.chat import ChatRequest, ChatResponse, Intent, Source
from guia.routing import CascadeRouter, RouteDecision, Tier, category_to_intent
from guia.services.intent import IntentClassifier
from guia.services.router import ModelRouter, QueryTier

if TYPE_CHECKING:
    from sciback_adapter_koha import KohaAdapter
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
    "Los servicios de campus (notas, matrícula) estarán disponibles "
    "próximamente. Por ahora puedo ayudarte con búsquedas en el repositorio "
    "institucional, publicaciones académicas y el catálogo de la biblioteca."
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
        cascade_router: CascadeRouter | None = None,
        cache: SemanticCache | None = None,
        institution: str = "la universidad",
        search_adapter: SearchAdapter | None = None,
        koha_adapter: KohaAdapter | None = None,
        audit_repo: AuditLogRepository | None = None,
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
        self._search_adapter = search_adapter
        self._koha = koha_adapter
        self._audit_repo = audit_repo

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """Genera una respuesta para el ChatRequest del usuario (async).

        Todas las operaciones bloqueantes se ejecutan en un thread pool
        via asyncio.to_thread() para no bloquear el event loop.
        """
        import time

        t_start = time.perf_counter()
        query = request.query
        route_decision: RouteDecision | None = None  # se setea en paso 3
        sources_used_names: list[str] = []  # ['dspace', 'koha', ...] para audit

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
                response = ChatResponse(
                    answer=cached.answer,
                    intent=cached.intent,
                    sources=cached.sources,
                    model_used=cached.model_used,
                    cached=True,
                    tokens_used=0,
                )
                await self._emit_audit(
                    request, response, route_decision, sources_used_names, t_start
                )
                return response

        # 3. Clasificar intent + tier
        # Si el CascadeRouter está disponible (P1.2), preferirlo: ahorra
        # ~150-300ms en queries triviales que resuelve en Gate 1 o Gate 2.
        # El intent_hint (test override) sigue teniendo precedencia.
        route_decision = None
        if request.intent_hint is not None:
            intent = request.intent_hint
        elif self._cascade is not None:
            route_decision = self._cascade.decide(query, query_vector)
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
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.set, query, response, query_vector=query_vector
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
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.set, query, response, query_vector=query_vector
                )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
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
            sources_used_names.append("opensearch")
        else:
            records = await asyncio.to_thread(
                self._store.search, query_vector, limit=5, min_score=0.3
            )
            context_text, sources = _records_to_context(records)
            if records:
                sources_used_names.append("pgvector")

        # 6. Elegir LLM de síntesis según complejidad de la query.
        # Preferencia: usar el tier de la RouteDecision si CascadeRouter decidió.
        # Caso contrario, fallback al ModelRouter legacy o synthesis_llm directo.
        if route_decision is not None and self._fast_llm is not None:
            # Cascade decidió: T0_FAST → fast_llm; T1_STD/T2_DEEP → synthesis_llm
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

        # 7. Síntesis LLM (sync → thread)
        system = _SYSTEM_PROMPT.format(
            institution=self._institution,
            context=context_text if context_text else "No se encontraron documentos relevantes.",
        )
        messages = [LLMMessage(role="system", content=system)]
        for turn in request.history:
            messages.append(LLMMessage(role=turn.role, content=turn.content))
        messages.append(LLMMessage(role="user", content=query))
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

        await self._emit_audit(
            request, response, route_decision, sources_used_names, t_start
        )
        return response

    async def _emit_audit(
        self,
        request: ChatRequest,
        response: ChatResponse,
        route_decision: RouteDecision | None,
        sources_used: list[str],
        t_start: float,
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
        privacy_level = (
            route_decision.privacy.value if route_decision is not None else "cloud_ok"
        )
        gate_used = (
            route_decision.gate_used.value if route_decision is not None else "unknown"
        )

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
            latency_ms=latency_ms,
            cached=response.cached,
        )
        try:
            await self._audit_repo.record(entry)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("audit_emit_failed", exc_info=True)
