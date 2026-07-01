"""Cliente async hacia el sidecar de Dify (FASE A migración GUIA→Dify).

El sidecar expone `POST /sidecar/v1/chat` y hace de puente hacia la app de
Dify (routing, gates, RAG y síntesis viven ahora en Dify — GUIA solo
reenvía la consulta del usuario y renderiza la respuesta).

Vive separado de `chainlit_app` para poder testearse sin levantar Chainlit
ni sus dependencias (Data Layer, Redis, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class DifyClientError(Exception):
    """Error de comunicación con el sidecar de Dify (HTTP, timeout, payload)."""


@dataclass(slots=True)
class DifyChatResult:
    """Resultado normalizado de una consulta al sidecar de Dify.

    Attributes:
        answer: Texto de respuesta generado por Dify.
        citations: Lista de `retriever_resource` (document_name, content,
            score, etc.) tal como los devuelve Dify, sin transformar.
        conversation_id: Id de conversación de Dify — debe reenviarse en el
            siguiente turno para mantener memoria multi-turno.
        latency_ms: Latencia reportada por el sidecar (ms).
        ai_label: Metadata opcional del sidecar (ej. etiqueta de modelo/ruta).
    """

    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    conversation_id: str = ""
    latency_ms: int = 0
    ai_label: dict[str, Any] = field(default_factory=dict)


class DifyClient:
    """Cliente HTTP async hacia el endpoint `/sidecar/v1/chat` de Dify.

    Args:
        base_url: URL base del sidecar (ej. "https://192.168.15.210/sidecar").
        api_key: Bearer token del sidecar (`GUIA_DIFY_SIDECAR_KEY`).
        verify: Verificación TLS. `False` para el cert de CA interna en
            entornos de prueba (equivalente a `-k` en curl).
        timeout: Timeout total de la petición en segundos.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        verify: bool = True,
        timeout: float = 120.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/v1/chat"
        self._api_key = api_key
        self._verify = verify
        self._timeout = timeout

    async def chat(
        self,
        query: str,
        user: str,
        conversation_id: str = "",
    ) -> DifyChatResult:
        """Envía una consulta al sidecar y normaliza la respuesta.

        Args:
            query: Texto del usuario.
            user: Identificador del usuario (email o "anon").
            conversation_id: Id de conversación previo de Dify, o "" en el
                primer turno.

        Returns:
            DifyChatResult con la respuesta, citas y el conversation_id a
            reenviar en el siguiente turno.

        Raises:
            DifyClientError: si el sidecar responde con error HTTP, timeout,
                o un payload que no se puede interpretar.
        """
        payload = {"query": query, "user": user, "conversation_id": conversation_id}
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(verify=self._verify, timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise DifyClientError(f"Timeout consultando el sidecar Dify: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DifyClientError(f"Error de red consultando el sidecar Dify: {exc}") from exc

        if response.status_code != 200:
            raise DifyClientError(
                f"Sidecar Dify respondió {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise DifyClientError(f"Respuesta no-JSON del sidecar Dify: {exc}") from exc

        try:
            return DifyChatResult(
                answer=data["answer"],
                citations=data.get("citations") or [],
                conversation_id=data.get("conversation_id", ""),
                latency_ms=data.get("latency_ms", 0),
                ai_label=data.get("ai_label") or {},
            )
        except KeyError as exc:
            raise DifyClientError(f"Payload del sidecar Dify sin campo requerido: {exc}") from exc
