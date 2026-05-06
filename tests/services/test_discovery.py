"""Tests del discovery layer (serendipia controlada)."""

from __future__ import annotations

from guia.config import GUIASettings
from guia.services.discovery import (
    build_explore_links,
    build_source_buckets,
    extract_related_terms,
)


def _settings(**overrides):
    base = dict(
        koha_opac_base_url="https://biblioteca.upeu.edu.pe",
        ojs_base_url="https://revistas.upeu.edu.pe",
        dspace_base_url="https://repositorio.upeu.edu.pe",
        alicia_base_url="https://alicia.concytec.gob.pe",
        dspace_indexed=False,
        alicia_indexed=False,
    )
    base.update(overrides)
    return GUIASettings(**base)


# ── source_buckets ─────────────────────────────────────────────────────────


def test_source_buckets_groups_hits_by_source():
    hits = [
        {"id": "koha:1", "title": "A", "source": "koha"},
        {"id": "koha:2", "title": "B", "source": "koha"},
        {"id": "ojs:1", "title": "C", "source": "ojs"},
    ]
    buckets = build_source_buckets(hits, "nutricion", _settings())

    assert len(buckets) == 2
    assert buckets[0].source_type == "koha"
    assert buckets[0].count == 2
    assert "biblioteca.upeu.edu.pe" in buckets[0].url
    assert "nutricion" in buckets[0].url
    assert buckets[1].source_type == "ojs"
    assert buckets[1].count == 1


def test_source_buckets_omits_when_url_not_configured():
    """Sin URL base configurada → omitimos el bucket en lugar de poner link roto."""
    hits = [{"id": "koha:1", "title": "A", "source": "koha"}]
    buckets = build_source_buckets(hits, "x", _settings(koha_opac_base_url=""))
    assert buckets == []


def test_source_buckets_empty_hits_returns_empty():
    assert build_source_buckets([], "x", _settings()) == []


def test_source_buckets_query_url_encoded():
    hits = [{"id": "ojs:1", "title": "A", "source": "ojs"}]
    buckets = build_source_buckets(hits, "nutrición & dieta", _settings())
    assert buckets and "nutrici" in buckets[0].url
    assert "%26" in buckets[0].url or "%20%26" in buckets[0].url  # & escapado


# ── explore_in ─────────────────────────────────────────────────────────────


def test_explore_in_offers_dspace_when_not_indexed():
    """Cuando DSpace no está indexado y no aparece en buckets, lo sugerimos como exploración."""
    buckets = build_source_buckets(
        [{"id": "koha:1", "title": "A", "source": "koha"}], "x", _settings()
    )
    links = build_explore_links("nutrición", buckets, _settings())

    types = [link.source_type for link in links]
    assert "dspace" in types
    assert "alicia" in types
    dspace = next(link for link in links if link.source_type == "dspace")
    assert dspace.available is False  # marcado como pendiente


def test_explore_in_omits_dspace_if_indexed():
    s = _settings(dspace_indexed=True, alicia_indexed=True)
    links = build_explore_links("x", [], s)
    assert all(link.source_type not in ("dspace", "alicia") for link in links)


def test_explore_in_omits_dspace_when_already_in_buckets():
    """Si DSpace ya aportó hits, no lo duplicamos en explore."""
    buckets = build_source_buckets(
        [{"id": "ds:1", "title": "A", "source": "dspace"}], "x", _settings()
    )
    links = build_explore_links("x", buckets, _settings())
    assert all(link.source_type != "dspace" for link in links)


# ── related_terms ──────────────────────────────────────────────────────────


def test_related_terms_from_subjects():
    hits = [
        {"id": "1", "title": "x", "subjects": ["Nutrición deportiva", "Fisiología"]},
        {"id": "2", "title": "y", "subjects": ["Nutrición deportiva", "Dietética"]},
    ]
    terms = extract_related_terms(hits, query="nutrición")
    # "Nutrición deportiva" aparece dos veces → debe estar y al inicio
    assert "Nutrición deportiva" in terms
    assert "Fisiología" in terms
    assert "Dietética" in terms


def test_related_terms_excludes_query_subset():
    """Subjects cuyos tokens son subset de la query no se sugieren (redundancia)."""
    hits = [{"id": "1", "title": "x", "subjects": ["Nutrición", "Salud pública"]}]
    terms = extract_related_terms(hits, query="nutrición")
    assert "Nutrición" not in terms
    assert "Salud pública" in terms


def test_related_terms_handles_missing_subjects():
    hits = [{"id": "1", "title": "x"}, {"id": "2", "title": "y", "subjects": None}]
    assert extract_related_terms(hits, query="x") == []


def test_related_terms_respects_max():
    hits = [{"id": "1", "title": "x", "subjects": [f"Tema-{i}" for i in range(20)]}]
    terms = extract_related_terms(hits, query="x", max_terms=3)
    assert len(terms) == 3
