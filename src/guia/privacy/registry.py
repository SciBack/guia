"""Registry de DataLevel por (source, method) — declarativo (ADR-036).

Mientras los adapters externos (sciback-adapter-dspace, ojs, koha, alicia)
no migren al patrón @data_classification, GUIA mantiene su propia tabla
de clasificación basada en el `source_name` que aparece en sources_used
del audit (y en metadata['source'] del vector store).

Cuando un adapter use varios métodos con niveles distintos (caso típico:
Koha que tiene `search_catalog` L0 y `get_patron_loans` L2), se modela
extendiendo el source_name con sufijo: 'koha-loans', 'koha-patron'.
"""

from __future__ import annotations

from guia.privacy.levels import DataLevel

# Tabla source → DataLevel.
#
# REGLA: si una nueva fuente aparece en sources_used del audit y NO está
# en este registry, el level_for() retorna el conservador L1_INTERNAL por
# defecto. Para activar políticas más permisivas (L0_PUBLIC) o estrictas
# (L2/L3), agregarla aquí explícitamente.
SOURCE_REGISTRY: dict[str, DataLevel] = {
    # ── L0: producción científica pública ───────────────────────────────
    "dspace": DataLevel.L0_PUBLIC,
    "ojs": DataLevel.L0_PUBLIC,
    "alicia": DataLevel.L0_PUBLIC,
    "openalex": DataLevel.L0_PUBLIC,
    "crossref": DataLevel.L0_PUBLIC,
    "orcid": DataLevel.L0_PUBLIC,
    "ror": DataLevel.L0_PUBLIC,
    "pgvector": DataLevel.L0_PUBLIC,  # vector store con docs públicos hoy
    "opensearch": DataLevel.L0_PUBLIC,  # idem (M2)
    "cache": DataLevel.L0_PUBLIC,  # caché de respuestas a queries L0
    # ── L0: catálogo bibliográfico (libros disponibles públicos) ────────
    "koha": DataLevel.L0_PUBLIC,  # search_catalog → catálogo bibliográfico
    "koha-catalog": DataLevel.L0_PUBLIC,
    # ── L1: información institucional no-PII ────────────────────────────
    "internal": DataLevel.L1_INTERNAL,
    "calendar": DataLevel.L1_INTERNAL,
    "events": DataLevel.L1_INTERNAL,
    # ── L2: datos personales del usuario ────────────────────────────────
    "koha-loans": DataLevel.L2_PERSONAL,  # préstamos del usuario
    "koha-patron": DataLevel.L2_PERSONAL,  # perfil del usuario
    "sis": DataLevel.L2_PERSONAL,  # notas, matrícula
    "erp": DataLevel.L2_PERSONAL,  # estado de cuenta
    "moodle": DataLevel.L2_PERSONAL,
    # ── L3: datos confidenciales / regulados ────────────────────────────
    "rrhh": DataLevel.L3_RESTRICTED,
    "salud": DataLevel.L3_RESTRICTED,
    "embargoed-thesis": DataLevel.L3_RESTRICTED,
}


_DEFAULT_LEVEL = DataLevel.L1_INTERNAL
"""Conservador: si no se conoce la fuente, asumir interno (no L0 público)."""


def level_for(source: str) -> DataLevel:
    """DataLevel de una fuente. Default conservador L1_INTERNAL si no está."""
    return SOURCE_REGISTRY.get(source, _DEFAULT_LEVEL)


def max_level_for_sources(sources: list[str]) -> DataLevel:
    """Aplica la regla MAX-LEVEL-WINS sobre un conjunto de fuentes.

    Si una query toca DSpace (L0) Y Koha-loans (L2), el resultado es L2:
    el más restrictivo gana. Lista vacía retorna L0_PUBLIC.
    """
    if not sources:
        return DataLevel.L0_PUBLIC
    return max((level_for(s) for s in sources), default=DataLevel.L0_PUBLIC)
