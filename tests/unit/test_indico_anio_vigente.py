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


def _evento(anio: int) -> SimpleNamespace:
    """Como lo guarda Event: un EventDatetime con un datetime dentro."""
    from datetime import datetime

    return SimpleNamespace(
        starts_at=SimpleNamespace(when=datetime(anio, 9, 10, 7, 30)), date=None
    )


class TestExtraerElAnio:
    def test_lo_saca_del_when_de_un_evento(self) -> None:
        """Event.starts_at es un EventDatetime con un datetime en ``when``.
        Mirar solo los campos de publicación dejaba el filtro sin efecto: la
        cosecha del 10-sep-2026 descartó 0 de 533 sin dar ningún error."""
        assert _anio_del_item(_evento(2026)) == 2026

    def test_lo_saca_de_year_int_en_una_publicacion(self) -> None:
        assert _anio_del_item(_con_fecha(year_int=2026)) == 2026

    def test_una_fecha_que_solo_sabe_imprimirse_tambien_vale(self) -> None:
        """Reserva para fuentes que traigan la fecha como texto."""

        class FechaTexto:
            def __str__(self) -> str:
                return "2026-09-10T07:30:00"

        assert _anio_del_item(SimpleNamespace(starts_at=FechaTexto(), date=None)) == 2026

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
