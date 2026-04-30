"""Tests del modelo AuditLogEntry y hash_query (P1.3 — Ley 29733).

REGLA CRÍTICA verificada aquí: la query original NUNCA se persiste.
Solo su hash sha256 hex.
"""

from __future__ import annotations

from dataclasses import asdict, fields

import pytest

from guia.audit import AuditLogEntry, hash_query


# ── hash_query() ──────────────────────────────────────────────────────────


def test_hash_query_returns_sha256_hex() -> None:
    """El hash es sha256 hex (64 chars)."""
    h = hash_query("¿cuál es mi promedio?")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_query_is_deterministic() -> None:
    """Misma query → mismo hash."""
    q = "tesis sobre machine learning"
    assert hash_query(q) == hash_query(q)


def test_hash_query_different_for_different_queries() -> None:
    """Queries distintas → hashes distintos."""
    assert hash_query("hola") != hash_query("adios")


def test_hash_query_strips_whitespace() -> None:
    """Espacios al borde no deben afectar el hash (normalización)."""
    assert hash_query("hola") == hash_query("  hola  ")


def test_hash_query_is_case_sensitive() -> None:
    """Mayúsculas/minúsculas SÍ afectan el hash (no normalizamos demasiado)."""
    assert hash_query("HOLA") != hash_query("hola")


# ── AuditLogEntry — REGLA CRÍTICA: no contiene la query ───────────────────


def test_entry_does_not_have_query_field() -> None:
    """REGLA NO-NEGOCIABLE: AuditLogEntry NO tiene un campo 'query' o similar.

    Inspección estática del dataclass: ningún campo se llama 'query',
    'text', 'prompt', 'content' o 'message'.
    """
    forbidden_field_names = {"query", "text", "prompt", "content", "message", "raw"}
    actual_fields = {f.name for f in fields(AuditLogEntry)}
    overlap = actual_fields & forbidden_field_names
    assert not overlap, f"AuditLogEntry tiene campos prohibidos: {overlap}"


def test_entry_has_query_hash_not_query() -> None:
    """El campo se llama query_hash y solo guarda el hash."""
    field_names = {f.name for f in fields(AuditLogEntry)}
    assert "query_hash" in field_names


def test_serialized_entry_does_not_contain_raw_query() -> None:
    """asdict() no expone la query original — solo el hash."""
    raw_query = "información supersecreta sobre mis notas"
    entry = AuditLogEntry(
        user_id="user-123",
        query_hash=hash_query(raw_query),
        intent="campus",
        privacy_level="always_local",
        sources_used=["sis"],
        llm_model="qwen2.5:7b",
        llm_provider="ollama-local",
    )
    blob = str(asdict(entry))

    assert raw_query not in blob
    assert "supersecreta" not in blob
    assert entry.query_hash in blob  # el hash sí está


# ── Defaults conservadores ────────────────────────────────────────────────


def test_entry_defaults_pii_false() -> None:
    """Por default no asume PII detectado/redactado (P2.3 los activa)."""
    e = AuditLogEntry(
        user_id="u",
        query_hash="abc",
        intent="general",
        privacy_level="cloud_ok",
        sources_used=[],
        llm_model="claude-haiku",
        llm_provider="anthropic-cloud",
    )
    assert e.pii_detected is False
    assert e.pii_redacted is False
    assert e.latency_ms == 0
    assert e.cached is False
    assert e.gate_used == "unknown"


def test_entry_is_frozen() -> None:
    """AuditLogEntry es inmutable."""
    e = AuditLogEntry(
        user_id="u",
        query_hash="abc",
        intent="general",
        privacy_level="cloud_ok",
        sources_used=[],
        llm_model="x",
        llm_provider="y",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        e.intent = "research"  # type: ignore[misc]
