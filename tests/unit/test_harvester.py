"""Tests del harvester — separación embedding_text vs display_metadata (ADR-037)."""

from __future__ import annotations

from types import SimpleNamespace

from guia.services.harvester import (
    _MAX_EMBEDDING_CHARS,
    _publication_to_embedding_text,
    _publication_to_metadata,
)


def _make_pub(
    *,
    title: str = "",
    abstract: str = "",
    keywords: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> SimpleNamespace:
    """Construye un objeto Publication-like para tests (duck-typed)."""
    return SimpleNamespace(
        title=SimpleNamespace(primary_value=title) if title else None,
        abstract=SimpleNamespace(primary_value=abstract) if abstract else None,
        keywords=keywords,
        extra=extra,
        publication_date=None,
        kind=None,
        primary_language=None,
        external_ids=None,
        authorships=None,
        publisher=None,
        id=None,
    )


# ─── Capa A — embedding_text se trunca (debe seguir igual tras refactor) ──


def test_embedding_text_is_truncated_to_max_chars() -> None:
    """El input al embedder se trunca a _MAX_EMBEDDING_CHARS (E5 ~512 tokens)."""
    long_abstract = "palabra " * 500  # ~3500 chars
    pub = _make_pub(title="Título corto", abstract=long_abstract)

    text = _publication_to_embedding_text(pub)

    assert len(text) <= _MAX_EMBEDDING_CHARS
    assert _MAX_EMBEDDING_CHARS == 1500  # documenta el contrato


def test_embedding_text_short_input_not_truncated() -> None:
    """Textos cortos pasan sin tocar."""
    pub = _make_pub(title="Título", abstract="Abstract corto.")

    text = _publication_to_embedding_text(pub)

    assert text == "Título Abstract corto."


def test_embedding_text_includes_keywords() -> None:
    """Keywords se concatenan al embedding text."""
    pub = _make_pub(title="T", abstract="A", keywords=["ml", "educacion"])

    text = _publication_to_embedding_text(pub)

    assert "ml" in text
    assert "educacion" in text


# ─── Capa B — metadata es lossless (lo que P1.1 corrige) ─────────────────


def test_metadata_preserves_full_abstract_no_truncation() -> None:
    """REGRESIÓN P1.1: el abstract debe guardarse íntegro, no truncado.

    Antes del fix: meta['abstract'] = abstract[:1000]. Hoy: completo.
    """
    long_abstract = "Este es un abstract muy detallado. " * 100  # ~3500 chars
    pub = _make_pub(title="T", abstract=long_abstract)

    meta = _publication_to_metadata(pub)

    assert meta["abstract"] == long_abstract
    assert len(meta["abstract"]) > _MAX_EMBEDDING_CHARS


def test_metadata_preserves_full_toc_from_koha() -> None:
    """TOC de Koha (MARC 505) se guarda íntegro como string o lista."""
    long_toc = "Capítulo " + " — Capítulo ".join(str(i) for i in range(1, 51))
    pub = _make_pub(title="Libro", extra={"toc": long_toc})

    meta = _publication_to_metadata(pub)

    assert meta["toc"] == long_toc
    assert "Capítulo 50" in meta["toc"]


def test_metadata_preserves_toc_as_list() -> None:
    """TOC como lista de capítulos también se preserva."""
    chapters = [f"Capítulo {i}: contenido detallado" for i in range(1, 31)]
    pub = _make_pub(title="Libro", extra={"toc": chapters})

    meta = _publication_to_metadata(pub)

    assert meta["toc"] == chapters
    assert len(meta["toc"]) == 30


def test_metadata_preserves_description_full() -> None:
    """description_full (DSpace dc.description largo) sin truncar."""
    long_desc = "Descripción detallada del trabajo. " * 200
    pub = _make_pub(title="Tesis", extra={"description_full": long_desc})

    meta = _publication_to_metadata(pub)

    assert meta["description_full"] == long_desc


def test_metadata_description_falls_back_to_description_key() -> None:
    """Si no hay description_full, usa el key 'description'."""
    pub = _make_pub(title="T", extra={"description": "Texto descripción"})

    meta = _publication_to_metadata(pub)

    assert meta["description_full"] == "Texto descripción"


def test_metadata_separates_subjects_ocde_from_subjects() -> None:
    """subjects_ocde (CONCYTEC) va separado de subjects libres."""
    pub = _make_pub(
        title="T",
        extra={
            "subjects": ["ml", "ai"],
            "subjects_ocde": ["1.02.01 Ciencias de la Computación"],
        },
    )

    meta = _publication_to_metadata(pub)

    assert meta["subjects"] == ["ml", "ai"]
    assert meta["subjects_ocde"] == ["1.02.01 Ciencias de la Computación"]


def test_metadata_no_extra_means_no_optional_fields() -> None:
    """Si la Publication no tiene extra, no hay toc/description_full/subjects_ocde."""
    pub = _make_pub(title="T", abstract="A")

    meta = _publication_to_metadata(pub)

    assert "toc" not in meta
    assert "description_full" not in meta
    assert "subjects_ocde" not in meta
    assert meta["title"] == "T"
    assert meta["abstract"] == "A"


# ─── Coherencia entre Capa A y Capa B ─────────────────────────────────────


def test_embedding_text_truncated_but_metadata_complete() -> None:
    """Contrato ADR-037: embedding truncado, metadata completa, en el mismo pub."""
    full_abstract = "x" * 5000
    pub = _make_pub(title="T", abstract=full_abstract)

    embedding_text = _publication_to_embedding_text(pub)
    meta = _publication_to_metadata(pub)

    assert len(embedding_text) <= _MAX_EMBEDDING_CHARS
    assert meta["abstract"] == full_abstract
    assert len(meta["abstract"]) == 5000


# ─── DSpace-CRIS — es un segundo DSpace, con su propia etiqueta de fuente ──


class _AdaptadorFalso:
    """Un DSpaceAdapter mínimo: solo hace falta que sepa cosechar."""

    def __init__(self, publicaciones: list[object]) -> None:
        self._publicaciones = publicaciones
        self.llamadas: list[dict[str, object]] = []

    def harvest(self, *, set_spec: object = None, from_date: object = None):
        self.llamadas.append({"set_spec": set_spec, "from_date": from_date})
        yield from self._publicaciones


def _servicio_con(cris: object | None, registro: list[str]) -> object:
    """HarvesterService con _harvest_source espiado: el pipeline real no es
    lo que se prueba aquí, sino con qué etiqueta de fuente se le llama."""
    from guia.services.harvester import HarvesterService

    svc = HarvesterService(store=None, embedder=None, dspace_cris=cris)  # type: ignore[arg-type]
    svc._harvest_source = lambda *, source_name, iterator, batch_size: (  # type: ignore[method-assign]
        registro.append(source_name),
        list(iterator),
        {"total": 1, "ok": 1, "error": 0},
    )[-1]
    return svc


def test_cris_se_cosecha_como_fuente_propia() -> None:
    """La etiqueta es "cris", no "dspace": son dos repositorios distintos y el
    enlace de cada resultado depende de cuál sea."""
    registro: list[str] = []
    adaptador = _AdaptadorFalso([_make_pub(title="Un artículo")])

    svc = _servicio_con(adaptador, registro)
    resultado = svc.harvest_dspace_cris(from_date="2026-01-01")  # type: ignore[attr-defined]

    assert registro == ["cris"]
    assert resultado["ok"] == 1
    assert adaptador.llamadas == [{"set_spec": None, "from_date": "2026-01-01"}]


def test_sin_cris_configurado_no_falla() -> None:
    """Un despliegue sin CRIS —la mayoría— no puede romperse por esto."""
    registro: list[str] = []

    svc = _servicio_con(None, registro)
    resultado = svc.harvest_dspace_cris()  # type: ignore[attr-defined]

    assert registro == []
    assert resultado == {"total": 0, "ok": 0, "error": 0}


# ─── Los eventos de Indico necesitan un id estable, como las publicaciones ──


class TestIdEstableDeEvento:
    """El mismo evento, dos cosechas, un solo documento.

    Se usaba ``event.id``, un UUIDv7 que el dominio genera **en el
    constructor**: cada cosecha fabricaba un Event nuevo, luego un id nuevo,
    luego una fila nueva. Medido el 11-sep-2026: **50 de los 102 documentos de
    Indico eran duplicados**, con dos ids apuntando a la misma URL.

    No era solo desperdicio: las copias compiten entre sí. El evento "Cultura
    de prevención y resiliencia" era el primero en BM25 —26,9 frente a 11,1—
    y no salía en el top-5 porque sus dos copias se repartían la señal.
    """

    def test_el_id_sale_del_numero_de_evento(self) -> None:
        from guia.services.harvester import _id_estable_de_evento

        meta = {"url": "https://indico.upeu.edu.pe/event/359/", "title": "Charla"}

        assert _id_estable_de_evento(object(), meta) == "indico:event:359"

    def test_dos_cosechas_del_mismo_evento_dan_el_mismo_id(self) -> None:
        from guia.services.harvester import _id_estable_de_evento

        meta = {"url": "https://indico.upeu.edu.pe/event/359/", "title": "Charla"}

        # Objetos distintos, como los que fabrica cada cosecha.
        assert _id_estable_de_evento(object(), dict(meta)) == _id_estable_de_evento(
            object(), dict(meta)
        )

    def test_sin_url_se_usa_una_huella_del_titulo(self) -> None:
        """Peor que la URL, pero al menos no cambia en cada pasada."""
        from guia.services.harvester import _id_estable_de_evento

        meta = {"title": "Jornada de investigación"}
        primero = _id_estable_de_evento(object(), meta)

        assert primero.startswith("indico:event:sha1:")
        assert primero == _id_estable_de_evento(object(), dict(meta))

    def test_eventos_distintos_no_colisionan(self) -> None:
        from guia.services.harvester import _id_estable_de_evento

        a = _id_estable_de_evento(object(), {"url": ".../event/359/"})
        b = _id_estable_de_evento(object(), {"url": ".../event/360/"})

        assert a != b
