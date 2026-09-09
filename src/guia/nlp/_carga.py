"""Carga perezosa de modelos pesados, una sola vez y sin carreras.

Los cuatro modelos NLP (idioma, toxicidad, spaCy, SymSpell) repetian el mismo
patron roto: marcaban la bandera de "ya cargado" ANTES de cargar y sin cerrojo.
Eso daba dos fallos a la vez cuando el warmup y una consulta coincidian —lo que
pasa en cada despliegue:

* la consulta no esperaba al warmup, arrancaba su PROPIA carga del mismo modelo
  (dos copias compitiendo por RAM en una VM con 2 GB libres);
* y si miraba entre medias veia "cargado" con el modelo a ``None``, asi que
  seguia adelante con el fallback silencioso, sin dejar rastro en los logs.

Medido el 09-sep-2026: consulta a t+2s del arranque, 65 s; a t+20s, 0,44 s.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class CargaUnica(Generic[T]):
    """Envuelve un cargador caro para que se ejecute exactamente una vez.

    Quien llegue mientras otro carga espera a que termine, en vez de empezar
    una carga paralela. Si el cargador falla, se registra el fallo y se
    devuelve ``None`` para siempre: los llamantes tienen fallback seguro y no
    tiene sentido reintentar una carga de 15 s en cada consulta.
    """

    def __init__(self, cargador: Callable[[], T]) -> None:
        self._cargador = cargador
        self._valor: T | None = None
        self._cargado = False
        self._cerrojo = threading.Lock()

    @property
    def cargado(self) -> bool:
        return self._cargado

    def obtener(self) -> T | None:
        if self._cargado:
            return self._valor
        with self._cerrojo:
            if self._cargado:  # otro hilo lo cargo mientras esperabamos
                return self._valor
            try:
                self._valor = self._cargador()
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "carga_de_modelo_fallida cargador=%s",
                    getattr(self._cargador, "__name__", self._cargador),
                    exc_info=True,
                )
                self._valor = None
            finally:
                # DESPUES de cargar, nunca antes.
                self._cargado = True
        return self._valor
