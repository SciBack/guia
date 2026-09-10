"""HarvesterService — cosecha publicaciones de DSpace, OJS, ALICIA e Indico."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from guia.services.chunking import iter_chunks_for_publication

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sciback_adapter_alicia import AliciaHarvester
    from sciback_adapter_dspace import DSpaceAdapter
    from sciback_adapter_indico import IndicoAdapter
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


_MAX_EMBEDDING_CHARS = 1500  # multilingual-e5 soporta ~512 tokens ≈ 1500 chars


def _localized_str_or_empty(val: object) -> str:
    """Wrapper de _localized_str que retorna '' si val es None."""
    return _localized_str(val) if val is not None else ""


def _publication_to_full_text(pub: Publication) -> str:
    """Texto extendido (potencialmente largo) para chunking — Capa C (ADR-037).

    Concatena title + abstract + toc + description_full. Si después del
    truncamiento del padre (1500 chars) hay material restante, se chunkeará.
    """
    parts: list[str] = []

    if getattr(pub, "title", None):
        parts.append(_localized_str(pub.title))

    if getattr(pub, "abstract", None):
        parts.append(_localized_str(pub.abstract))

    extra = getattr(pub, "extra", None) or {}
    if isinstance(extra, dict):
        toc = extra.get("toc")
        if toc:
            if isinstance(toc, list):
                parts.append(" ".join(str(t) for t in toc))
            else:
                parts.append(str(toc))
        desc_full = extra.get("description_full") or extra.get("description")
        if desc_full:
            parts.append(str(desc_full))

    return " ".join(parts).strip()


def _publication_to_embedding_text(pub: Publication) -> str:
    """Extrae el texto que se manda al embedder (Capa A — vectorial, lossy).

    Trunca a _MAX_EMBEDDING_CHARS para no exceder el context limit del modelo
    (multilingual-e5-large-instruct, ~512 tokens). El truncamiento es correcto
    AQUÍ y solo aquí — el documento completo se preserva en metadata
    (Capa B — document store) vía _publication_to_metadata. Ver ADR-037.
    """
    parts: list[str] = []

    if getattr(pub, "title", None):
        parts.append(_localized_str(pub.title))

    if getattr(pub, "abstract", None):
        parts.append(_localized_str(pub.abstract))

    keywords = getattr(pub, "keywords", None)
    if isinstance(keywords, list) and keywords:
        parts.append(" ".join(str(k) for k in keywords))

    text = " ".join(parts) if parts else ""
    return text[:_MAX_EMBEDDING_CHARS] if len(text) > _MAX_EMBEDDING_CHARS else text


def _stable_pub_id(pub: Publication, source_name: str, fallback_idx: int) -> str:
    """Devuelve un identificador determinístico para upserts idempotentes.

    "Determinístico" quiere decir: el mismo registro de la misma fuente produce
    el mismo id en cosechas distintas. Si no lo cumple, cada cosecha inserta
    filas nuevas en vez de actualizar las existentes.

    Eso es exactamente lo que pasaba: la versión anterior caía a
    ``f"{source}:uuid:{pub.id}"``, y ``Publication.id`` es un UUIDv7 que
    ``SciBackBaseEntity`` genera **en el constructor**. Cada cosecha fabricaba
    Publications nuevas, luego un id nuevo, luego una fila nueva. Medido el
    2026-09-08 sobre el índice de UPeU: 15.949 registros de OJS para 682 títulos
    distintos, hasta 23 copias del mismo artículo. El ``idx`` de reserva tenía el
    mismo defecto por otra vía — depende de la posición dentro de la cosecha.

    Orden de preferencia, de más a menos fiable:

    1. ``external_ids`` que ya viene con el prefijo de la fuente (``koha:12345``).
    2. Identificador OAI-PMH del registro. El protocolo lo obliga a ser único y
       estable, así que para todo lo cosechado por OAI es la mejor identidad —
       **por delante del DOI**, que es igual de estable pero no siempre está:
       un artículo sin DOI asignado todavía entraba por otra rama, y al
       asignárselo cambiaba de id. Esa divergencia es la que duplicaba.
    3. DOI o handle, globalmente únicos.
    4. URL canónica del recurso.
    5. Huella determinística del contenido — último recurso para registros sin
       ningún identificador. No es tan buena (dos ediciones con idéntico título,
       año y editorial colapsan en una), pero es estable, que es lo que aquí
       importa: preferimos fundir dos registros gemelos antes que multiplicar
       uno solo en cada cosecha.

    ``fallback_idx`` se conserva en la firma por compatibilidad con las llamadas
    existentes, pero ya no participa: era una fuente de inestabilidad.
    """
    ext_ids = getattr(pub, "external_ids", None) or []
    extra = getattr(pub, "extra", None) or {}

    # 1) Identificador ya prefijado por la fuente.
    for eid in ext_ids:
        value = str(getattr(eid, "value", "") or "")
        if value.startswith(f"{source_name}:"):
            return value

    # 2) Identificador OAI-PMH del registro.
    if isinstance(extra, dict):
        oai_id = str(extra.get("oai_identifier") or "").strip()
        if oai_id:
            return oai_id if oai_id.startswith("oai:") else f"oai:{oai_id}"

    # 3) DOI o handle.
    for eid in ext_ids:
        value = str(getattr(eid, "value", "") or "").strip()
        scheme = str(getattr(eid, "scheme", "")).lower()
        # IdentifierScheme puede serializarse como "IdentifierScheme.DOI".
        scheme = scheme.rsplit(".", 1)[-1]
        if value and scheme in ("doi", "handle"):
            return f"{scheme}:{value}"

    # 4) URL canónica.
    if isinstance(extra, dict):
        url = str(extra.get("url") or "").strip()
        if url:
            return f"{source_name}:url:{url}"

    # 5) Huella del contenido.
    return f"{source_name}:sha1:{_content_fingerprint(pub)}"


def _content_fingerprint(pub: Publication) -> str:
    """Huella estable de un registro sin identificador propio.

    Se calcula sobre campos que no cambian entre cosechas: título normalizado,
    año de publicación y editorial. Se dejan fuera resumen y materias, que sí
    varían cuando la fuente corrige metadatos — y un cambio así no debería
    convertir el registro en otro distinto.
    """
    import hashlib
    import unicodedata

    def _norm(value: object) -> str:
        text = str(value or "").strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        return " ".join(text.split())

    titulo = _norm(_localized_str_or_empty(getattr(pub, "title", None)))
    fecha = getattr(pub, "publication_date", None)
    # AcademicDate expone year_int (no year): guarda las partes por separado
    # para no inventar mes y día cuando la fuente solo declara el año.
    anio = _norm(getattr(fecha, "year_int", "") if fecha else "")
    editorial = _norm(getattr(pub, "publisher", None))

    semilla = "\x1f".join([titulo, anio, editorial])
    return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:16]


def _publication_to_metadata(pub: Publication) -> dict[str, object]:
    """Extrae metadatos COMPLETOS sin truncar (Capa B — document store).

    Lossless por diseño (ADR-037): cuando el usuario pide "dame el abstract
    completo" o "muéstrame la tabla de contenido", la respuesta sale de aquí.
    NO truncar campos textuales en esta función — la truncación es
    responsabilidad exclusiva de _publication_to_embedding_text.
    """
    meta: dict[str, object] = {}

    if getattr(pub, "title", None):
        meta["title"] = _localized_str(pub.title)

    if getattr(pub, "abstract", None):
        # Abstract íntegro — el LLM debe poder devolverlo completo cuando lo pidan.
        meta["abstract"] = _localized_str(pub.abstract)

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
    canonical_url: str | None = None
    if ext_ids:
        ids_dict: dict[str, list[str]] = {}
        for eid in ext_ids:
            scheme = str(getattr(eid, "scheme", "")).lower()
            value = str(getattr(eid, "value", "")).strip()
            if scheme and value:
                ids_dict.setdefault(scheme, []).append(value)
                # Construir URL canónica desde DOI o Handle (prioridad: DOI > Handle)
                if canonical_url is None:
                    if scheme == "doi":
                        canonical_url = (
                            value if value.startswith("http") else f"https://doi.org/{value}"
                        )
                    elif scheme == "handle" and canonical_url is None:
                        canonical_url = (
                            value if value.startswith("http") else f"https://hdl.handle.net/{value}"
                        )
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
    # Preferir extra["authors"] (OJS lo llena con dc:creator multi-valor)
    keywords = getattr(pub, "keywords", None) or []
    pub_extra = getattr(pub, "extra", None) or {}
    if not authors:
        extra_authors = pub_extra.get("authors") if isinstance(pub_extra, dict) else None
        if extra_authors and isinstance(extra_authors, list):
            authors = [str(a) for a in extra_authors if a]
    # Fallback final: keywords con autor (Koha mete el autor ahí)
    if not authors and keywords:
        # En Koha, la primera keyword es el autor
        authors = [str(keywords[0])]
    if authors:
        meta["authors"] = authors

    if keywords:
        meta["keywords"] = [str(k) for k in keywords]

    # Publisher (campo nativo de Publication desde v0.8)
    publisher = getattr(pub, "publisher", None)
    if publisher:
        meta["publisher"] = str(publisher)

    # Extra: datos de cita específicos del adapter (subtitle, place, edition, …)
    extra = getattr(pub, "extra", None) or {}
    # URL canónica: prioridad extra["url"] > extra["external_resource_uri"] > DOI/Handle
    extra_url = (
        extra.get("url") if isinstance(extra, dict) else None
    ) or (extra.get("external_resource_uri") if isinstance(extra, dict) else None)
    final_url = extra_url or canonical_url
    if final_url:
        meta["url"] = str(final_url)
    if extra:
        # subtitle va en metadata propio para que el LLM lo use en citas
        for field in ("subtitle", "place", "edition", "series", "pages", "call_number"):
            val = extra.get(field)
            if val:
                meta[field] = str(val)
        # subjects libres (Koha keywords, OJS subjects)
        subjects = extra.get("subjects")
        if subjects and isinstance(subjects, list):
            meta["subjects"] = [str(s) for s in subjects]
        # subjects OCDE (clasificación CONCYTEC, separada de subjects libres)
        subjects_ocde = extra.get("subjects_ocde")
        if subjects_ocde and isinstance(subjects_ocde, list):
            meta["subjects_ocde"] = [str(s) for s in subjects_ocde]
        # TOC: tabla de contenido íntegra (Koha MARC 505), sin truncar
        toc = extra.get("toc")
        if toc:
            meta["toc"] = str(toc) if not isinstance(toc, list) else [str(t) for t in toc]
        # description_full: dc.description largo de DSpace, sin truncar
        description_full = extra.get("description_full") or extra.get("description")
        if description_full:
            meta["description_full"] = str(description_full)

    pub_uuid = getattr(pub, "id", None)
    if pub_uuid:
        meta["pub_uuid"] = str(pub_uuid)

    return meta


def _anio_del_item(item: object) -> int | None:
    """Año de un Event o una Publication, o None si no lo declara."""
    fecha = getattr(item, "starts_at", None) or getattr(item, "date", None)
    for atributo in ("year_int", "year"):
        valor = getattr(fecha, atributo, None)
        if isinstance(valor, int):
            return valor
    texto = str(getattr(fecha, "raw", "") or fecha or "")
    if len(texto) >= 4 and texto[:4].isdigit():
        return int(texto[:4])
    return None


def _event_to_embedding_text(event: object) -> str:
    """Texto para embedding de un Event: título, descripción, sede y tipo.

    La descripción va la primera después del título, y es la razón de ser de
    esta función: un evento sin ella solo se puede encontrar por su nombre, y
    los títulos de congresos y jornadas rara vez dicen de qué tratan. Medido el
    10-sep-2026, antes de incluirla: los 549 eventos del índice tenían el
    título por todo contenido, así que su vector no representaba nada más.
    """
    parts: list[str] = []
    title = getattr(event, "title", None)
    if title:
        parts.append(_localized_str(title))
    descripcion = getattr(event, "description", None)
    if descripcion:
        parts.append(_localized_str(descripcion))
    venue = getattr(event, "venue", None)
    if venue:
        parts.append(str(venue))
    kind = getattr(event, "kind", None)
    if kind:
        parts.append(str(kind))
    text = " ".join(parts)
    return text[:_MAX_EMBEDDING_CHARS] if len(text) > _MAX_EMBEDDING_CHARS else text


def _event_to_metadata(event: object) -> dict[str, object]:
    """Metadatos lossless de un Event para el document store.

    La descripción se guarda bajo la clave ``abstract`` y no ``description``
    porque es el nombre que leen el índice de OpenSearch, el render de fuentes
    y el reranker. Llamarla de otro modo aquí obligaría a tocar los tres.
    """
    meta: dict[str, object] = {}
    descripcion = getattr(event, "description", None)
    if descripcion:
        meta["abstract"] = _localized_str(descripcion)
    title = getattr(event, "title", None)
    if title:
        meta["title"] = _localized_str(title)
    kind = getattr(event, "kind", None)
    if kind:
        meta["kind"] = str(kind)
        meta["source_type"] = "indico"
    venue = getattr(event, "venue", None)
    if venue:
        meta["venue"] = str(venue)
    country_code = getattr(event, "country_code", None)
    if country_code:
        meta["country_code"] = str(country_code)

    starts_at = getattr(event, "starts_at", None)
    if starts_at:
        hint = getattr(starts_at, "display_hint", None) or ""
        if hint:
            date_part = hint.split(" ")[0]
            year_str = date_part.split("-")[0] if date_part else ""
            try:
                meta["year"] = int(year_str)
                meta["date"] = date_part
            except (ValueError, IndexError):
                pass

    # URL del evento: guardada como ExternalIdentifier(scheme=OTHER)
    ext_ids = getattr(event, "external_ids", None) or []
    for eid in ext_ids:
        scheme = str(getattr(eid, "scheme", "")).lower()
        value = str(getattr(eid, "value", "")).strip()
        if scheme == "other" and value.startswith("http") and value:
            meta["url"] = value
            break

    event_uuid = getattr(event, "id", None)
    if event_uuid:
        meta["event_uuid"] = str(event_uuid)

    return meta


class HarvesterService:
    """Servicio de cosecha de publicaciones académicas.

    Args:
        store: Vector store donde persistir los embeddings.
        embedder: E5EmbeddingAdapter para generar embeddings de pasajes.
        dspace: Adapter DSpace 7.x (opcional).
        ojs: Adapter OJS 3.x (opcional).
        alicia: Harvester ALICIA/CONCYTEC (opcional).
        koha: Adapter Koha (opcional).
        indico: Adapter Indico (opcional).
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
        indico: IndicoAdapter | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._dspace = dspace
        self._ojs = ojs
        self._alicia = alicia
        self._koha = koha
        self._indico = indico

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

    def harvest_indico(
        self, *, batch_size: int = 50, solo_anio: int | None = None
    ) -> dict[str, int]:
        """Cosecha eventos y contribuciones de Indico vía HTTP Export API.

        El IndicoHarvester produce un stream mixto de ``Event`` y ``Publication``
        (contribuciones). Los ``Event`` se indexan con helpers propios; las
        ``Publication`` usan el pipeline estándar de publicaciones.

        Args:
            batch_size: Documentos por lote de embedding.
            solo_anio: Si se indica, descarta lo que no sea de ese año. Indico
                mezcla contenidos con vidas muy distintas —clases del ciclo,
                jornadas científicas, promociones del cafetín— y los de ciclos
                pasados dejan de ser útiles en cuanto termina el periodo. Para
                el detalle histórico, GUIA remite a indico.upeu.edu.pe, cuyo
                enlace viaja en los metadatos de cada registro.
        """
        if self._indico is None:
            logger.warning("Indico adapter not configured — skipping")
            return {"total": 0, "ok": 0, "error": 0}

        import time

        from sciback_core.entities.event import Event
        from sciback_core.entities.publication import Publication
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
                for doc_id, vector, meta in zip(
                    batch_ids, embedding_resp.embeddings, batch_metas, strict=False
                ):
                    self._store.upsert(doc_id, vector, metadata=meta)
                ok += len(batch_ids)
            except Exception:
                logger.exception("batch_error", extra={"source": "indico"})
                error += len(batch_ids)
            finally:
                batch_texts.clear()
                batch_ids.clear()
                batch_metas.clear()

        descartados_por_anio = 0
        for item in self._indico.harvest():
            if solo_anio is not None:
                anio = _anio_del_item(item)
                # Sin año declarado se conserva: es preferible indexar algo
                # dudoso a perderlo por un campo que la fuente no rellenó.
                if anio is not None and anio != solo_anio:
                    descartados_por_anio += 1
                    continue

            total += 1
            if isinstance(item, Event):
                embedding_text = _event_to_embedding_text(item)
                if not embedding_text:
                    error += 1
                    continue
                meta = _event_to_metadata(item)
                meta["source"] = "indico"
                doc_id = f"indico:event:{item.id}"
                batch_texts.append(embedding_text)
                batch_ids.append(doc_id)
                batch_metas.append(meta)
            elif isinstance(item, Publication):
                embedding_text = _publication_to_embedding_text(item)
                if not embedding_text:
                    error += 1
                    continue
                doc_id = _stable_pub_id(item, "indico", total)
                meta = _publication_to_metadata(item)
                meta["source"] = "indico"
                batch_texts.append(embedding_text)
                batch_ids.append(doc_id)
                batch_metas.append(meta)

                full_text = _publication_to_full_text(item)
                if len(full_text) > _MAX_EMBEDDING_CHARS * 1.5:
                    for chunk_id, chunk_text, chunk_meta in iter_chunks_for_publication(
                        doc_id, full_text, meta
                    ):
                        batch_texts.append(chunk_text)
                        batch_ids.append(chunk_id)
                        batch_metas.append(chunk_meta)
            else:
                error += 1
                continue

            if len(batch_texts) >= batch_size:
                flush_batch()

            if total % self._PROGRESS_INTERVAL == 0:
                elapsed = time.monotonic() - t_start
                rate = total / elapsed if elapsed > 0 else 0
                logger.info("harvest_progress", extra={"source": "indico", "processed": total})
                print(f"[indico] {total} procesados — {ok} OK, {error} err — {rate:.1f} reg/s", flush=True)

        flush_batch()
        elapsed = time.monotonic() - t_start
        rate = total / elapsed if elapsed > 0 else 0
        print(f"[indico] COMPLETO — {total} procesados, {ok} OK, {error} err — {rate:.1f} reg/s — {round(elapsed)}s", flush=True)
        return {"total": total, "ok": ok, "error": error}

    def harvest_all(self, *, from_date: str | None = None) -> dict[str, dict[str, int]]:
        """Cosecha todas las fuentes configuradas."""
        return {
            "dspace": self.harvest_dspace(from_date=from_date),
            "ojs": self.harvest_ojs(),
            "alicia": self.harvest_alicia(from_date=from_date),
            "koha": self.harvest_koha(),
            "indico": self.harvest_indico(),
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
            embedding_text = _publication_to_embedding_text(pub)
            if not embedding_text:
                error += 1
                continue

            pub_id = _stable_pub_id(pub, source_name, total)
            meta = _publication_to_metadata(pub)

            # 1) Padre: embedding del título + abstract truncado a 1500 chars
            batch_texts.append(embedding_text)
            batch_ids.append(pub_id)
            batch_metas.append(meta)

            # 2) Chunks (P3.1, ADR-037): si el full_text es sustancialmente
            # más largo que el embedding_text, generar chunks adicionales con
            # parent_id apuntando al padre. Permite Parent-Document Retrieval
            # cuando el usuario hace queries que matchean partes específicas
            # de la TOC o description_full.
            full_text = _publication_to_full_text(pub)
            if len(full_text) > _MAX_EMBEDDING_CHARS * 1.5:
                for chunk_id, chunk_text, chunk_meta in iter_chunks_for_publication(
                    pub_id, full_text, meta
                ):
                    batch_texts.append(chunk_text)
                    batch_ids.append(chunk_id)
                    batch_metas.append(chunk_meta)

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
