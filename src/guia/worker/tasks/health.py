"""Celery tasks — ExternalResource health checking (ADR-033)."""

from __future__ import annotations

from guia.worker.celery_app import app


@app.task(
    name="guia.worker.tasks.health.check_external_resources",
    bind=True,
    max_retries=1,
    acks_late=True,
    time_limit=3600,
)
def check_external_resources(self: object, domain: str | None = None) -> dict:
    """HEAD requests periódicos a ExternalResource.resolver_url.

    Rate-limited: máx 10 req/s por dominio (ADR-033).
    """
    # Implementación completa en M2 (ExternalResource + StoragePort)
    return {"status": "health_check_queued", "domain": domain}
