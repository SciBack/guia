"""Expansión de siglas académicas mediante diccionario JSON.

Carga `data/acronyms/es_academic.json` en el primer uso.
Si el archivo no existe, opera como identidad (sin error).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_DICT: dict[str, str] | None = None
_DICT_LOADED = False
_DEFAULT_DICT_PATH = Path("data/acronyms/es_academic.json")

_BUILTIN: dict[str, str] = {
    "IA": "inteligencia artificial",
    "ML": "machine learning",
    "TIC": "tecnologías de la información y comunicación",
    "TICS": "tecnologías de la información y comunicación",
    "NLP": "procesamiento de lenguaje natural",
    "NLU": "comprensión del lenguaje natural",
    "SIS": "sistema de información",
    "BD": "base de datos",
    "BBDD": "base de datos",
    "ERP": "sistema de planificación de recursos empresariales",
    "CRM": "gestión de relaciones con clientes",
    "SGBD": "sistema gestor de bases de datos",
    "POO": "programación orientada a objetos",
    "API": "interfaz de programación de aplicaciones",
}


def _load_dict(path: Path | None = None) -> dict[str, str]:
    global _DICT, _DICT_LOADED
    if _DICT_LOADED:
        return _DICT or {}
    _DICT_LOADED = True
    target = path or _DEFAULT_DICT_PATH
    if target.exists():
        try:
            with target.open(encoding="utf-8") as f:
                _DICT = {**_BUILTIN, **json.load(f)}
            return _DICT
        except Exception:
            pass
    _DICT = _BUILTIN.copy()
    return _DICT


def expand_acronyms(text: str, dict_path: Path | None = None) -> str:
    """Reemplaza siglas conocidas por su forma expandida."""
    acronym_dict = _load_dict(dict_path)
    if not acronym_dict:
        return text

    def replace(m: re.Match[str]) -> str:
        word = m.group(0)
        upper = word.upper()
        return acronym_dict.get(upper, word)

    pattern = r"\b[A-ZÁÉÍÓÚÜÑ]{2,6}s?\b"
    return re.sub(pattern, replace, text)
