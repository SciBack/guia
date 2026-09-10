"""Detección de idioma con fasttext LID-176.

Distingue español de inglés, portugués y demás, y **quechua** cuando el texto
da para reconocerlo. Lo que no distingue es **aymara**: el modelo LID-176 no
lo tiene entre sus 176 idiomas —comprobado el 10-sep-2026 leyendo las
etiquetas del propio ``lid.176.bin``—, aunque el docstring de este módulo lo
prometiera. Sí trae quechua (``qu``) y guaraní (``gn``).

Con frases cortas acierta menos, y eso es propio de la detección de idioma:
"Nuqaqa Peru suyumanta kani, yachay wasiman rini sapa punchaw" sale ``qu``
con 0,58, pero un saludo suelto de cuatro palabras se va a ``en`` con 0,13.
Por eso el gate que lo usa solo debería actuar con confianza alta.

Si el modelo no está disponible, devuelve ("es", 1.0): un fallback seguro para
una universidad cuyo idioma de trabajo es el español.
"""
from __future__ import annotations

import threading

_LID_MODEL = None
_LID_LOADED = False
# La primera llamada descarga y carga lid.176.bin. Sin cerrojo, dos hilos
# —el warmup y la primera consulta— lo cargaban a la vez; y como la bandera
# se marcaba ANTES de terminar, el segundo se iba con _LID_MODEL=None y daba
# "es" por defecto sin haber mirado el texto. Ahora espera al primero.
_LID_LOCK = threading.Lock()


def _remendar_fasttext_para_numpy2() -> None:
    """Deja usable un fasttext que NumPy 2 rompió, sin tocar NumPy.

    fasttext 0.9.3 termina ``predict`` con ``np.array(probs, copy=False)``.
    NumPy 2 ya no admite esa forma de pedir "no copies" y lanza
    ``ValueError: Unable to avoid copy while creating an array as requested``,
    así que **toda** detección fallaba y el módulo devolvía "es" siempre.
    Medido el 10-sep-2026 en el sidecar de producción: el detector llevaba
    caído desde el despliegue, en silencio.

    Meta dejó de mantener fasttext, así que no va a llegar arreglado de
    fábrica. El remedio de la propia comunidad es cambiar esa línea por
    ``np.asarray``, que hace lo mismo y sí copia cuando hace falta.

    Aquí se aplica **solo al módulo de fasttext**, sustituyendo su referencia
    a NumPy por un envoltorio que se comporta igual salvo en ese caso. NumPy
    sigue siendo estricto para todo lo demás del proceso —comprobado—, que es
    lo que importa: un parche global habría cambiado, calladamente, el
    comportamiento de los embeddings y del reranker, que también usan NumPy.
    """
    import fasttext.FastText as modulo_fasttext  # noqa: N813 — es un módulo, no una clase
    import numpy as np

    class _NumpyParaFasttext:
        def __getattr__(self, nombre: str) -> object:
            return getattr(np, nombre)

        def array(self, obj: object, *args: object, **kwargs: object) -> object:
            if kwargs.get("copy") is False:
                kwargs.pop("copy")
                return np.asarray(obj, *args, **kwargs)
            return np.array(obj, *args, **kwargs)

    modulo_fasttext.np = _NumpyParaFasttext()


def _get_model() -> object | None:
    global _LID_MODEL, _LID_LOADED
    if _LID_LOADED:
        return _LID_MODEL
    with _LID_LOCK:
        if _LID_LOADED:  # otro hilo lo cargo mientras esperabamos
            return _LID_MODEL
        try:
            _remendar_fasttext_para_numpy2()
            # El paquete fasttext-langdetect instala el módulo como `ftlangdetect`.
            from ftlangdetect import detect
            detect("hola")
            _LID_MODEL = detect
        except Exception:
            _LID_MODEL = None
        finally:
            _LID_LOADED = True
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
