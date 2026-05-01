"""Composition root de GUIA Node.

Este módulo es el ÚNICO lugar donde se instancian adapters concretos.
Los servicios reciben interfaces (ports) — nunca importan adapters directamente.
"""

from __future__ import annotations

import redis
from sciback_core.ports.llm import LLMPort
from sciback_core.ports.vector_store import VectorStorePort

from guia.audit import AuditLogRepository
from guia.config import GUIASettings, LLMMode
from guia.grobid import GrobidClient
from guia.routing import (
    CascadeRouter,
    EmbeddingRouter,
    LLMIntentCategoryClassifier,
    RuleBasedRouter,
)
from guia.search.backend import SearchAdapter, get_search_adapter
from guia.services.cache import SemanticCache
from guia.services.chat import ChatService
from guia.services.harvester import HarvesterService
from guia.services.history import ConversationRepository
from guia.services.profile import UserProfileRepository
from guia.services.router import ModelRouter
from guia.services.search import SearchService


class GUIAContainer:
    """Contenedor de dependencias de GUIA.

    Construye todos los servicios en el orden correcto según la configuración.
    Diseñado para ser instanciado una sola vez al inicio de la aplicación.

    Args:
        settings: Configuración global de GUIA. Si es None, lee del entorno.
    """

    def __init__(self, settings: GUIASettings | None = None) -> None:
        self.settings = settings or GUIASettings()
        self._init_adapters()
        self._init_services()

    def _init_adapters(self) -> None:
        """Instancia todos los adapters concretos según configuración."""
        from sciback_vectorstore_pgvector import PgVectorConfig, PgVectorStore

        # _env_file=None: evita que cada adapter lea el .env completo de GUIA
        pg_config = PgVectorConfig(_env_file=None)
        self.store: VectorStorePort = PgVectorStore(pg_config)
        self._pg_store_concrete = self.store  # para cleanup

        self.embedder = self._build_embedder()

        # LLMs según modo
        mode = self.settings.guia_llm_mode

        if mode == LLMMode.CLOUD:
            self.synthesis_llm = self._build_claude()
            self.classifier_llm: LLMPort = self.synthesis_llm
            self.fast_llm: LLMPort | None = None  # Cloud: sin fast path local

        elif mode == LLMMode.LOCAL:
            self.synthesis_llm = self._build_ollama()       # qwen2.5:7b
            self.fast_llm = self._build_ollama_fast()       # qwen2.5:3b
            self.classifier_llm = self.fast_llm             # 3b también clasifica

        else:  # HYBRID (default)
            self.synthesis_llm = self._build_claude()       # Claude para síntesis compleja
            self.fast_llm = self._build_ollama_fast()       # 3b para queries simples
            self.classifier_llm = self.fast_llm             # 3b clasifica intent

        # Adapters de fuentes (opcionales)
        self.dspace_adapter = self._try_build_dspace()
        self.ojs_adapter = self._try_build_ojs()
        self.alicia_harvester = self._try_build_alicia()
        self.koha_adapter = self._try_build_koha()
        self.grobid_client = self._try_build_grobid()

        # M4: SearchAdapter async (ADR-029) — None si backend=pgvector
        self.search_adapter: SearchAdapter | None = get_search_adapter(
            self.settings.search_backend,
            self.store,
        )

        # Redis para caché semántico y sesiones
        self._redis = redis.from_url(self.settings.redis_url, decode_responses=True)

    def _build_embedder(self) -> object:
        """Embeddings backend: ollama (E5 remoto) o fastembed (local ONNX)."""
        if self.settings.embedding_backend == "fastembed":
            from sciback_embeddings_fastembed import FastEmbedAdapter, FastEmbedConfig
            return FastEmbedAdapter(FastEmbedConfig(_env_file=None))
        from sciback_embeddings_e5 import E5Config, E5EmbeddingAdapter
        return E5EmbeddingAdapter(E5Config(_env_file=None))

    def _build_claude(self) -> LLMPort:
        from sciback_llm_claude import ClaudeConfig, ClaudeLLMAdapter
        return ClaudeLLMAdapter(ClaudeConfig(_env_file=None))

    def _build_ollama(self) -> LLMPort:
        from sciback_llm_ollama import OllamaConfig, OllamaLLMAdapter
        return OllamaLLMAdapter(OllamaConfig(_env_file=None))

    def _build_ollama_fast(self) -> LLMPort:
        from sciback_llm_ollama import OllamaConfig, OllamaLLMAdapter
        # Instancia separada con qwen2.5:3b — override del modelo por defecto
        cfg = OllamaConfig(_env_file=None, default_model="qwen2.5:3b")
        return OllamaLLMAdapter(cfg)

    def _try_build_dspace(self) -> object:
        try:
            from sciback_adapter_dspace import DSpaceAdapter
            from sciback_adapter_dspace.settings import DSpaceSettings
            return DSpaceAdapter(DSpaceSettings())
        except Exception:
            return None

    def _try_build_ojs(self) -> object:
        try:
            from sciback_adapter_ojs import OjsAdapter
            from sciback_adapter_ojs.settings import OjsSettings
            return OjsAdapter(OjsSettings())
        except Exception:
            return None

    def _try_build_alicia(self) -> object:
        try:
            from sciback_adapter_alicia import AliciaHarvester
            from sciback_adapter_alicia.settings import AliciaSettings
            return AliciaHarvester(AliciaSettings())
        except Exception:
            return None

    def _try_build_koha(self) -> object:
        try:
            from sciback_adapter_koha import KohaAdapter, KohaSettings
            return KohaAdapter(KohaSettings(_env_file=None))
        except Exception:
            return None

    def _try_build_grobid(self) -> GrobidClient | None:
        """Construye GrobidClient si grobid_url está configurado y el servicio responde.

        Si la variable está vacía o el endpoint no contesta, retorna None
        y el harvester opera sin full-text PDF (solo abstract/TOC).
        """
        url = (self.settings.grobid_url or "").strip()
        if not url:
            return None
        client = GrobidClient(base_url=url)
        if not client.is_alive():
            import logging
            logging.getLogger(__name__).warning(
                "grobid_unavailable", extra={"grobid_url": url}
            )
            return None
        return client

    def _init_services(self) -> None:
        """Construye servicios de aplicación usando los adapters."""
        self.cache = SemanticCache(
            self._redis,
            ttl=self.settings.semantic_cache_ttl,
            threshold=self.settings.semantic_cache_threshold,
        )

        # ModelRouter legacy (FAST/FULL): se mantiene por compatibilidad mientras
        # CascadeRouter no cubra el 100% de casos. Solo activo con fast_llm.
        self.router: ModelRouter | None = (
            ModelRouter(self.embedder) if self.fast_llm is not None else None
        )

        # P1.2: CascadeRouter (3 gates) — selección de modelo + privacidad.
        # Gate 3 (LLM classifier opt-in) usa el classifier_llm — ahora se
        # invoca solo cuando Gate 2 (embedding) tiene baja confianza.
        # warm_up() debe llamarse en el lifespan de la app (cl.on_app_startup).
        self.cascade_router: CascadeRouter | None = (
            CascadeRouter(
                rules=RuleBasedRouter(),
                embedding=EmbeddingRouter(self.embedder),
                llm_classifier=LLMIntentCategoryClassifier(self.classifier_llm),
            )
            if self.fast_llm is not None
            else None
        )

        # P1.3: AuditLogRepository — trazabilidad regulatoria (Ley 29733)
        # Persiste sha256(query) — NUNCA la query original. Retención 24 meses.
        self.audit_repo = AuditLogRepository(
            database_url=self.settings.pgvector_database_url,  # type: ignore[attr-defined]
        )
        self.audit_repo.initialize()

        # M4 + P1.2 + P1.3: ChatService async con cascada y audit
        self.chat_service = ChatService(
            synthesis_llm=self.synthesis_llm,
            store=self.store,
            embedder=self.embedder,
            classifier_llm=self.classifier_llm,
            fast_llm=self.fast_llm,
            router=self.router,
            cascade_router=self.cascade_router,
            cache=self.cache,
            search_adapter=self.search_adapter,
            koha_adapter=self.koha_adapter,  # type: ignore[arg-type]
            audit_repo=self.audit_repo,
        )

        self.search_service = SearchService(
            store=self.store,
            embedder=self.embedder,
        )

        self.harvester_service = HarvesterService(
            store=self.store,
            embedder=self.embedder,
            dspace=self.dspace_adapter,  # type: ignore[arg-type]
            ojs=self.ojs_adapter,  # type: ignore[arg-type]
            alicia=self.alicia_harvester,  # type: ignore[arg-type]
            koha=self.koha_adapter,  # type: ignore[arg-type]
        )

        # M4: UserProfileRepository — perfiles persistentes en Postgres (ADR-034)
        self.profile_repository = UserProfileRepository(
            database_url=self.settings.pgvector_database_url,  # type: ignore[attr-defined]
        )
        self.profile_repository.initialize()

        self.conversation_repository = ConversationRepository(
            database_url=self.settings.pgvector_database_url,  # type: ignore[attr-defined]
        )
        self.conversation_repository.initialize()

    def close(self) -> None:
        """Libera recursos (conexiones pool, etc.)."""
        if hasattr(self._pg_store_concrete, "close"):
            self._pg_store_concrete.close()  # type: ignore[union-attr]
        if self.search_adapter is not None:
            import asyncio
            asyncio.run(self.search_adapter.close())
        self.profile_repository.close()
        self.conversation_repository.close()
        self.audit_repo.close()
        self._redis.close()
