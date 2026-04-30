"""Tests del módulo chunking (P3.1, ADR-037)."""

from __future__ import annotations

import pytest

from guia.services.chunking import (
    DEFAULT_MAX_WORDS,
    chunk_text,
    iter_chunks_for_publication,
    make_chunk_id,
    make_chunk_metadata,
)


# ── chunk_text ────────────────────────────────────────────────────────────


def test_chunk_text_short_returns_one_chunk() -> None:
    """Texto corto cabe en un solo chunk."""
    text = "abstract corto de la tesis"
    chunks = chunk_text(text)
    assert chunks == [text]


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_long_splits_into_multiple() -> None:
    """Texto de 1000 palabras → varios chunks de ~250 cada uno."""
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_text(text, max_words=250, overlap=50)

    assert len(chunks) >= 4  # 1000/250 = 4 sin overlap, más con overlap
    for chunk in chunks:
        word_count = len(chunk.split())
        assert word_count <= 250


def test_chunk_text_overlap_works() -> None:
    """Chunks consecutivos comparten 'overlap' palabras."""
    words = [f"w{i}" for i in range(300)]
    text = " ".join(words)
    chunks = chunk_text(text, max_words=100, overlap=20)

    # Primer chunk: w0..w99
    # Segundo chunk: w80..w179 (overlap de 20)
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    overlap_words = set(first_words) & set(second_words)
    assert len(overlap_words) >= 20


def test_chunk_text_no_overlap() -> None:
    """overlap=0 produce chunks disjuntos."""
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_text(text, max_words=100, overlap=0)

    for i in range(len(chunks) - 1):
        first = set(chunks[i].split())
        second = set(chunks[i + 1].split())
        assert not (first & second), f"chunks {i} y {i+1} solapan"


def test_chunk_text_invalid_params() -> None:
    with pytest.raises(ValueError):
        chunk_text("texto", max_words=0)
    with pytest.raises(ValueError):
        chunk_text("texto", max_words=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_text("texto", max_words=100, overlap=-1)


# ── make_chunk_id / metadata ──────────────────────────────────────────────


def test_make_chunk_id_deterministic() -> None:
    assert make_chunk_id("dspace:123", 0) == "dspace:123#chunk_0"
    assert make_chunk_id("dspace:123", 5) == "dspace:123#chunk_5"


def test_make_chunk_metadata_includes_parent_info() -> None:
    parent_meta = {
        "title": "Tesis sobre IA",
        "source": "dspace",
        "authors": ["Pérez, J."],
        "year": 2024,
        "kind": "thesis",
        "abstract": "Texto largo...",  # NO debe heredarse al chunk
    }
    cm = make_chunk_metadata("dspace:1", 2, 5, parent_meta)

    assert cm["parent_id"] == "dspace:1"
    assert cm["chunk_index"] == 2
    assert cm["chunk_total"] == 5
    assert cm["is_chunk"] is True
    assert cm["title"] == "Tesis sobre IA"
    assert cm["source"] == "dspace"
    assert cm["authors"] == ["Pérez, J."]
    # abstract NO se hereda — vive solo en el padre (Capa B)
    assert "abstract" not in cm


# ── iter_chunks_for_publication ───────────────────────────────────────────


def test_iter_chunks_short_text_yields_nothing() -> None:
    """Texto corto → no se generan chunks (el padre es suficiente)."""
    chunks = list(
        iter_chunks_for_publication(
            "dspace:1", "abstract corto", {"title": "T"}
        )
    )
    assert chunks == []


def test_iter_chunks_long_text_yields_multiple() -> None:
    long_text = " ".join(f"palabra{i}" for i in range(1000))
    chunks = list(
        iter_chunks_for_publication(
            "dspace:1",
            long_text,
            {"title": "Tesis larga", "source": "dspace"},
        )
    )
    assert len(chunks) >= 4

    for i, (cid, ctext, cmeta) in enumerate(chunks):
        assert cid == f"dspace:1#chunk_{i}"
        assert cmeta["parent_id"] == "dspace:1"
        assert cmeta["chunk_index"] == i
        assert cmeta["chunk_total"] == len(chunks)
        assert cmeta["is_chunk"] is True
        assert cmeta["title"] == "Tesis larga"
        assert len(ctext.split()) <= DEFAULT_MAX_WORDS
