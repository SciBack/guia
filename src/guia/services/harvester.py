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


def _localized_str(val: object) -> str:
    """Extrae el primary_value de un LocalizedText o devuelve str(val)."""
    pv = getattr(val, "primary_value", None)
    return str(pv) if pv is not None else str(val)


def _publication_to_text(pub: Publication) -> str:
    """Extrae texto relevante de una Publication para embedding."""
    parts: list[str] = []

    if getattr(pub, "title", None):
        parts.append(_localized_str(pub.title))

    if getattr(pub, "abstract", None):
        parts.append(_localized_str(pub.abstract))

    keywords = getattr(pub, "keywords", None)
    if isinstance(keywords, list) and keywords:
        parts.append(" ".join(str(k) for k in keywords))

    return " ".join(parts) if parts else ""


def _stable_pub_id(pub: Publication, source_name: str, fallback_idx: int) -> str:
    """Devuelve un identificador determinístico para upserts idempotentes.

    Prioriza external_ids con prefijo conocido (koha:, doi:, handle:) sobre el
    UUID interno de la Publication. Fallback al UUID o al índice si nada existe.
    """
    ext_ids = getattr(pub, "external_ids", None) or []
    for eid in ext_ids:
        value = str(getattr(eid, "value", ""))
        # Si ya viene con prefijo "fuente:..." lo usamos tal cual.
        if value.startswith(f"{source_name}:"):
            return value
        # DOI/handle son globalmente únicos: úsalos también
        scheme = str(getattr(eid, "scheme", "")).lower()
        if scheme in ("doi", "handle") and value:
            return f"{scheme}:{value}"

    pub_uuid = getattr(pub, "id", None)
    if pub_uuid:
        return f"{source_name}:uuid:{pub_uuid}"
    return f"{source_name}:idx:{fallback_idx}"


def _publication_to_metadata(pub: Publication) -> dict[str, object]:
    """Extrae metadatos relevantes para almacenar junto al vector."""
    meta: dict[str, object] = {}

    if getattr(pub, "title", None):
        meta["title"] = _localized_str(pub.title)

    if getattr(pub, "abstract", None):
        # Recortar abstract para no inflar la columna jsonb
        meta["abstract"] = _localized_str(pub.abstract)[:1000]

    pub_date = getattr(pub, "publication_date", None)
    year = getattr(pub_date, "year_int", None) if pub_date else None
    if year and year != 1000:
        meta["year"] = int(year)

    kind = getattr(pub, "kind", None)
    if kind is not None:
        meta["kind"] = str(getattr(kind, "value", kind))

    primary_lang = getattr(pub, "primary_language", None)
    if primary_lang:
        meta["language"] = str(primary_lang)

    # External identifiers: ISBN/DOI/handle/koha-id, etc.
    ext_ids = getattr(pub, "external_ids", None) or []
    if ext_ids:
        ids_dict: dict[str, list[str]] = {}
        for eid in ext_ids:
            scheme = str(getattr(eid, "scheme", "")).lower()
            value = str(getattr(eid, "value", ""))
            if scheme and value:
                ids_dict.setdefault(scheme, []).append(value)
        if ids_dict:
            meta["external_ids"] = ids_dict

    # Authorships
    authorships = getattr(pub, "authorships", None) or []
    authors: list[str] = []
    for a in authorships:
        person = getattr(a, "person", None)
        full_name = getattr(person, "full_name", None) if person else None
        if full_name:
            authors.append(_localized_str(full_name))
    # Fallback: keywords con autor (Koha mete el autor ahí)
    keywords = getattr(pub, "keywords", None) or []
    if not authors and keywords:
        # En Koha, la primera keyword es el autor
        authors = [str(keywords[0])]
    if authors:
        meta["authors"] = authors

    if keywords:
        meta["keywords"] = [str(k) for k in keywords]

    pub_uuid = getattr(pub, "id", None)
    if pub_uuid:
        meta["pub_uuid"] = str(pub_uuid)

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
        """Cosecha el catálogo bibliográfico de Koha vía REST API.

        Nota: Koha tiene búsqueda directa vía REST API (KohaAdapter.search).
        Este harvest solo es necesario si se quiere que libros de Koha aparezcan
        también en consultas RESEARCH/GENERAL de pgvector. Para disponibilidad
        en tiempo real usar get_availability() directamente desde ChatService.
        """
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

    _PROGRESS_INTERVAL = 500  # loguear progreso cada N registros

    def _harvest_source(
        self,
        source_name: str,
        iterator: Iterator[Publication],
        batch_size: int,
    ) -> dict[str, int]:
        """Implementación común de cosecha con batching de embeddings."""
        import time
        total = 0
        ok = 0
        error = 0
        t_start = time.monotonic()

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
                error += 1
                continue

            pub_id = _stable_pub_id(pub, source_name, total)
            meta = _publication_to_metadata(pub)

            batch_texts.append(text)
            batch_ids.append(pub_id)
            batch_metas.append(meta)

            if len(batch_texts) >= batch_size:
                flush_batch()

            if total % self._PROGRESS_INTERVAL == 0:
                elapsed = time.monotonic() - t_start
                rate = total / elapsed if elapsed > 0 else 0
                logger.info(
                    "harvest_progress",
                    extra={
                        "source": source_name,
                        "processed": total,
                        "ok": ok,
                        "error": error,
                        "rate_per_sec": round(rate, 1),
                        "elapsed_s": round(elapsed),
                    },
                )
                print(
                    f"[{source_name}] {total} procesados — {ok} OK, {error} err "
                    f"— {rate:.1f} reg/s — {round(elapsed)}s",
                    flush=True,
                )

        flush_batch()

        elapsed = time.monotonic() - t_start
        rate = total / elapsed if elapsed > 0 else 0
        logger.info(
            "harvest_complete",
            extra={
                "source": source_name,
                "total": total,
                "ok": ok,
                "error": error,
                "elapsed_s": round(elapsed),
                "rate_per_sec": round(rate, 1),
            },
        )
        print(
            f"[{source_name}] COMPLETO — {total} procesados, {ok} OK, {error} err "
            f"— {rate:.1f} reg/s — {round(elapsed)}s",
            flush=True,
        )
        return {"total": total, "ok": ok, "error": error}
