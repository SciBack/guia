"""Privacy module — clasificación L0-L3 + PrivacyRouter + PII redaction.

ADR-036 — Privacy Classification & PII Handling.

Diseño en 4 capas:
1. DataLevel (L0..L3) — clasificación del nivel de sensibilidad de un dato
2. SOURCE_REGISTRY — tabla declarativa source.method → DataLevel
3. PrivacyRouter — combina (PII en query, niveles de adapters, PII en docs)
   con regla MAX-LEVEL-WINS para producir un PrivacyVerdict
4. PII redaction — detectores regex (DNI peruano, email institucional,
   código estudiante) con redact()/restore() para envíos cloud

Nota arquitectónica: el ADR-036 propone que este módulo viva en
`sciback-core/privacy/`. Mientras `sciback-core` no publique versión nueva,
el módulo vive aquí (`guia/privacy/`) y se moverá en M3.
"""

from guia.privacy.levels import DataLevel, data_classification
from guia.privacy.pii import PIIDetection, redact, restore
from guia.privacy.registry import SOURCE_REGISTRY, level_for, max_level_for_sources
from guia.privacy.router import PrivacyRouter, PrivacyVerdict

__all__ = [
    "DataLevel",
    "PIIDetection",
    "PrivacyRouter",
    "PrivacyVerdict",
    "SOURCE_REGISTRY",
    "data_classification",
    "level_for",
    "max_level_for_sources",
    "redact",
    "restore",
]
