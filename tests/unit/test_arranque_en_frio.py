"""La ventana entre "el proceso levanta" y "los modelos estan cargados".

Medido en produccion el 09-sep-2026, recreando el contenedor de la API:

    /health responde a t+7s     <- el contenedor figuraba sano
    consulta en t+2s   65.17s
    consulta en t+20s   0.44s
    warmup_complete en t+19s

Los 65 s no son "esperar al warmup": esperarlo habria costado 19. Eran dos
cargas del mismo modelo compitiendo por una VM con 2 GB libres, porque la
bandera de "ya cargado" se marcaba ANTES de terminar de cargar.
"""

from __future__ import annotations

import threading

from guia.routing.gates import ToxicityGate


class TestUnaSolaCargaDelModelo:
    def test_dos_hilos_a_la_vez_cargan_el_modelo_una_sola_vez(self) -> None:
        """El segundo hilo espera al primero en vez de arrancar otra carga."""
        gate = ToxicityGate(enabled=True, threshold=0.85)
        cargas = []
        empezar = threading.Barrier(4)

        class ModeloLento:
            def __init__(self, _nombre: str) -> None:
                cargas.append(1)
                import time

                time.sleep(0.15)  # simula los ~15 s reales

            def predict(self, _texto: str) -> dict[str, float]:
                return {"toxicity": 0.0}

        import sys
        import types

        modulo = types.ModuleType("detoxify")
        modulo.Detoxify = ModeloLento  # type: ignore[attr-defined]
        sys.modules["detoxify"] = modulo
        try:
            def trabajo() -> None:
                empezar.wait()
                gate.evaluate("una consulta cualquiera")

            hilos = [threading.Thread(target=trabajo) for _ in range(3)]
            for h in hilos:
                h.start()
            empezar.wait()
            for h in hilos:
                h.join(timeout=10)
        finally:
            del sys.modules["detoxify"]

        assert sum(cargas) == 1, f"se cargo {sum(cargas)} veces, deberia ser 1"

    def test_la_bandera_se_marca_despues_de_cargar_no_antes(self) -> None:
        """Marcarla antes hacia que una consulta concurrente se saltara el
        filtro de toxicidad en silencio: veia "cargado" con el modelo a None."""
        gate = ToxicityGate(enabled=True, threshold=0.85)
        visto_durante_la_carga: list[tuple[bool, bool]] = []

        class ModeloQueMira:
            def __init__(self, _nombre: str) -> None:
                # Estado observado desde dentro de la propia carga.
                visto_durante_la_carga.append(
                    (gate._model_loaded, gate._model is None)
                )

            def predict(self, _texto: str) -> dict[str, float]:
                return {"toxicity": 0.0}

        import sys
        import types

        modulo = types.ModuleType("detoxify")
        modulo.Detoxify = ModeloQueMira  # type: ignore[attr-defined]
        sys.modules["detoxify"] = modulo
        try:
            gate.evaluate("hola")
        finally:
            del sys.modules["detoxify"]

        cargado, sin_modelo = visto_durante_la_carga[0]
        assert not cargado, "la bandera ya estaba puesta mientras cargaba"
        assert sin_modelo
        assert gate._model_loaded, "al terminar si debe quedar marcada"


class TestSondaDeReadiness:
    def test_no_esta_lista_hasta_que_el_warmup_termina(self) -> None:
        from guia.services.warmup import _EstadoDeWarmup

        estado = _EstadoDeWarmup()
        assert not estado.done
        estado.marcar_listo()
        assert estado.done
