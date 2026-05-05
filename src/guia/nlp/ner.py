"""Extracción de entidades nombradas con spaCy es_core_news_lg.

Detecta PER (personas/autores), ORG (instituciones), LOC (lugares).
Si spaCy no está disponible, retorna dict vacío sin error.
"""
from __future__ import annotations

_NLP = None
_NLP_LOADED = False


def _get_nlp(model: str = "es_core_news_lg") -> object | None:
    global _NLP, _NLP_LOADED
    if _NLP_LOADED:
        return _NLP
    _NLP_LOADED = True
    try:
        import spacy
        _NLP = spacy.load(model)
    except Exception:
        _NLP = None
    return _NLP


def extract_entities(
    text: str,
    model: str = "es_core_news_lg",
    min_confidence: float = 0.0,
) -> dict[str, list[str]]:
    """Extrae entidades nombradas relevantes para filtros de búsqueda.

    Returns:
        Dict con listas por tipo: {"PER": [...], "ORG": [...], "LOC": [...]}
    """
    nlp = _get_nlp(model)
    if nlp is None:
        return {}

    try:
        doc = nlp(text)
    except Exception:
        return {}

    result: dict[str, list[str]] = {}
    for ent in doc.ents:
        if ent.label_ in ("PER", "ORG", "LOC"):
            if ent.label_ not in result:
                result[ent.label_] = []
            name = ent.text.strip()
            if name and name not in result[ent.label_]:
                result[ent.label_].append(name)

    return result
