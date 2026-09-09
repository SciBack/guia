"""Gates de router pre-retriever (ADR-045).

LanguageGate: detecta quechua/idioma no-español e informa al usuario.
ToxicityGate: filtra queries abusivas antes del retriever.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateResult:
    """Resultado de evaluación de un gate."""

    passed: bool
    reason: str | None = None
    user_message: str | None = None


class LanguageGate:
    """Detecta idioma de la query con fasttext LID-176.

    No bloquea — siempre pasa. Agrega user_message informativo cuando
    detecta quechua u otro idioma no-español.
    """

    def __init__(self, *, enabled: bool = True, analizador: object | None = None) -> None:
        self._enabled = enabled
        # Cuando hay analizador, el modelo vive en el sidecar y este proceso no
        # carga nada. Sin él se usa el modelo local, que es lo que necesitan la
        # CLI y los tests.
        self._analizador = analizador

    def evaluate(self, query: str) -> GateResult:
        if not self._enabled:
            return GateResult(passed=True)

        try:
            if self._analizador is not None:
                lang, conf = self._analizador.idioma(query)  # type: ignore[attr-defined]
            else:
                from guia.nlp.language import detect_language

                lang, conf = detect_language(query)
        except Exception:
            return GateResult(passed=True)

        if lang == "es" or conf < 0.7:
            return GateResult(passed=True)

        if lang == "qu":
            return GateResult(
                passed=True,
                reason="quechua_detected",
                user_message=(
                    "Detecté que escribes en quechua. "
                    "Mis fuentes están principalmente en español, "
                    "pero puedo intentar ayudarte."
                ),
            )

        return GateResult(
            passed=True,
            reason=f"non_spanish:{lang}",
            user_message=(
                f"Detecté un idioma distinto al español ({lang}). "
                "Si deseas, puedes consultar en español para mejores resultados."
            ),
        )


class ToxicityGate:
    """Filtra queries con contenido tóxico usando Detoxify multilingual.

    Bloquea la query si el score supera el threshold configurable.
    Carga el modelo de forma lazy en el primer uso.
    """

    _CANNED_RESPONSE = (
        "No puedo procesar esa consulta. "
        "Si necesitas ayuda académica, reformula tu pregunta."
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        threshold: float = 0.85,
        analizador: object | None = None,
    ) -> None:
        self._enabled = enabled
        self._threshold = threshold
        self._analizador = analizador
        self._model: object | None = None
        self._model_loaded = False
        # Detoxify tarda ~15 s en cargar y pesa ~1,1 GB. Sin este cerrojo, una
        # consulta que llegaba mientras el warmup lo cargaba arrancaba UNA
        # SEGUNDA carga: dos copias compitiendo por RAM en una VM con 2 GB
        # libres, medido en 65 s de respuesta cuando esperar habria costado 15.
        self._load_lock = threading.Lock()

    def evaluate(self, query: str) -> GateResult:
        if not self._enabled or not query.strip():
            return GateResult(passed=True)

        score = self._predict(query)
        if score < self._threshold:
            return GateResult(passed=True)

        return GateResult(
            passed=False,
            reason=f"toxicity:{score:.2f}",
            user_message=self._CANNED_RESPONSE,
        )

    def _predict(self, query: str) -> float:
        if self._analizador is not None:
            # Una sola copia del modelo, en el sidecar. Medido: 712 MB que este
            # proceso ya no carga.
            return float(self._analizador.toxicidad(query))  # type: ignore[attr-defined]

        self._ensure_model()

        if self._model is None:
            return 0.0

        try:
            results = self._model.predict(query)  # type: ignore[union-attr]
            return float(max(results.values()))
        except Exception:
            return 0.0

    def _ensure_model(self) -> None:
        """Carga el modelo una sola vez, y espera si otro hilo ya lo esta cargando.

        La bandera se marca DESPUES de cargar, no antes. Marcarla antes tenia un
        efecto peor que la lentitud: mientras el warmup cargaba, una consulta
        concurrente veia ``_model_loaded=True`` con ``_model=None`` y se saltaba
        el filtro de toxicidad en silencio, sin dejar rastro en los logs.
        """
        if self._model_loaded:
            return
        with self._load_lock:
            if self._model_loaded:  # otro hilo lo cargo mientras esperabamos
                return
            try:
                from detoxify import Detoxify

                self._model = Detoxify("multilingual")
            except Exception:
                logger.warning("toxicity_model_load_failed", exc_info=True)
                self._model = None
            finally:
                self._model_loaded = True
