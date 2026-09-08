"""Separación entre el clasificador de intención y el modelo local.

`fast_llm` hacía dos trabajos a la vez: clasificar la intención de cada consulta
y atender las consultas con datos personales. Son incompatibles — el segundo
obliga a que el modelo sea local, el primero a que sea barato — y con un solo
modelo cumpliendo ambos papeles, uno pierde. Medido en producción el
2026-09-08 con gemma4:12b: ~60 s por consulta solo en clasificar, y devolviendo
una categoría que el enrutador ni siquiera reconocía.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from guia.container import GUIAContainer


def _contenedor(proveedor: str) -> tuple[GUIAContainer, MagicMock]:
    ajustes = MagicMock()
    ajustes.guia_classifier_provider = proveedor
    contenedor = GUIAContainer.__new__(GUIAContainer)
    contenedor.settings = ajustes  # type: ignore[attr-defined]
    return contenedor, ajustes


@pytest.mark.parametrize(
    ("proveedor", "constructor"),
    [
        ("nim", "_build_nim"),
        ("claude", "_build_claude"),
        ("ollama", "_build_ollama_fast"),
    ],
)
def test_el_proveedor_configurado_es_el_que_clasifica(
    proveedor: str, constructor: str
) -> None:
    contenedor, _ = _contenedor(proveedor)

    with (
        patch.object(GUIAContainer, "_build_nim", return_value="nim"),
        patch.object(GUIAContainer, "_build_claude", return_value="claude"),
        patch.object(GUIAContainer, "_build_ollama_fast", return_value="ollama"),
    ):
        elegido = GUIAContainer._build_classifier(contenedor, "el-de-siempre")

    assert elegido == proveedor


def test_fast_conserva_el_comportamiento_anterior() -> None:
    """Nadie debe cambiar de clasificador solo por actualizar."""
    contenedor, _ = _contenedor("fast")

    assert GUIAContainer._build_classifier(contenedor, "el-de-siempre") == "el-de-siempre"


def test_el_default_es_fast() -> None:
    from guia.config import GUIASettings

    assert GUIASettings.model_fields["guia_classifier_provider"].default == "fast"


def test_un_proveedor_desconocido_no_deja_sin_clasificador() -> None:
    """Una errata en el .env degrada al de siempre, no rompe el enrutador."""
    contenedor, _ = _contenedor("inventado")

    assert GUIAContainer._build_classifier(contenedor, "el-de-siempre") == "el-de-siempre"


def test_clasificar_en_nim_no_toca_el_modelo_local() -> None:
    """La rama de PII sigue siendo local aunque el clasificador salga a la nube.

    Es el punto de toda la separación: mandar la clasificación fuera no debe
    arrastrar consigo las consultas con datos personales.
    """
    contenedor, _ = _contenedor("nim")
    local = object()

    with (
        patch.object(GUIAContainer, "_build_nim", return_value="nim") as nim,
        patch.object(GUIAContainer, "_build_ollama_fast") as ollama_fast,
    ):
        elegido = GUIAContainer._build_classifier(contenedor, local)

    assert elegido == "nim"
    assert elegido is not local
    nim.assert_called_once()
    ollama_fast.assert_not_called()
