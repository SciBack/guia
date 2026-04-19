"""SemanticCache — caché semántico sobre Redis."""

from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis as redis_module

    from guia.domain.chat import ChatResponse

DEFAULT_TTL = 3600
DEFAULT_THRESHOLD = 0.92
CACHE_PREFIX = "guia:chat:"
VECTOR_PREFIX = "guia:vec:"


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity entre dos vectores."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _query_key(query: str) -> str:
    """Clave determinista para una query exacta."""
    digest = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]
    return f"{CACHE_PREFIX}{digest}"


class SemanticCache:
    """Caché semántico de respuestas GUIA sobre Redis.

    Args:
        client: Cliente Redis ya conectado.
        ttl: Tiempo de vida de entradas en segundos.
        threshold: Score mínimo para considerar cache hit (0.0-1.0).
    """

    def __init__(
        self,
        client: redis_module.Redis,  # type: ignore[type-arg]
        *,
        ttl: int = DEFAULT_TTL,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._redis = client
        self.ttl = ttl
        self.threshold = threshold

    def get(self, query: str, *, query_vector: list[float] | None = None) -> ChatResponse | None:
        """Busca una respuesta cacheada para la query."""
        from guia.domain.chat import ChatResponse as CR

        # 1. Hit exacto
        exact_key = _query_key(query)
        raw = self._redis.get(exact_key)
        if raw is not None:
            data = json.loads(raw)  # type: ignore[arg-type]
            return CR(**data)

        # 2. Hit semántico
        if query_vector is not None:
            hits = self._semantic_search(query_vector)
            if hits:
                return hits[0]

        return None

    def set(
        self,
        query: str,
        response: ChatResponse,
        *,
        query_vector: list[float] | None = None,
    ) -> None:
        """Almacena una respuesta en el caché."""
        exact_key = _query_key(query)
        payload = response.model_dump_json()
        self._redis.setex(exact_key, self.ttl, payload)

        if query_vector is not None:
            vec_key = f"{VECTOR_PREFIX}{exact_key}"
            self._redis.setex(
                vec_key,
                self.ttl,
                json.dumps({"vector": query_vector, "response_key": exact_key}),
            )

    def _semantic_search(self, query_vector: list[float]) -> list[ChatResponse]:
        """Busca en los vectores almacenados por similitud coseno."""
        from guia.domain.chat import ChatResponse as CR

        pattern = f"{VECTOR_PREFIX}*"
        results: list[CR] = []

        cursor: int = 0
        while True:
            cursor, keys = self._redis.scan(cursor, match=pattern, count=100)  # type: ignore[misc]
            for key in keys:
                raw = self._redis.get(key)
                if raw is None:
                    continue
                data = json.loads(raw)  # type: ignore[arg-type]
                stored_vec: list[float] = data["vector"]
                score = _cosine(query_vector, stored_vec)
                if score >= self.threshold:
                    response_raw = self._redis.get(data["response_key"])
                    if response_raw is not None:
                        results.append(CR(**json.loads(response_raw)))  # type: ignore[arg-type]
            if cursor == 0:
                break

        return results
