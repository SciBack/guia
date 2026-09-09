"""Cuándo GUIA responde con un listado y cuándo redacta.

El umbral original miraba solo **cuántas** fuentes había, no **qué** se
preguntó. Medido en producción el 2026-09-09: "explícame en dos frases qué es
la quinua" devolvía cinco tesis sobre derivados de quinua, porque el buscador
encontró cinco cosas y eso bastaba para clasificarlo como listado.
"""

from __future__ import annotations

import pytest

from guia.domain.chat import Intent, Source
from guia.services.chat import _classify_answer_type, _pide_explicacion


def _fuentes(n: int) -> list[Source]:
    return [
        Source(id=f"dspace:{i}", title=f"Tesis {i}", url=f"https://x/{i}", source_type="dspace")
        for i in range(n)
    ]


# ── El caso que motivó el cambio ─────────────────────────────────────────────


def test_una_pregunta_se_responde_redactando() -> None:
    tipo = _classify_answer_type(
        Intent.RESEARCH, _fuentes(5), "explícame en dos frases qué es la quinua"
    )

    assert tipo == "narrative"


def test_una_busqueda_sigue_devolviendo_listado() -> None:
    """Para "tesis sobre X", la lista real es mejor respuesta que un párrafo."""
    tipo = _classify_answer_type(
        Intent.RESEARCH, _fuentes(5), "tesis sobre contaminación del lago Titicaca"
    )

    assert tipo == "list"


def test_un_tema_suelto_sigue_devolviendo_listado() -> None:
    """El listado es el comportamiento por defecto, y además no cuesta modelo."""
    assert _classify_answer_type(Intent.RESEARCH, _fuentes(5), "nutrición infantil") == "list"


# ── Reconocer la pregunta ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "consulta",
    [
        "qué es la quinua",
        "que es la quinua",  # sin tilde
        "QUÉ ES LA QUINUA",  # mayúsculas
        "explícame la fotosíntesis",
        "explicame la fotosintesis",
        "cómo funciona el blockchain",
        "por qué se contamina el lago",
        "resume los hallazgos sobre metales pesados",
        "compara las metodologías de esos trabajos",
        "en qué consiste la economía circular",
        "para qué sirve la kiwicha",
    ],
)
def test_se_reconocen_las_formas_de_preguntar(consulta: str) -> None:
    assert _pide_explicacion(consulta), consulta


@pytest.mark.parametrize(
    "consulta",
    [
        "tesis sobre quinua",
        "libros de nutrición",
        "artículos de machine learning",
        "nutrición infantil",
        "contaminación del lago Titicaca",
    ],
)
def test_una_busqueda_no_se_confunde_con_una_pregunta(consulta: str) -> None:
    assert not _pide_explicacion(consulta), consulta


def test_la_pregunta_tambien_se_detecta_en_medio() -> None:
    """El usuario no siempre empieza por la pregunta."""
    assert _pide_explicacion("del lago Titicaca, explícame la contaminación")


# ── Lo que no cambia ─────────────────────────────────────────────────────────


def test_con_pocas_fuentes_siempre_se_redacta() -> None:
    assert _classify_answer_type(Intent.RESEARCH, _fuentes(2), "tesis sobre quinua") == "narrative"


def test_otros_intents_no_producen_listados() -> None:
    assert _classify_answer_type(Intent.CAMPUS, _fuentes(5), "mis notas") == "narrative"


def test_sin_consulta_se_conserva_el_comportamiento_anterior() -> None:
    """El parámetro es opcional: quien no lo pase no cambia de comportamiento."""
    assert _classify_answer_type(Intent.RESEARCH, _fuentes(5)) == "list"
