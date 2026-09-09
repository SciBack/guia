"""Cuándo GUIA pregunta sobre qué tema, en vez de buscar a ciegas.

Caso real del 09-sep-2026, probando en el navegador:

    usuario: estoy buscando algo para mi tesis
    GUIA:    5 resultados — "Guía para elaborar una tesis",
             "La tesis doctoral", "7 Pasos para elaborar una tesis"...

Buscó la palabra "tesis" en el catálogo y devolvió libros sobre *cómo redactar*
una tesis. Ninguno servía: el usuario nunca dijo de qué trata la suya. Buscar
sin tema no da un resultado imperfecto, da uno que no responde a nada.
"""

from __future__ import annotations

import pytest

from guia.services.chat import _pregunta_por_el_tema, _sin_tema


@pytest.mark.parametrize(
    "consulta",
    [
        "estoy buscando algo para mi tesis",
        "necesito información",
        "sí, quiero información académica",
        "quiero libros",
        "busco material",
        "ayúdame",
        "necesito bibliografía para mi trabajo",
        "recomiéndame algo",
        "dame documentos",
        # Encontrados probando en el navegador el 09-sep-2026: la primera
        # version de la lista no los cubria y GUIA se iba a buscar "tarea".
        "necesito hacer mi tarea",
        "tengo que hacer un ensayo",
        "necesito preparar mi exposición",
        "es para mi monografía",
        "tengo un trabajo final",
    ],
)
def test_una_peticion_sin_tema_se_detecta(consulta: str) -> None:
    assert _sin_tema(consulta), consulta


@pytest.mark.parametrize(
    "consulta",
    [
        "tesis sobre contaminación del lago Titicaca",
        "libros de nutrición infantil",
        "explícame qué es la quinua",
        "nutrición infantil",
        "hábitos de estudio y rendimiento académico",
        "necesito bibliografía sobre economía circular",
        "busco tesis de machine learning",
        "¿qué tesis hay sobre IA?",
        "tesis de ADN",
        # El andamiaje no puede comerse el tema cuando SI esta
        "necesito hacer mi tarea de nutrición",
        "un ensayo sobre la quinua",
    ],
)
def test_una_peticion_con_tema_pasa_a_buscar(consulta: str) -> None:
    """El tema puede venir con andamiaje alrededor; lo que importa es que esté."""
    assert not _sin_tema(consulta), consulta


def test_la_diferencia_esta_en_el_tema_no_en_la_longitud() -> None:
    """Una frase larga sin tema sigue sin tenerlo; una corta con tema, sí."""
    assert _sin_tema("hola, necesito por favor algo de información para mi trabajo")
    assert not _sin_tema("quinua")


def test_las_tildes_no_cambian_la_deteccion() -> None:
    assert _sin_tema("necesito informacion") == _sin_tema("necesito información")


def test_la_pregunta_dice_que_puede_buscar_y_da_ejemplos() -> None:
    """Preguntar "¿sobre qué?" a secas deja al usuario igual de perdido."""
    texto = _pregunta_por_el_tema()

    assert "tema" in texto.lower()
    assert "biblioteca" in texto.lower()
    assert "por ejemplo" in texto.lower()
