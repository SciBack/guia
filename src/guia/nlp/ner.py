"""Extracción de entidades nombradas con spaCy es_core_news_lg.

Detecta PER (personas/autores), ORG (instituciones), LOC (lugares).
Si spaCy no está disponible, retorna dict vacío sin error.
"""
from __future__ import annotations

import threading

from guia.nlp._carga import CargaUnica

_CARGAS: dict[str, CargaUnica[object]] = {}
_CARGAS_LOCK = threading.Lock()


def _get_nlp(model: str = "es_core_news_lg") -> object | None:
    """Carga el modelo de spaCy una sola vez por nombre.

    es_core_news_lg tarda ~10 s en abrir. Sin el cerrojo, la consulta que caia
    durante el warmup lo abria por su cuenta en paralelo.
    """
    carga = _CARGAS.get(model)
    if carga is None:
        with _CARGAS_LOCK:
            carga = _CARGAS.get(model)
            if carga is None:
                def _cargar() -> object:
                    import spacy

                    return spacy.load(model)

                carga = CargaUnica(_cargar)
                _CARGAS[model] = carga
    return carga.obtener()


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
