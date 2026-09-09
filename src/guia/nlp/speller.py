"""Corrección ortográfica con SymSpellPy.

Si el diccionario no existe, intenta descargarlo automáticamente desde
hermitdave/FrequencyWords (licencia CC BY 4.0). Si la descarga falla,
opera como identidad (sin error).
"""
from __future__ import annotations

import threading

import logging
import os

from guia.nlp._carga import CargaUnica

import urllib.request
from pathlib import Path

_DEFAULT_DICT_PATH = Path("data/symspell/es_full.txt")
#: Indice ya construido. Va al volumen compartido (el mismo de fastembed) para
#: sobrevivir a los recreates; sin el, cada despliegue reconstruia 1,2 millones
#: de entradas dentro de la primera consulta del primer usuario.
_PICKLE_DIR = os.getenv("GUIA_NLP_CACHE_DIR", "/tmp/fastembed_cache").strip()
_PICKLE_PATH = Path(_PICKLE_DIR) / "symspell_es_ed2_p7.pkl" if _PICKLE_DIR else None
_DICT_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords"
    "/master/content/2018/es/es_full.txt"
)


def _download_dict(target: Path) -> bool:
    """Descarga el diccionario de frecuencias español si no existe."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_DICT_URL, target)  # noqa: S310
        return target.exists() and target.stat().st_size > 1000
    except Exception:
        return False


_CARGA: CargaUnica[object] | None = None
_CARGA_LOCK = threading.Lock()


def _get_symspell(dict_path: Path | None = None) -> object | None:
    """Carga el diccionario una sola vez, esperando si otro ya esta en ello.

    Ojo: la primera carga puede DESCARGAR el diccionario de internet. Sin
    cerrojo, dos hilos disparaban dos descargas del mismo fichero dentro de
    la peticion del usuario.
    """
    global _CARGA
    if _CARGA is None:
        with _CARGA_LOCK:
            if _CARGA is None:
                def _cargar() -> object | None:
                    target = dict_path or _DEFAULT_DICT_PATH
                    if not target.exists():
                        _download_dict(target)
                    if not target.exists():
                        return None
                    from symspellpy import SymSpell

                    sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)

                    # El diccionario tiene 1,2 millones de entradas y construir
                    # su indice de borrados cuesta ~45 s en la VM. symspellpy
                    # sabe serializar ese indice ya construido: 22 s en vez de
                    # 45, con el mismo diccionario y las mismas correcciones.
                    # El pickle vive en el volumen compartido, asi que solo se
                    # paga entero la primera vez, no en cada recreate.
                    pickle_path = _PICKLE_PATH
                    if pickle_path is not None and pickle_path.exists():
                        try:
                            sym.load_pickle(str(pickle_path))
                            return sym
                        except Exception:
                            logging.getLogger(__name__).warning(
                                "symspell_pickle_ilegible_se_reconstruye path=%s",
                                pickle_path,
                            )
                            sym = SymSpell(
                                max_dictionary_edit_distance=2, prefix_length=7
                            )

                    sym.load_dictionary(str(target), term_index=0, count_index=1)
                    if pickle_path is not None:
                        try:
                            pickle_path.parent.mkdir(parents=True, exist_ok=True)
                            sym.save_pickle(str(pickle_path))
                        except Exception:
                            # Que no se pueda cachear no impide corregir.
                            logging.getLogger(__name__).warning(
                                "symspell_pickle_no_guardado path=%s",
                                pickle_path,
                                exc_info=True,
                            )
                    return sym

                _CARGA = CargaUnica(_cargar)
    return _CARGA.obtener()


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
