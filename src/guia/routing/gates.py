"""Gates de router pre-retriever (ADR-045).

LanguageGate: detecta quechua/idioma no-español e informa al usuario.
ToxicityGate: filtra queries abusivas antes del retriever.
"""
from __future__ import annotations

from dataclasses import dataclass


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

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    def evaluate(self, query: str) -> GateResult:
        if not self._enabled:
            return GateResult(passed=True)

        try:
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

    def __init__(self, *, enabled: bool = True, threshold: float = 0.85) -> None:
        self._enabled = enabled
        self._threshold = threshold
        self._model: object | None = None
        self._model_loaded = False

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
        if not self._model_loaded:
            self._model_loaded = True
            try:
                from detoxify import Detoxify
                self._model = Detoxify("multilingual")
            except Exception:
                self._model = None

        if self._model is None:
            return 0.0

        try:
            results = self._model.predict(query)  # type: ignore[union-attr]
            return float(max(results.values()))
        except Exception:
            return 0.0
