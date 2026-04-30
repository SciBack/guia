"""PII redaction — placeholder, implementación real en P2.3."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PIIDetection:
    """Resultado de la detección de PII en un texto.

    Implementación completa en P2.3. Por ahora solo el shape.
    """

    has_pii: bool = False
    redacted_text: str = ""
    replacements: dict[str, str] = field(default_factory=dict)


def redact(text: str) -> PIIDetection:
    """Detecta y reemplaza PII en un texto. Stub en P2.1; real en P2.3."""
    return PIIDetection(has_pii=False, redacted_text=text, replacements={})


def restore(text: str, replacements: dict[str, str]) -> str:
    """Re-hidrata placeholders con los valores originales. Stub en P2.1."""
    out = text
    for placeholder, original in replacements.items():
        out = out.replace(placeholder, original)
    return out
