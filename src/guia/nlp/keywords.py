"""Expansión de keywords con YAKE (keyword extraction unsupervised).

Se usa como fallback cuando el retrieval devuelve 0 hits:
extrae keywords del query y amplía la búsqueda.
"""
from __future__ import annotations


def expand_keywords(text: str, max_keywords: int = 5, language: str = "es") -> list[str]:
    """Extrae keywords relevantes del texto con YAKE.

    Returns:
        Lista de keywords ordenadas por relevancia (score menor = más relevante).
        Lista vacía si YAKE no está disponible o el texto es muy corto.
    """
    if len(text.split()) < 3:
        return []

    try:
        import yake
        kw_extractor = yake.KeywordExtractor(
            lan=language,
            n=2,
            dedupLim=0.9,
            top=max_keywords,
            features=None,
        )
        keywords = kw_extractor.extract_keywords(text)
        return [kw for kw, score in keywords]
    except Exception:
        return []
