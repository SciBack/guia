"""Strip de saludos y cortesías antes del retriever.

Elimina patrones de saludo/cortesía del inicio de la query.
Opera en <1ms, sin dependencias externas.
"""
from __future__ import annotations

import re

_GREETING_PATTERNS = re.compile(
    r"""
    ^\s*
    (
        (buen[oa]s?\s+(?:tardes?|noches?|días?|día))
        | (hola)
        | (saludos?)
        | (qué\s+tal)
        | (estimad[oa]s?\s+\w+)
        | (por\s+favor)
        | (gracias)
        | (disculp[ae])
        | (perdón)
        | (oiga)
        | (oye)
    )
    [\s,!¡¿?.]*
    """,
    re.VERBOSE | re.IGNORECASE,
)

_TRAILING_PATTERNS = re.compile(
    r"""\s*(por\s+favor|gracias|muchas\s+gracias|de\s+antemano)\s*[.!]?\s*$""",
    re.IGNORECASE,
)


def strip_greetings(text: str) -> str:
    """Elimina saludos del inicio y cortesías del final de la query."""
    text = _GREETING_PATTERNS.sub("", text).strip()
    text = _TRAILING_PATTERNS.sub("", text).strip()
    return text
