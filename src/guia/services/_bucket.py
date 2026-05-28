"""Bucket A/B determinístico para el AgentOrchestrator (ADR-050, Día 3).

La función assign_bucket() es pura, síncrona y sin efectos laterales.
El mismo user_id siempre cae al mismo bucket (sha256 determinístico).
"""

from __future__ import annotations

import hashlib
from typing import Literal


def assign_bucket(
    user_id: str | None,
    rollout_pct: int,
) -> Literal["agent", "legacy"]:
    """Asigna determinísticamente un user_id a bucket agent o legacy.

    Anónimos (user_id None, vacío, o que empiece con 'anon') siempre van
    a legacy. El mismo user_id no anónimo siempre cae al mismo bucket.

    Args:
        user_id: Identificador estable del usuario (UPeU ID, Telegram ID, etc.).
            None o cadena vacía → legacy.
        rollout_pct: Porcentaje de usuarios a enviar al bucket agent (0-100).
            0 → todos legacy. 100 → todos agent (excepto anónimos).

    Returns:
        "agent" si el usuario cae en el porcentaje de rollout, "legacy" en
        caso contrario.
    """
    if not user_id or user_id.lower().startswith("anon"):
        return "legacy"
    if rollout_pct <= 0:
        return "legacy"
    if rollout_pct >= 100:
        return "agent"
    h = int(hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8], 16)
    return "agent" if (h % 100) < rollout_pct else "legacy"
