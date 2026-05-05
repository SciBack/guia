"""Detección de idioma con fasttext LID-176.

Detecta quechua (qu), aymara (ay), y otros idiomas no-español.
Si fasttext no está disponible, retorna ("es", 1.0) como fallback seguro.
"""
from __future__ import annotations

_LID_MODEL = None
_LID_LOADED = False


def _get_model() -> object | None:
    global _LID_MODEL, _LID_LOADED
    if _LID_LOADED:
        return _LID_MODEL
    _LID_LOADED = True
    try:
        # El paquete fasttext-langdetect instala el módulo como `ftlangdetect`.
        # fasttext 0.9.3 tiene incompatibilidad con NumPy 2.x (ValueError en predict);
        # el except captura ambos casos y activa el fallback seguro.
        from ftlangdetect import detect
        detect("hola")
        _LID_MODEL = detect
    except Exception:
        _LID_MODEL = None
    return _LID_MODEL


def detect_language(text: str) -> tuple[str, float]:
    """Detecta el idioma del texto.

    Returns:
        Tupla (lang_code, confidence). lang_code sigue ISO 639-1.
        Retorna ("es", 1.0) si fasttext no está disponible.
    """
    if not text or len(text.strip()) < 3:
        return ("es", 1.0)

    model = _get_model()
    if model is None:
        return ("es", 1.0)

    try:
        result = model(text.strip().replace("\n", " "))
        lang = result.get("lang", "es")
        score = float(result.get("score", 0.0))
        return (lang, score)
    except Exception:
        return ("es", 1.0)
