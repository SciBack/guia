"""PII redaction — detección y reemplazo antes de envíos cloud (P2.3, ADR-036).

Estrategia: cuando una query L0/L1 (cloud_ok) menciona accidentalmente PII
del usuario ('soy Juan Pérez DNI 70123456'), detectar y reemplazar por
placeholders deterministas (`<USER_DNI_1>`, `<USER_EMAIL_1>`) ANTES de
enviar al LLM cloud. La respuesta del LLM se re-hidrata con los valores
originales para que el usuario reciba texto coherente.

Cobertura inicial (regex Perú-céntrica):
- DNI peruano: 8 dígitos
- Email institucional: @*.edu.pe (case-insensitive)
- Email genérico: cualquier dominio (más permisivo, captura @gmail/upeu)
- Código estudiante UPeU: 9 dígitos pegados o tras "código"
- Teléfono peruano: +51 / 9 dígitos empezando por 9

Para detección NER (nombres de personas, organizaciones) ver feature flag
GUIA_PII_NER_ENABLED en una iteración futura — por ahora solo regex.

NO sustituye al PrivacyRouter (P2.2) que decide si la query puede ir a
cloud en primer lugar. Esto es la SEGUNDA capa de defensa: aún cuando
final_level=L0/L1 (cloud_ok), si hay PII residual en la query, se redacta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Patrones ──────────────────────────────────────────────────────────────

# DNI peruano: 8 dígitos exactos
_DNI_RE = re.compile(r"(?<!\d)\d{8}(?!\d)")

# Código estudiante UPeU: 9 dígitos exactos
_CODIGO_ESTUDIANTE_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")

# Email genérico (captura @upeu, @gmail, @outlook, etc.)
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Teléfono peruano móvil: +51 9XXXXXXXX, 9XXXXXXXX (9 dígitos empezando por 9)
_TELEFONO_PE_RE = re.compile(r"(?:\+51\s*)?(?<!\d)9\d{8}(?!\d)")


# Orden importa: detectar primero códigos largos (9 dígitos) antes de DNI (8).
# Si una secuencia de 9 dígitos matchea código, no debe matchear DNI también.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", _EMAIL_RE),
    ("TELEFONO", _TELEFONO_PE_RE),
    ("CODIGO", _CODIGO_ESTUDIANTE_RE),
    ("DNI", _DNI_RE),
]


@dataclass(frozen=True)
class PIIDetection:
    """Resultado de redact()."""

    has_pii: bool
    redacted_text: str
    """Texto con placeholders <USER_DNI_1>, <USER_EMAIL_1>, etc."""
    replacements: dict[str, str] = field(default_factory=dict)
    """Mapa placeholder → valor original. Usar restore() para re-hidratar."""

    @property
    def types_detected(self) -> set[str]:
        """Conjunto de tipos detectados ('DNI', 'EMAIL', ...)."""
        return {p.split("_")[1] for p in self.replacements}


def redact(text: str) -> PIIDetection:
    """Detecta PII en texto y reemplaza por placeholders únicos.

    Idempotente: ejecutar redact() sobre el redacted_text resultante NO
    debería detectar más PII (los placeholders no matchean los patrones).

    Args:
        text: Texto a redactar.

    Returns:
        PIIDetection con has_pii, redacted_text y replacements.
    """
    if not text:
        return PIIDetection(has_pii=False, redacted_text=text, replacements={})

    replacements: dict[str, str] = {}
    counters: dict[str, int] = {}
    redacted = text

    for kind, pattern in _PATTERNS:
        # Acumular matches sin destruir el orden lineal
        # (re.sub con función para mantener counters consistentes)
        def replace_match(m: re.Match[str], k: str = kind) -> str:
            counters[k] = counters.get(k, 0) + 1
            placeholder = f"<USER_{k}_{counters[k]}>"
            original = m.group(0)
            # Si el mismo valor aparece varias veces, reusar el mismo placeholder
            for ph, val in replacements.items():
                if val == original:
                    counters[k] -= 1  # rollback contador
                    return ph
            replacements[placeholder] = original
            return placeholder

        redacted = pattern.sub(replace_match, redacted)

    return PIIDetection(
        has_pii=bool(replacements),
        redacted_text=redacted,
        replacements=replacements,
    )


def restore(text: str, replacements: dict[str, str]) -> str:
    """Re-hidrata placeholders con sus valores originales.

    Inverso de redact(). Útil para mostrar al usuario una respuesta del
    LLM cloud que incluye los placeholders en su salida — los reemplazamos
    de vuelta para que el texto sea legible.

    Args:
        text: Texto que potencialmente contiene placeholders.
        replacements: Mapa retornado por redact().

    Returns:
        Texto con placeholders sustituidos por valores originales.
    """
    out = text
    # Ordenar por longitud descendente para evitar que <USER_DNI_1> matchee
    # dentro de <USER_DNI_10> (no pasa hoy pero es defensa)
    for placeholder in sorted(replacements, key=len, reverse=True):
        out = out.replace(placeholder, replacements[placeholder])
    return out
