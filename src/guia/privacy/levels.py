"""DataLevel L0-L3 + decorator @data_classification (ADR-036)."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Callable, TypeVar

T = TypeVar("T", bound=Callable[..., Any])


class DataLevel(IntEnum):
    """Nivel de sensibilidad del dato — orden lexicográfico = orden de severidad.

    L0_PUBLIC < L1_INTERNAL < L2_PERSONAL < L3_RESTRICTED

    Permite usar `max(level_a, level_b)` para combinar niveles.
    """

    L0_PUBLIC = 0
    """Producción científica institucional ya pública (DSpace abierto, OJS, ALICIA)."""

    L1_INTERNAL = 1
    """Información institucional no-PII (calendario, reglamentos, eventos)."""

    L2_PERSONAL = 2
    """Datos personales del usuario (notas, préstamos, perfil, historial). LOCAL ONLY."""

    L3_RESTRICTED = 3
    """Datos confidenciales/regulados (RRHH, salud, embargos). LOCAL + audit + role."""


def data_classification(level: DataLevel) -> Callable[[T], T]:
    """Decorator que marca el nivel de privacidad del retorno de un método.

    Uso (cuando el módulo se mueva a sciback-core en M3):

        class KohaAdapter:
            @data_classification(DataLevel.L0_PUBLIC)
            def search_catalog(self, query: str): ...   # libros públicos

            @data_classification(DataLevel.L2_PERSONAL)
            def get_patron_loans(self, patron_id): ...  # préstamos personales

    El nivel se almacena en `fn.__data_level__` y puede leerse vía introspección.
    """

    def decorator(fn: T) -> T:
        fn.__data_level__ = level  # type: ignore[attr-defined]
        return fn

    return decorator


def get_method_level(fn: Callable[..., Any]) -> DataLevel | None:
    """Lee el DataLevel de un método decorado, o None si no está anotado."""
    return getattr(fn, "__data_level__", None)
