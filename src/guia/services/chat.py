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
from sciback_privacy import PrivacyRouter, PrivacyVerdict, redact, restore
from guia.routing import CascadeRouter, IntentCategory, RouteDecision, Tier, category_to_intent
from guia.services.intent import IntentClassifier
from guia.services.router import ModelRouter, QueryTier

if TYPE_CHECKING:
    from sciback_adapter_koha import KohaAdapter
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter

    from guia.search.backend import SearchAdapter
    from guia.services.cache import SemanticCache
    from guia.routing.gates import LanguageGate, ToxicityGate
    from guia.services.query_rewriter import QueryRewriter

_DEFAULT_SOURCES_INVENTORY = """\
FUENTES ACTUALMENTE DISPONIBLES (las únicas que puedes consultar):
- Koha UPeU — catálogo de la biblioteca, ~34,985 libros físicos indexados
  (puedes buscar libros, autores, materias y disponibilidad de ejemplares).
- OJS revistas.upeu.edu.pe — ~744 artículos científicos publicados por la UPeU.

FUENTES NO DISPONIBLES AÚN (NO las menciones como si las tuvieras):
- DSpace repositorio.upeu.edu.pe — bloqueado, sin acceso desde el servidor.
- ALICIA / RENATI — pendiente de integración."""


_SYSTEM_PROMPT = """\
Eres GUIA, el asistente universitario de {institution}.

# Identidad y tono
Ya te presentaste al inicio de la conversación. NO te vuelvas a presentar ni
saludes de nuevo en cada turno. Continúa la conversación de forma natural,
manteniendo el contexto de los mensajes anteriores. Solo saluda si el usuario
inicia un mensaje con un saludo explícito ("hola", "buenos días", etc.).

Responde en español, claro y conciso. No expliques lo obvio. Adapta el tono al
del usuario (formal/informal). Cita las fuentes cuando uses información del
contexto recuperado.

# Fuentes que tienes indexadas y puedes consultar
{sources_inventory}

Cuando el usuario pregunte qué puedes hacer o qué fuentes tienes, responde con
este inventario real — NO digas "no sé" ni "consulta a la biblioteca". Eres tú
quien tiene acceso a esas fuentes.

# Cómo razonar sobre el contexto recuperado
El sistema te entrega abajo los documentos más relevantes para la consulta del
usuario, recuperados por búsqueda híbrida (semántica + léxica) sobre el índice.

- Si hay documentos relevantes: respóndele al usuario citando títulos/autores y
  resumiendo lo que encontraste.
- Si NO hay documentos relevantes (contexto vacío o irrelevante):
  1. NUNCA digas "ve a la biblioteca" o "contacta al servicio de referencia" —
     tú eres ese servicio.
  2. Reconoce que esa búsqueda específica no devolvió resultados.
  3. Sugiere reformular con sinónimos o términos relacionados (ej. "excel" →
     "Microsoft Excel", "hojas de cálculo", "ofimática"; "IA" → "inteligencia
     artificial", "machine learning", "aprendizaje automático").
  4. Ofrece intentar la búsqueda con esos términos alternativos.

No inventes datos, autores ni referencias que no estén en el contexto.

# Contexto recuperado para esta consulta
{context}"""

