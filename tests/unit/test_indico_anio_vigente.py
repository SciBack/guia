"""Indico se queda solo con el año vigente.

Indico mezcla contenidos con vidas muy distintas: las clases del ciclo 2026-II
(45 de los 48 eventos de septiembre), jornadas científicas, y hasta promociones
del cafetín. Los de ciclos pasados dejan de servir en cuanto termina el periodo,
y para el histórico GUIA remite a indico.upeu.edu.pe — el enlace de cada
registro viaja en sus metadatos.
"""

from __future__ import annotations

from types import SimpleNamespace

from guia.services.harvester import _anio_del_item


def _con_fecha(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(starts_at=SimpleNamespace(**kwargs), date=None)


class TestExtraerElAnio:
    def test_lo_saca_de_year_int(self) -> None:
        assert _anio_del_item(_con_fecha(year_int=2026)) == 2026

    def test_lo_saca_de_year(self) -> None:
        assert _anio_del_item(_con_fecha(year=2025)) == 2025

    def test_lo_saca_de_una_fecha_en_texto(self) -> None:
        assert _anio_del_item(_con_fecha(raw="2026-09-10T07:30:00")) == 2026

    def test_sin_fecha_devuelve_none(self) -> None:
        """Y el harvester conserva esos: mejor indexar algo dudoso que perderlo
        por un campo que la fuente no rellenó."""
        assert _anio_del_item(SimpleNamespace(starts_at=None, date=None)) is None

    def test_una_fecha_ilegible_no_revienta(self) -> None:
        assert _anio_del_item(_con_fecha(raw="sin fecha conocida")) is None


class TestElCriterioDeDescarte:
    """Reproduce la decisión del bucle, que es lo que se quiere fijar."""

    @staticmethod
    def _se_descarta(anio_item: int | None, solo_anio: int | None) -> bool:
        if solo_anio is None:
            return False
        return anio_item is not None and anio_item != solo_anio

    def test_se_queda_el_del_anio_vigente(self) -> None:
        assert not self._se_descarta(2026, 2026)

    def test_se_va_el_de_ciclos_pasados(self) -> None:
        assert self._se_descarta(2025, 2026)
        assert self._se_descarta(2024, 2026)

    def test_sin_anio_se_conserva(self) -> None:
        assert not self._se_descarta(None, 2026)

    def test_sin_filtro_no_se_descarta_nada(self) -> None:
        assert not self._se_descarta(2019, None)
