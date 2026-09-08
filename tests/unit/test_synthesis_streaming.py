"""Síntesis emitida por fragmentos.

El modelo no se acelera: a los 13 tok/s medidos en el Mac Mini M4 el
2026-09-08, una respuesta de 600 tokens sigue tardando 48 s. Lo que cambia es
que el usuario ve texto desde el primer segundo en vez de un mensaje vacío.

Lo que estos tests protegen es que el canal adicional no altere el resultado:
la respuesta devuelta debe ser la misma con streaming o sin él, porque de ella
dependen la auditoría, el caché y el historial.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from guia.services.chat import ChatService


class _LLMQueEmite:
    """Adapter con streaming, como Ollama o NIM."""

    def __init__(self, trozos: list[str]) -> None:
        self._trozos = trozos
        self.config = MagicMock(default_model="modelo-de-prueba")
        self.recibido: dict[str, object] = {}

    def stream(self, messages, **kwargs):  # noqa: ANN001, ANN003, ANN202
        self.recibido = dict(kwargs)
        yield from self._trozos


@pytest.mark.asyncio
async def test_los_fragmentos_llegan_al_callback_en_orden() -> None:
    servicio = ChatService.__new__(ChatService)
    llm = _LLMQueEmite(["La quinua ", "es un ", "pseudocereal."])
    vistos: list[str] = []

    async def escribir(trozo: str) -> None:
        vistos.append(trozo)

    respuesta = await ChatService._synthesize_streaming(servicio, llm, [], escribir)

    assert vistos == ["La quinua ", "es un ", "pseudocereal."]
    assert respuesta.content == "La quinua es un pseudocereal."


@pytest.mark.asyncio
async def test_la_respuesta_completa_equivale_a_la_concatenacion() -> None:
    """De este contenido dependen auditoría, caché e historial."""
    servicio = ChatService.__new__(ChatService)
    trozos = ["uno ", "dos ", "tres"]
    llm = _LLMQueEmite(trozos)

    async def escribir(trozo: str) -> None:
        return None

    respuesta = await ChatService._synthesize_streaming(servicio, llm, [], escribir)

    assert respuesta.content == "".join(trozos)
    assert respuesta.model == "modelo-de-prueba"


@pytest.mark.asyncio
async def test_se_respetan_los_limites_de_generacion() -> None:
    servicio = ChatService.__new__(ChatService)
    llm = _LLMQueEmite(["x"])

    async def escribir(trozo: str) -> None:
        return None

    await ChatService._synthesize_streaming(servicio, llm, [], escribir)

    assert llm.recibido["max_tokens"] == 1024
    assert llm.recibido["temperature"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_un_fallo_a_media_emision_se_propaga() -> None:
    """El usuario ya vio texto parcial: fingir que todo fue bien sería peor."""

    class _LLMQueFalla(_LLMQueEmite):
        def stream(self, messages, **kwargs):  # noqa: ANN001, ANN003, ANN202
            yield "empieza bien"
            raise RuntimeError("se cortó la conexión")

    servicio = ChatService.__new__(ChatService)
    vistos: list[str] = []

    async def escribir(trozo: str) -> None:
        vistos.append(trozo)

    with pytest.raises(RuntimeError, match="se cortó"):
        await ChatService._synthesize_streaming(servicio, _LLMQueFalla([]), [], escribir)

    assert vistos == ["empieza bien"], "lo ya emitido debe haber llegado"


@pytest.mark.asyncio
async def test_el_callback_corre_en_el_bucle_de_eventos() -> None:
    """El generador del adapter es síncrono y se consume en un hilo.

    Si el callback se ejecutara en ese hilo, cualquier await de Chainlit
    reventaría. Debe volver al bucle principal.
    """
    servicio = ChatService.__new__(ChatService)
    bucle_principal = asyncio.get_running_loop()
    bucles: list[object] = []

    async def escribir(trozo: str) -> None:
        bucles.append(asyncio.get_running_loop())

    await ChatService._synthesize_streaming(servicio, _LLMQueEmite(["a", "b"]), [], escribir)

    assert bucles and all(b is bucle_principal for b in bucles)