_CAMPUS_UNAVAILABLE = (
    "Los servicios de campus (notas, matrícula, horarios) aún no están disponibles. "
    "Por ahora puedo ayudarte con el catálogo de la biblioteca Koha (~34,985 libros) "
    "y artículos de las revistas académicas OJS de UPeU (~744 artículos)."
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
        sources_inventory: str | None = None,
        search_adapter: SearchAdapter | None = None,
        koha_adapter: KohaAdapter | None = None,
        audit_repo: AuditLogRepository | None = None,
        privacy_router: PrivacyRouter | None = None,
        query_rewriter: "QueryRewriter | None" = None,
        language_gate: "LanguageGate | None" = None,
        toxicity_gate: "ToxicityGate | None" = None,
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
        self._sources_inventory = sources_inventory or _DEFAULT_SOURCES_INVENTORY
        self._search_adapter = search_adapter
        self._koha = koha_adapter
        self._audit_repo = audit_repo
        # P2.2: PrivacyRouter — si no se inyecta, se construye uno por default.
        # Es stateless y barato (regex + tabla lookup), no tiene sentido tenerlo opcional.
        self._privacy_router = privacy_router or PrivacyRouter()
        self._query_rewriter = query_rewriter
        self._language_gate = language_gate
        self._toxicity_gate = toxicity_gate

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
        privacy_verdict: PrivacyVerdict | None = None  # se setea en paso 5b

        # 0. ToxicityGate — bloquear antes de procesar
        if self._toxicity_gate is not None:
            tox_result = self._toxicity_gate.evaluate(query)
            if not tox_result.passed:
                response = ChatResponse(
                    answer=tox_result.user_message or "Consulta no procesable.",
                    intent=Intent.OUT_OF_SCOPE,
                    sources=[],
                    model_used="none",
                    cached=False,
                )
                await self._emit_audit(
                    request, response, route_decision, sources_used_names, t_start
                )
                return response

        # 1. Embed query (sync HTTP → thread)
        query_vector: list[float] = await asyncio.to_thread(
            self._embedder.embed_query, query
        )

        # 0b. LanguageGate — detectar idioma para contexto adicional
        language_hint: str | None = None
        if self._language_gate is not None:
            lang_result = self._language_gate.evaluate(query)
            if lang_result.user_message:
                language_hint = lang_result.user_message

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
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        # 4b. GREETING: respuesta conversacional directa sin RAG
        if route_decision is not None and route_decision.intent == IntentCategory.GREETING:
            greeting_llm = self._fast_llm or self._synthesis_llm
            greeting_system = (
                f"Eres GUIA, el asistente universitario de {self._institution}. "
                "Responde de forma breve, amigable y directa. "
                "No listes fuentes ni hagas búsquedas. No inventes información."
            )
            g_messages = [LLMMessage(role="system", content=greeting_system)]
            for turn in request.history:
                g_messages.append(LLMMessage(role=turn.role, content=turn.content))
            g_messages.append(LLMMessage(role="user", content=query))
            g_response = await asyncio.to_thread(
                greeting_llm.complete, g_messages, max_tokens=200, temperature=0.3
            )
            response = ChatResponse(
                answer=g_response.content,
                intent=intent,
                sources=[],
                model_used=g_response.model,
                cached=False,
            )
            await self._emit_audit(
                request, response, route_decision, sources_used_names, t_start
            )
            return response

        # 5. RAG: reescribir query con pipeline NLP (ADR-044) antes del retrieval
        search_text = query
        if self._query_rewriter is not None:
            try:
                rewrite = await self._query_rewriter.rewrite(
                    query,
                    [{"role": t.role, "content": t.content} for t in request.history],
                )
                if rewrite.is_search_query and rewrite.cleaned:
                    search_text = rewrite.cleaned
            except Exception:
                pass

        if self._search_adapter is not None:
            # M4: await directo, sin asyncio.run() bridge
            hits = await self._search_adapter.hybrid_dicts(
                text=search_text,
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

        # 5b. PrivacyRouter (P2.2) — combina sources + PII en query/docs.
        # MAX-LEVEL-WINS: si final_level >= L2_PERSONAL → force_local.
        privacy_verdict = self._privacy_router.evaluate(
            query=query,
            sources_used=sources_used_names,
            retrieved_docs_text=context_text,
        )

        # 6. Elegir LLM de síntesis según privacidad + complejidad.
        # Prioridad 1: privacy_verdict.force_local fuerza fast_llm si es local.
        # Prioridad 2: tier de RouteDecision (CascadeRouter).
        # Prioridad 3: ModelRouter legacy.
        # Prioridad 4: synthesis_llm directo.
        if privacy_verdict.force_local and self._fast_llm is not None:
            # GUARDRAIL DE PRIVACIDAD: datos L2/L3 nunca van a cloud
            synthesis_llm = self._fast_llm
        elif route_decision is not None and self._fast_llm is not None:
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

        # 6b. PII redaction (P2.3) — segunda capa de defensa.
        # Si vamos a cloud (no force_local) Y hay PII en query/contexto,
        # reemplazar por placeholders antes de enviar; re-hidratar después.
        # Si vamos a local (force_local=True), no redactamos: el LLM local
        # ya está en infraestructura controlada.
        going_to_cloud = synthesis_llm is self._synthesis_llm and not (
            privacy_verdict and privacy_verdict.force_local
        )
        pii_replacements: dict[str, str] = {}
        query_for_llm = query
        context_for_llm = context_text
        if going_to_cloud:
            d_query = redact(query)
            d_context = redact(context_text) if context_text else redact("")
            if d_query.has_pii or d_context.has_pii:
                query_for_llm = d_query.redacted_text
                context_for_llm = d_context.redacted_text
                pii_replacements = {**d_query.replacements, **d_context.replacements}

        # 7. Síntesis LLM (sync → thread)
        context_block = (
            context_for_llm
            if context_for_llm
            else (
                "(la búsqueda no devolvió documentos relevantes — sigue las "
                "instrucciones de la sección 'Cómo razonar sobre el contexto "
                "recuperado' para sugerir reformular con sinónimos)"
            )
        )
        context_block_final = context_block
        if language_hint:
            context_block_final = f"[Nota: {language_hint}]\n\n{context_block}"
        system = _SYSTEM_PROMPT.format(
            institution=self._institution,
            sources_inventory=self._sources_inventory,
            context=context_block_final,
        )
        messages = [LLMMessage(role="system", content=system)]
        for turn in request.history:
            messages.append(LLMMessage(role=turn.role, content=turn.content))
        messages.append(LLMMessage(role="user", content=query_for_llm))
        llm_response = await asyncio.to_thread(
            synthesis_llm.complete, messages, max_tokens=1024, temperature=0.1
        )

        # 7b. Re-hidratar la respuesta del LLM (si redactamos antes)
        answer_text = llm_response.content
        if pii_replacements:
            answer_text = restore(answer_text, pii_replacements)

        response = ChatResponse(
            answer=answer_text,
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
            request, response, route_decision, sources_used_names, t_start,
            privacy_verdict, pii_redacted=bool(pii_replacements),
        )
        return response

    async def _emit_audit(
        self,
        request: ChatRequest,
        response: ChatResponse,
        route_decision: RouteDecision | None,
        sources_used: list[str],
        t_start: float,
        privacy_verdict: PrivacyVerdict | None = None,
        pii_redacted: bool = False,
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

        # P2.2: privacidad final = privacy_verdict si existe (más preciso),
        # sino route_decision.privacy del CascadeRouter, sino default cloud_ok.
        if privacy_verdict is not None:
            privacy_level = (
                "always_local" if privacy_verdict.force_local else "cloud_ok"
            )
            pii_detected = privacy_verdict.pii_in_query or privacy_verdict.pii_in_docs
        elif route_decision is not None:
            privacy_level = route_decision.privacy.value
            pii_detected = False
        else:
            privacy_level = "cloud_ok"
            pii_detected = False

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
            pii_detected=pii_detected,
            pii_redacted=pii_redacted,
            latency_ms=latency_ms,
            cached=response.cached,
        )
        try:
            await self._audit_repo.record(entry)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("audit_emit_failed", exc_info=True)
