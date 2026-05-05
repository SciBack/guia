"""Extracción de filtros de fecha desde texto en español.

Convierte expresiones temporales en filtros estructurados OpenSearch range.
Opera sin LLM usando dateparser.
"""
from __future__ import annotations

import re
from datetime import date


def extract_date_filters(text: str) -> dict | None:
    """Extrae filtros de fecha del texto de la query.

    Returns:
        dict con claves 'gte' y/o 'lte' (formato ISO date string), o None si
        no se detectan referencias temporales.
    """
    text_lower = text.lower()
    today = date.today()
    current_year = today.year

    if re.search(r"\baño\s+(pasado|anterior)\b", text_lower):
        y = current_year - 1
        return {"gte": f"{y}-01-01", "lte": f"{y}-12-31"}

    if re.search(r"\b(este\s+año|año\s+actual|año\s+en\s+curso)\b", text_lower):
        return {"gte": f"{current_year}-01-01", "lte": f"{current_year}-12-31"}

    m = re.search(r"\búltimos?\s+(\d+)\s+años?\b", text_lower)
    if m:
        n = int(m.group(1))
        start_year = current_year - n
        return {"gte": f"{start_year}-01-01"}

    m = re.search(r"\b(?:desde|a\s+partir\s+de)\s+(\d{4})\b", text_lower)
    if m:
        return {"gte": f"{m.group(1)}-01-01"}

    m = re.search(r"\b(?:antes\s+de|hasta)\s+(\d{4})\b", text_lower)
    if m:
        return {"lte": f"{m.group(1)}-12-31"}

    m = re.search(r"\b(\d{4})\s*[-–a]\s*(\d{4})\b", text)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if 1900 < y1 <= y2 <= current_year + 1:
            return {"gte": f"{y1}-01-01", "lte": f"{y2}-12-31"}

    m = re.search(r"\b(?:del|en|año)\s+(\d{4})\b", text_lower)
    if m:
        y = int(m.group(1))
        if 1900 < y <= current_year + 1:
            return {"gte": f"{y}-01-01", "lte": f"{y}-12-31"}

    try:
        import dateparser
        parsed = dateparser.parse(
            text,
            languages=["es"],
            settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False},
        )
        if parsed and 1900 < parsed.year <= current_year + 1:
            return {"gte": f"{parsed.year}-01-01", "lte": f"{parsed.year}-12-31"}
    except Exception:
        pass

    return None
