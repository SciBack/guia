"""El diccionario se recorta a las palabras mas frecuentes.

El fichero de hermitdave trae 1.202.520 entradas ordenadas por frecuencia, y
construir su indice de borrados costaba ~45 s en cada arranque de la VM. La
cola de esa lista son erratas, nombres propios y formas rarisimas que no
aparecen en una consulta de biblioteca.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def diccionario(tmp_path: Path) -> Path:
    """Diccionario de juguete, ya ordenado de mas a menos frecuente."""
    ruta = tmp_path / "es_full.txt"
    ruta.write_text(
        "\n".join(f"palabra{i} {1_000_000 - i}" for i in range(500)),
        encoding="utf-8",
    )
    return ruta


def _speller_con(monkeypatch: pytest.MonkeyPatch, cache: Path, maximo: str):
    monkeypatch.setenv("GUIA_SPELLER_MAX_ENTRIES", maximo)
    monkeypatch.setenv("GUIA_NLP_CACHE_DIR", str(cache))
    import guia.nlp.speller as speller

    return importlib.reload(speller)


class TestRecorte:
    def test_se_queda_con_las_n_mas_frecuentes(
        self, diccionario: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speller = _speller_con(monkeypatch, tmp_path / "cache", "100")

        recortado = speller._recortar(diccionario)

        lineas = recortado.read_text(encoding="utf-8").splitlines()
        assert len(lineas) == 100
        assert lineas[0].startswith("palabra0 ")  # la mas frecuente sobrevive
        assert lineas[-1].startswith("palabra99 ")

    def test_cero_significa_el_diccionario_entero(
        self, diccionario: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speller = _speller_con(monkeypatch, tmp_path / "cache", "0")

        assert speller._recortar(diccionario) == diccionario

    def test_el_recorte_no_toca_el_original(
        self, diccionario: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Subir el limite despues no puede exigir volver a descargar nada."""
        speller = _speller_con(monkeypatch, tmp_path / "cache", "50")
        antes = diccionario.read_text(encoding="utf-8")

        recortado = speller._recortar(diccionario)

        assert recortado != diccionario
        assert diccionario.read_text(encoding="utf-8") == antes

    def test_se_reutiliza_el_recorte_ya_generado(
        self, diccionario: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speller = _speller_con(monkeypatch, tmp_path / "cache", "100")

        primero = speller._recortar(diccionario)
        primero.write_text("marca\n", encoding="utf-8")
        segundo = speller._recortar(diccionario)

        assert segundo == primero
        assert segundo.read_text(encoding="utf-8") == "marca\n"

    def test_si_no_puede_escribir_usa_el_completo(
        self, diccionario: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un recorte que falla debe degradar a lento-pero-correcto."""
        speller = _speller_con(monkeypatch, tmp_path / "cache", "100")
        monkeypatch.setattr(
            speller.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("ro"))
        )

        assert speller._recortar(diccionario) == diccionario


class TestNombreDelIndiceCacheado:
    def test_el_tamano_forma_parte_del_nombre(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin esto, cambiar el recorte reutilizaria el indice del tamano viejo
        y la configuracion nueva no tendria ningun efecto observable."""
        cache = tmp_path / "cache"
        con_200k = _speller_con(monkeypatch, cache, "200000")._PICKLE_PATH
        con_50k = _speller_con(monkeypatch, cache, "50000")._PICKLE_PATH
        completo = _speller_con(monkeypatch, cache, "0")._PICKLE_PATH

        assert con_200k != con_50k != completo
        assert "top200000" in con_200k.name
        assert "full" in completo.name
