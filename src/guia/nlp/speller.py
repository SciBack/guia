"""Corrección ortográfica con SymSpellPy.

Si el diccionario no existe, opera como identidad (sin error).
El diccionario es un archivo de frecuencias de palabras en español.
"""
from __future__ import annotations

from pathlib import Path

_SYMSPELL = None
_SYMSPELL_LOADED = False
_DEFAULT_DICT_PATH = Path("data/symspell/es_full.txt")


def _get_symspell(dict_path: Path | None = None) -> object | None:
    global _SYMSPELL, _SYMSPELL_LOADED
    if _SYMSPELL_LOADED:
        return _SYMSPELL
    _SYMSPELL_LOADED = True
    target = dict_path or _DEFAULT_DICT_PATH
    if not target.exists():
        return None
    try:
        from symspellpy import SymSpell
        sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        sym.load_dictionary(str(target), term_index=0, count_index=1)
        _SYMSPELL = sym
    except Exception:
        _SYMSPELL = None
    return _SYMSPELL


def correct_typos(text: str, dict_path: Path | None = None) -> str:
    """Corrige errores ortográficos en el texto usando SymSpellPy.

    Procesa palabra por palabra para preservar el contexto de la query.
    Si SymSpellPy no está disponible o no hay diccionario, retorna el texto sin cambios.
    """
    sym = _get_symspell(dict_path)
    if sym is None:
        return text

    try:
        from symspellpy import Verbosity
        words = text.split()
        corrected: list[str] = []
        for word in words:
            if len(word) <= 3 or word.isupper() or word.isdigit() or "://" in word:
                corrected.append(word)
                continue
            suggestions = sym.lookup(word.lower(), Verbosity.CLOSEST, max_edit_distance=2)
            if suggestions and suggestions[0].distance > 0:
                fixed = suggestions[0].term
                if word[0].isupper():
                    fixed = fixed.capitalize()
                corrected.append(fixed)
            else:
                corrected.append(word)
        return " ".join(corrected)
    except Exception:
        return text
