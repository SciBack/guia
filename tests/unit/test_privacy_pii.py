"""Tests de PII redaction (P2.3, ADR-036)."""

from __future__ import annotations

import pytest

from guia.privacy import redact, restore


# ── No-op cuando no hay PII ───────────────────────────────────────────────


def test_redact_empty_text() -> None:
    d = redact("")
    assert d.has_pii is False
    assert d.redacted_text == ""
    assert d.replacements == {}


def test_redact_text_without_pii() -> None:
    d = redact("¿qué tesis hay sobre teología sistemática?")
    assert d.has_pii is False
    assert d.redacted_text == "¿qué tesis hay sobre teología sistemática?"


# ── DNI (8 dígitos) ───────────────────────────────────────────────────────


def test_redact_dni() -> None:
    d = redact("mi DNI es 70123456")
    assert d.has_pii is True
    assert "70123456" not in d.redacted_text
    assert "<USER_DNI_1>" in d.redacted_text
    assert d.replacements["<USER_DNI_1>"] == "70123456"


def test_redact_does_not_match_short_numbers() -> None:
    """7 dígitos no son DNI."""
    d = redact("código antiguo: 1234567")
    # Los 7 dígitos 1234567 no son DNI ni código (9 dígitos), no hay match.
    assert d.has_pii is False


def test_redact_does_not_match_long_numbers_as_dni() -> None:
    """10 dígitos no son DNI ni código."""
    d = redact("número 1234567890")
    assert "DNI" not in d.types_detected


# ── Código estudiante (9 dígitos) ─────────────────────────────────────────


def test_redact_codigo_estudiante() -> None:
    d = redact("mi código de estudiante es 201912345")
    assert d.has_pii is True
    assert "201912345" not in d.redacted_text
    assert any(ph.startswith("<USER_CODIGO_") for ph in d.replacements)


# ── Email ─────────────────────────────────────────────────────────────────


def test_redact_email_institucional() -> None:
    d = redact("contáctame en juan.perez@upeu.edu.pe")
    assert d.has_pii is True
    assert "juan.perez@upeu.edu.pe" not in d.redacted_text
    assert "<USER_EMAIL_1>" in d.redacted_text


def test_redact_email_generico() -> None:
    """Cualquier email se redacta, no solo .edu.pe."""
    d = redact("mi correo es alguien@gmail.com")
    assert d.has_pii is True
    assert "alguien@gmail.com" not in d.redacted_text


# ── Teléfono peruano ──────────────────────────────────────────────────────


def test_redact_telefono_pe() -> None:
    d = redact("mi celular es 987654321")
    assert d.has_pii is True
    assert "987654321" not in d.redacted_text
    # Es un 9 al inicio + 8 dígitos = teléfono móvil PE


def test_redact_telefono_con_codigo_pais() -> None:
    d = redact("llámame al +51 987654321")
    assert d.has_pii is True


def test_redact_does_not_match_telefono_fijo() -> None:
    """7 dígitos fijos no matchean."""
    d = redact("teléfono fijo 6224444")
    assert d.has_pii is False


# ── Múltiples PII ─────────────────────────────────────────────────────────


def test_redact_multiple_distinct_pii() -> None:
    text = "Soy Juan, DNI 70123456, código 201912345, correo j@upeu.edu.pe"
    d = redact(text)
    assert d.has_pii is True
    types = d.types_detected
    assert "DNI" in types
    assert "CODIGO" in types
    assert "EMAIL" in types


def test_redact_same_value_twice_uses_same_placeholder() -> None:
    """Si un mismo DNI aparece dos veces, se usa el mismo placeholder."""
    d = redact("DNI 70123456 confirmado. Repito DNI 70123456")
    # Solo una entrada en replacements (mismo valor)
    dni_placeholders = [k for k in d.replacements if "DNI" in k]
    assert len(dni_placeholders) == 1


# ── restore() ─────────────────────────────────────────────────────────────


def test_restore_reverses_redact() -> None:
    """redact() y luego restore() devuelve el texto original."""
    original = "Soy juan@upeu.edu.pe DNI 70123456"
    d = redact(original)
    restored = restore(d.redacted_text, d.replacements)
    assert restored == original


def test_restore_handles_llm_response_with_placeholders() -> None:
    """El LLM cloud puede repetir el placeholder en su respuesta."""
    d = redact("verifica mi DNI 70123456")
    # Simulación de respuesta del LLM
    llm_response = "Tu DNI <USER_DNI_1> está registrado correctamente."
    restored = restore(llm_response, d.replacements)
    assert restored == "Tu DNI 70123456 está registrado correctamente."


def test_restore_no_placeholders_passes_through() -> None:
    """Texto sin placeholders no se altera."""
    text = "una respuesta sin nada que reemplazar"
    assert restore(text, {}) == text
    assert restore(text, {"<USER_DNI_1>": "70123456"}) == text


# ── Idempotencia ──────────────────────────────────────────────────────────


def test_redact_is_idempotent() -> None:
    """Aplicar redact dos veces no detecta más PII (los placeholders no matchean)."""
    text = "DNI 70123456 email a@b.com"
    d1 = redact(text)
    d2 = redact(d1.redacted_text)
    # La segunda pasada no debería detectar nada nuevo
    assert d2.has_pii is False
    assert d2.redacted_text == d1.redacted_text


# ── types_detected helper ────────────────────────────────────────────────


def test_types_detected_set() -> None:
    d = redact("DNI 70123456 y email x@y.com")
    assert d.types_detected == {"DNI", "EMAIL"}
