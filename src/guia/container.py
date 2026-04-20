"""Composition root de GUIA Node.

Este módulo es el ÚNICO lugar donde se instancian adapters concretos.
Los servicios reciben interfaces (ports) — nunca importan adapters directamente.
"""

from __future__ import annotations

import redis
from sciback_core.ports.llm import LLMPort
from sciback_core.ports.vector_store import VectorStorePort

from guia.config import GUIASettings, LLMMode
from guia.search.backend import SyncSearchAdapter, get_search_adapter
from guia.services.cache import SemanticCache
from guia.services.chat import ChatService
from guia.services.harvester import HarvesterService
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
        from sciback_embeddings_e5 import E5Config, E5EmbeddingAdapter
        from sciback_vectorstore_pgvector import PgVectorConfig, PgVectorStore

        # _env_file=None: evita que cada adapter lea el .env completo de GUIA
        # (que contiene vars de otros adapters y causaría extra_forbidden).
        # Las vars PGVECTOR_*, E5_*, CLAUDE_*, OLLAMA_* se exportan como env vars reales.
        pg_config = PgVectorConfig(_env_file=None)
        self.store: VectorStorePort = PgVectorStore(pg_config)
        self._pg_store_concrete = self.store  # para cleanup

        self.embedder = E5EmbeddingAdapter(E5Config(_env_file=None))

        # LLMs según modo
        mode = self.settings.guia_llm_mode

        if mode == LLMMode.CLOUD:
            self.synthesis_llm = self._build_claude()
            self.classifier_llm: LLMPort = self.synthesis_llm

        elif mode == LLMMode.LOCAL:
            ollama = self._build_ollama()
            self.synthesis_llm = ollama
            self.classifier_llm = ollama

        else:  # HYBRID (default)
            self.synthesis_llm = self._build_claude()
            self.classifier_llm = self._build_ollama()

        # Adapters de fuentes (opcionales — pueden no estar configurados)
        self.dspace_adapter = self._try_build_dspace()
        self.ojs_adapter = self._try_build_ojs()
        self.alicia_harvester = self._try_build_alicia()

        # M3: Search backend (ADR-029) — None si backend=pgvector
        self.search_adapter: SyncSearchAdapter | None = get_search_adapter(
            self.settings.search_backend,
            self.store,
        )

        # Redis para caché semántico
        self._redis = redis.from_url(self.settings.redis_url, decode_responses=True)

    def _build_claude(self) -> LLMPort:
        from sciback_llm_claude import ClaudeConfig, ClaudeLLMAdapter
        return ClaudeLLMAdapter(ClaudeConfig(_env_file=None))

    def _build_ollama(self) -> LLMPort:
        from sciback_llm_ollama import OllamaConfig, OllamaLLMAdapter
        return OllamaLLMAdapter(OllamaConfig(_env_file=None))

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

    def _init_services(self) -> None:
        """Construye servicios de aplicación usando los adapters."""
        self.cache = SemanticCache(
            self._redis,
            ttl=self.settings.semantic_cache_ttl,
            threshold=self.settings.semantic_cache_threshold,
        )

        self.chat_service = ChatService(
            synthesis_llm=self.synthesis_llm,
            store=self.store,
            embedder=self.embedder,
            classifier_llm=self.classifier_llm,
            cache=self.cache,
            search_adapter=self.search_adapter,  # M3: usa hybrid_sync cuando disponible
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
        )

    def close(self) -> None:
        """Libera recursos (conexiones pool, etc.)."""
        if hasattr(self._pg_store_concrete, "close"):
            self._pg_store_concrete.close()  # type: ignore[union-attr]
        if self.search_adapter is not None:
            import asyncio
            asyncio.run(self.search_adapter.close())
        self._redis.close()
