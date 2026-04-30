"""Audit log — trazabilidad regulatoria de queries (ADR-036, P1.3).

Cumplimiento Ley 29733 (Perú): cada query genera entrada en `audit_log`
con sha256(query) — NUNCA la query original — más metadata de routing
y LLM. Retención: 24 meses.

Componentes:
- AuditLogEntry: dataclass con los campos persistidos
- AuditLogRepository: persistencia en Postgres (psycopg sync wrapped en threads)
- middleware.audit_query: decorator que envuelve ChatService.answer()
"""

from guia.audit.models import AuditLogEntry, hash_query
from guia.audit.repository import AuditLogRepository

__all__ = [
    "AuditLogEntry",
    "AuditLogRepository",
    "hash_query",
]
