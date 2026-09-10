"""Los lotes ceden el paso a las consultas de usuario.

Medido el 09-sep-2026 con una sola cola FIFO: una búsqueda que en reposo tarda
0,8 s tardó 11,4 s mientras se recosechaban 10.000 documentos, porque esperaba
detrás de todo lo que la cosecha había encolado.

Lo que estas pruebas fijan es el reparto de turnos, no la velocidad. Y también
fijan el límite honesto: una inferencia ya en marcha NO se puede desalojar, así
que lo que se consigue es que los lotes no se encolen por delante, no que se
interrumpan.
"""

from __future__ import annotations

import asyncio

import pytest

from guia.embeddings_sidecar import ColaDeInferencia


@pytest.fixture
def cola() -> ColaDeInferencia:
    """Una cola nueva por prueba: los primitivos de asyncio se atan al bucle."""
    return ColaDeInferencia()


async def _trabajo(cola: ColaDeInferencia, nombre: str, prioritaria: bool,
                   orden: list[str], dur: float = 0.02) -> None:
    async with cola.turno(prioritaria=prioritaria):
        orden.append(nombre)
        await asyncio.sleep(dur)


class TestPrioridad:
    @pytest.mark.asyncio
    async def test_la_interactiva_adelanta_a_los_lotes_encolados(
        self, cola: ColaDeInferencia
    ) -> None:
        """El caso que importa: cosecha en marcha, llega un usuario."""
        orden: list[str] = []

        # un lote ya ocupando el turno
        primero = asyncio.create_task(
            _trabajo(cola, "lote-1", False, orden, dur=0.05)
        )
        await asyncio.sleep(0.01)

        # se encolan más lotes y, después, una consulta de usuario
        lotes = [
            asyncio.create_task(_trabajo(cola, f"lote-{i}", False, orden))
            for i in range(2, 6)
        ]
        await asyncio.sleep(0.005)
        usuario = asyncio.create_task(_trabajo(cola, "USUARIO", True, orden))

        await asyncio.gather(primero, usuario, *lotes)

        # el usuario no espera a los cuatro lotes: entra justo tras el que ya corría
        assert orden[0] == "lote-1"
        posicion = orden.index("USUARIO")
        assert orden[1] == "USUARIO", f"el usuario quedó en la posición {posicion}: {orden}"

    @pytest.mark.asyncio
    async def test_varias_interactivas_pasan_antes_que_cualquier_lote(
        self, cola: ColaDeInferencia
    ) -> None:
        orden: list[str] = []

        ocupado = asyncio.create_task(
            _trabajo(cola, "lote-inicial", False, orden, dur=0.05)
        )
        await asyncio.sleep(0.01)
        lotes = [
            asyncio.create_task(_trabajo(cola, f"lote-{i}", False, orden)) for i in range(3)
        ]
        await asyncio.sleep(0.005)
        usuarios = [
            asyncio.create_task(_trabajo(cola, f"USUARIO-{i}", True, orden)) for i in range(3)
        ]

        await asyncio.gather(ocupado, *usuarios, *lotes)

        posiciones_usuario = [i for i, n in enumerate(orden) if n.startswith("USUARIO")]
        posiciones_lote = [
            i for i, n in enumerate(orden)
            if n.startswith("lote-") and n != "lote-inicial"
        ]
        assert max(posiciones_usuario) < min(posiciones_lote), orden

    @pytest.mark.asyncio
    async def test_sin_interactivas_los_lotes_corren_sin_estorbo(
        self, cola: ColaDeInferencia
    ) -> None:
        """Ceder no puede convertirse en pasar hambre."""
        orden: list[str] = []

        await asyncio.gather(
            *[_trabajo(cola, f"lote-{i}", False, orden) for i in range(5)]
        )

        assert len(orden) == 5

    @pytest.mark.asyncio
    async def test_el_turno_se_libera_aunque_el_trabajo_falle(
        self, cola: ColaDeInferencia
    ) -> None:
        """Una excepción no puede dejar la cola bloqueada para siempre."""
        orden: list[str] = []

        with pytest.raises(RuntimeError):
            async with cola.turno(prioritaria=True):
                raise RuntimeError("fallo dentro de la inferencia")

        # el siguiente entra sin colgarse
        await asyncio.wait_for(_trabajo(cola, "siguiente", True, orden), timeout=1.0)
        assert orden == ["siguiente"]

    @pytest.mark.asyncio
    async def test_sigue_habiendo_una_sola_inferencia_a_la_vez(
        self, cola: ColaDeInferencia
    ) -> None:
        """La sesión ONNX se comparte: dos forwards simultáneos la romperían."""
        simultaneas = 0
        pico = 0

        async def medir(prioritaria: bool) -> None:
            nonlocal simultaneas, pico
            async with cola.turno(prioritaria=prioritaria):
                simultaneas += 1
                pico = max(pico, simultaneas)
                await asyncio.sleep(0.01)
                simultaneas -= 1

        await asyncio.gather(*[medir(i % 2 == 0) for i in range(8)])

        assert pico == 1, f"hubo {pico} inferencias a la vez"


class TestElHarvesterUsaLaColaDeLotes:
    """La cosecha tiene que pedir por la puerta de atrás, o nada de esto sirve."""

    def test_anade_el_prefijo_a_la_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from guia.cli import _usar_cola_de_lotes

        monkeypatch.setenv("E5_OLLAMA_BASE_URL", "http://embeddings:11434")
        _usar_cola_de_lotes()

        import os

        assert os.environ["E5_OLLAMA_BASE_URL"] == "http://embeddings:11434/lote"

    def test_no_lo_duplica_si_ya_esta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from guia.cli import _usar_cola_de_lotes

        monkeypatch.setenv("E5_OLLAMA_BASE_URL", "http://embeddings:11434/lote")
        _usar_cola_de_lotes()

        import os

        assert os.environ["E5_OLLAMA_BASE_URL"] == "http://embeddings:11434/lote"

    def test_sin_url_configurada_no_inventa_ninguna(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from guia.cli import _usar_cola_de_lotes

        monkeypatch.delenv("E5_OLLAMA_BASE_URL", raising=False)
        _usar_cola_de_lotes()

        import os

        assert "E5_OLLAMA_BASE_URL" not in os.environ
