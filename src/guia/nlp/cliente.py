"""Cliente del analizador NLP que sirve el sidecar.

Por qué existe: cada canal cargaba su propia copia de los modelos NLP. Medido
el 09-sep-2026 en el contenedor de producción — Detoxify 712 MB, spaCy
es_core_news_lg 317 MB, SymSpell 31 MB: 1.061 MB por canal, duplicados en
``api`` y ``chainlit``, sobre una VM de 9,7 GB que tenía 500 MB libres. Es la
misma situación que resolvió ADR-051 para los embeddings, una capa más arriba.

Política de fallo, y es deliberada: si el sidecar no responde se devuelve el
valor neutro —el mismo que ya devolvían los gates cuando un modelo no
cargaba— y **se registra en WARNING**. Lo que no se hace es cargar el modelo
localmente como reserva: eso devolvería la memoria duplicada por la puerta de
atrás, que es justo lo que se viene a quitar.

El registro no es un detalle. Detoxify llevaba meses sin cargarse en ``api`` y
``chainlit`` por un ``PermissionError`` de la caché de HuggingFace, degradaba
en silencio y nadie se enteró. Un guardarraíl que falla callado es peor que no
tenerlo, porque se sigue contando con él.
"""

from __future__ import annotations

import httpx

from guia.logging import get_logger

logger = get_logger(__name__)

#: Valor de cada operación cuando no hay analizador. Coincide con la
#: degradación que ya tenían los gates: idioma español, sin toxicidad, texto
#: sin corregir y sin entidades.
_NEUTRO: dict[str, dict[str, object]] = {
    "toxicity": {"score": 0.0},
    "entities": {"entities": {}},
    "spellcheck": {"text": ""},
    "language": {"lang": "es", "confidence": 1.0},
}


class AnalizadorNLP:
    """Habla con ``POST /api/nlp`` del sidecar.

    Args:
        base_url: Raíz del sidecar (el mismo que sirve embeddings y reranker).
        timeout: Techo por petición. Corto a propósito: estas llamadas están en
            el camino de cada consulta, y es mejor degradar que hacer esperar.
    """

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._url = base_url.rstrip("/") + "/api/nlp"
        self._timeout = timeout
        # Cliente síncrono a propósito: los gates y el reescritor ya se
        # invocan dentro de ``asyncio.to_thread``, así que una llamada
        # bloqueante aquí no toca el bucle de eventos y evita duplicar cada
        # método en versión async.
        self._http = httpx.Client(timeout=timeout)

    def _pedir(self, op: str, texto: str) -> dict[str, object]:
        try:
            r = self._http.post(self._url, json={"op": op, "text": texto})
            r.raise_for_status()
            datos: dict[str, object] = r.json()
        except Exception as exc:
            logger.warning("nlp_sidecar_no_responde", op=op, error=str(exc))
            return {**_NEUTRO.get(op, {}), "disponible": False}

        if not datos.get("disponible", True):
            # El sidecar contestó, pero su modelo no cargó. Se distingue del
            # caso anterior porque el remedio es distinto: allí es la red, aquí
            # es el modelo.
            logger.warning("nlp_modelo_no_disponible_en_sidecar", op=op)
        return datos

    def toxicidad(self, texto: str) -> float:
        """Puntuación máxima de toxicidad, 0.0 si no hay analizador."""
        d = self._pedir("toxicity", texto)
        return float(d.get("score", 0.0) or 0.0)

    def entidades(self, texto: str) -> dict[str, list[str]]:
        """Entidades por tipo (PER, ORG, LOC…); vacío si no hay analizador."""
        d = self._pedir("entities", texto)
        ents = d.get("entities") or {}
        return ents if isinstance(ents, dict) else {}

    def corregir(self, texto: str) -> str:
        """Texto con las erratas corregidas; el original si no hay analizador."""
        d = self._pedir("spellcheck", texto)
        corregido = d.get("text")
        return corregido if isinstance(corregido, str) and corregido else texto

    def idioma(self, texto: str) -> tuple[str, float]:
        """Código ISO 639-1 y confianza; ("es", 1.0) si no hay analizador."""
        d = self._pedir("language", texto)
        return str(d.get("lang", "es")), float(d.get("confidence", 1.0) or 1.0)

    def calentar(self) -> dict[str, bool]:
        """Fuerza la carga de los cuatro modelos en el sidecar.

        La llama el warmup de cada canal. Antes cada canal cargaba los modelos
        en su propio proceso; ahora solo empuja al sidecar a tenerlos listos,
        que es trabajo hecho una vez y aprovechado por todos.
        """
        estado: dict[str, bool] = {}
        for op in ("language", "toxicity", "entities", "spellcheck"):
            d = self._pedir(op, "calentamiento")
            estado[op] = bool(d.get("disponible", False))
        logger.info("nlp_sidecar_calentado", **estado)
        return estado

    def cerrar(self) -> None:
        """Cierra el pool HTTP. La llama el container al apagarse."""
        self._http.close()
