"""Elección del proveedor que redacta la respuesta final.

Estaba cableado a Claude. El 2026-09-08 se agotó el saldo de Anthropic, su API
empezó a devolver 400 con un mensaje de facturación, y GUIA dejó de responder
por completo: no había a qué caer. Estos tests fijan que el proveedor sea una
decisión de configuración y que el default no cambie para nadie.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from guia.container import GUIAContainer


def _contenedor(proveedor: str | None = None) -> GUIAContainer:
    """Construye el container sin tocar red ni base de datos."""
    ajustes = MagicMock()
    ajustes.guia_llm_mode = "HYBRID"
    ajustes.guia_synthesis_provider = proveedor or "claude"
    return GUIAContainer.__new__(GUIAContainer), ajustes  # type: ignore[return-value]


@pytest.mark.parametrize(
    ("proveedor", "constructor"),
    [
        ("claude", "_build_claude"),
        ("nim", "_build_nim"),
        ("ollama", "_build_ollama"),
    ],
)
def test_el_proveedor_configurado_es_el_que_se_construye(
    proveedor: str, constructor: str
) -> None:
    contenedor, ajustes = _contenedor(proveedor)
    contenedor.settings = ajustes

    with (
        patch.object(GUIAContainer, "_build_claude", return_value="claude") as claude,
        patch.object(GUIAContainer, "_build_nim", return_value="nim") as nim,
        patch.object(GUIAContainer, "_build_ollama", return_value="ollama") as ollama,
    ):
        resultado = GUIAContainer._build_synthesis(contenedor)

    llamados = {"_build_claude": claude, "_build_nim": nim, "_build_ollama": ollama}
    assert resultado == proveedor
    llamados[constructor].assert_called_once()
    for nombre, mock in llamados.items():
        if nombre != constructor:
            mock.assert_not_called()


def test_el_default_sigue_siendo_claude() -> None:
    """Nadie debe cambiar de proveedor por actualizar: el default no se mueve."""
    from guia.config import GUIASettings

    assert GUIASettings.model_fields["guia_synthesis_provider"].default == "claude"


def test_un_proveedor_desconocido_cae_a_claude() -> None:
    """Un valor mal escrito en el .env no debe dejar a GUIA sin redactor."""
    contenedor, ajustes = _contenedor("gemini-inventado")
    contenedor.settings = ajustes

    with patch.object(GUIAContainer, "_build_claude", return_value="claude") as claude:
        assert GUIAContainer._build_synthesis(contenedor) == "claude"

    claude.assert_called_once()
