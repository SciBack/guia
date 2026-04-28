"""HarvesterService — cosecha publicaciones de DSpace, OJS y ALICIA."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sciback_adapter_alicia import AliciaHarvester
    from sciback_adapter_dspace import DSpaceAdapter
    from sciback_adapter_koha import KohaAdapter
    from sciback_adapter_ojs import OjsAdapter
    from sciback_core.entities.publication import Publication
    from sciback_core.ports.vector_store import VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter

logger = logging.getLogger(__name__)


_MAX_EMBEDDING_CHARS = 1500  # multilingual-e5 soporta ~512 tokens ≈ 1500 chars


def _publication_to_text(pub: Publication) -> str:
    """Extrae texto relevante de una Publication para embedding."""
    parts: list[str] = []

    if hasattr(pub, "title") and pub.title:
        parts.append(str(pub.title))

    if hasattr(pub, "abstract") and pub.abstract:
        parts.append(str(pub.abstract))

    if hasattr(pub, "keywords") and pub.keywords:
        keywords = pub.keywords
        if isinstance(keywords, list):
            parts.append(" ".join(str(k) for k in keywords))

    text = " ".join(parts) if parts else ""
    return text[:_MAX_EMBEDDING_CHARS]


def _publication_to_metadata(pub: Publication) -> dict[str, object]:
    """Extrae metadatos relevantes para almacenar junto al vector."""
    meta: dict[str, object] = {}

    for attr in ("title", "abstract", "year", "doi", "handle", "language"):
        val = getattr(pub, attr, None)
        if val is not None:
            meta[attr] = str(val) if not isinstance(val, int | float) else val

    if hasattr(pub, "authorships"):
        authors = []
        for a in pub.authorships or []:
            if hasattr(a, "person") and hasattr(a.person, "full_name"):
                authors.append(str(a.person.full_name))
        if authors:
            meta["authors"] = authors

    if hasattr(pub, "id"):
        meta["pub_id"] = str(pub.id)

    return meta


class HarvesterService:
    """Servicio de cosecha de publicaciones académicas.

    Args:
        store: Vector store donde persistir los embeddings.
        embedder: E5EmbeddingAdapter para generar embeddings de pasajes.
        dspace: Adapter DSpace 7.x (opcional).
        ojs: Adapter OJS 3.x (opcional).
        alicia: Harvester ALICIA/CONCYTEC (opcional).
    """

    def __init__(
        self,
        store: VectorStorePort,
        embedder: E5EmbeddingAdapter,
        *,
        dspace: DSpaceAdapter | None = None,
        ojs: OjsAdapter | None = None,
        alicia: AliciaHarvester | None = None,
        koha: KohaAdapter | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._dspace = dspace
        self._ojs = ojs
        self._alicia = alicia
        self._koha = koha

    def harvest_dspace(
        self,
        *,
        set_spec: str | None = None,
        from_date: str | None = None,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Cosecha publicaciones de DSpace vía OAI-PMH."""
        if self._dspace is None:
            logger.warning("DSpace adapter not configured — skipping")
            return {"total": 0, "ok": 0, "error": 0}

        return self._harvest_source(
            source_name="dspace",
            iterator=self._dspace.harvest(set_spec=set_spec, from_date=from_date),
            batch_size=batch_size,
        )

    def harvest_ojs(
        self,
        *,
        set_spec: str | None = None,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Cosecha artículos de OJS vía OAI-PMH."""
        if self._ojs is None:
            logger.warning("OJS adapter not configured — skipping")
            return {"total": 0, "ok": 0, "error": 0}

        return self._harvest_source(
            source_name="ojs",
            iterator=self._ojs.harvest(set_spec=set_spec),
            batch_size=batch_size,
        )

    def harvest_alicia(
        self,
        *,
        from_date: str | None = None,
        until_date: str | None = None,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Cosecha publicaciones de ALICIA/CONCYTEC."""
        if self._alicia is None:
            logger.warning("Alicia harvester not configured — skipping")
            return {"total": 0, "ok": 0, "error": 0}

        return self._harvest_source(
            source_name="alicia",
            iterator=self._alicia.harvest(from_date=from_date, until_date=until_date),
            batch_size=batch_size,
        )

    def harvest_koha(self, *, batch_size: int = 50) -> dict[str, int]:
        """Cosecha el catálogo bibliográfico de Koha vía REST API."""
        if self._koha is None:
            logger.warning("Koha adapter not configured — skipping")
            return {"total": 0, "ok": 0, "error": 0}

        return self._harvest_source(
            source_name="koha",
            iterator=self._koha.harvest(),
            batch_size=batch_size,
        )

    def harvest_all(self, *, from_date: str | None = None) -> dict[str, dict[str, int]]:
        """Cosecha todas las fuentes configuradas."""
        return {
            "dspace": self.harvest_dspace(from_date=from_date),
            "ojs": self.harvest_ojs(),
            "alicia": self.harvest_alicia(from_date=from_date),
            "koha": self.harvest_koha(),
        }

    def _harvest_source(
        self,
        source_name: str,
        iterator: Iterator[Publication],
        batch_size: int,
    ) -> dict[str, int]:
        """Implementación común de cosecha con batching de embeddings."""
        total = 0
        ok = 0
        error = 0

        batch_texts: list[str] = []
        batch_ids: list[str] = []
        batch_metas: list[dict[str, object]] = []

        def flush_batch() -> None:
            nonlocal ok, error
            if not batch_texts:
                return
            try:
                embedding_resp = self._embedder.embed_passages(batch_texts)
                for pub_id, vector, meta in zip(
                    batch_ids, embedding_resp.embeddings, batch_metas, strict=False
                ):
                    meta["source"] = source_name
                    self._store.upsert(pub_id, vector, metadata=meta)
                ok += len(batch_ids)
                logger.info("batch_indexed", extra={"source": source_name, "count": len(batch_ids)})
            except Exception:
                logger.exception("batch_error", extra={"source": source_name})
                error += len(batch_ids)
            finally:
                batch_texts.clear()
                batch_ids.clear()
                batch_metas.clear()

        for pub in iterator:
            total += 1
            text = _publication_to_text(pub)
            if not text:
                logger.debug("empty_text", extra={"pub_id": getattr(pub, "id", "?")})
                error += 1
                continue

            pub_id = str(getattr(pub, "id", f"{source_name}:{total}"))
            meta = _publication_to_metadata(pub)

            batch_texts.append(text)
            batch_ids.append(pub_id)
            batch_metas.append(meta)

            if len(batch_texts) >= batch_size:
                flush_batch()

        flush_batch()

        logger.info(
            "harvest_complete",
            extra={"source": source_name, "total": total, "ok": ok, "error": error},
        )
        return {"total": total, "ok": ok, "error": error}
