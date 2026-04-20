"""Celery tasks — harvesting OAI-PMH (ADR-013)."""

from __future__ import annotations

from guia.worker.celery_app import app


def _incremental_from_date(incremental: bool) -> str | None:
    """Si incremental=True retorna fecha de ayer (ISO), si no None (cosecha completa)."""
    if not incremental:
        return None
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


@app.task(
    name="guia.worker.tasks.harvester.harvest_dspace",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def harvest_dspace(self: object, incremental: bool = True) -> dict:
    """Cosecha incremental DSpace OAI-PMH → pgvector."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)
    container = GUIAContainer(settings)
    # Bug fix M3: HarvesterService.harvest_dspace() acepta from_date, no incremental
    from_date = _incremental_from_date(incremental)
    result = container.harvester_service.harvest_dspace(from_date=from_date)
    container.close()
    return {"harvested": result.get("ok", 0), "source": "dspace"}


@app.task(
    name="guia.worker.tasks.harvester.harvest_ojs",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def harvest_ojs(self: object, incremental: bool = True) -> dict:
    """Cosecha incremental OJS OAI-PMH → pgvector."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)
    container = GUIAContainer(settings)
    # Bug fix M3: harvest_ojs() no acepta incremental — solo set_spec
    result = container.harvester_service.harvest_ojs()
    container.close()
    return {"harvested": result.get("ok", 0), "source": "ojs"}


@app.task(
    name="guia.worker.tasks.harvester.harvest_alicia",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
)
def harvest_alicia(self: object, incremental: bool = True) -> dict:
    """Cosecha ALICIA CONCYTEC OAI-PMH."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)
    container = GUIAContainer(settings)
    result = container.harvester_service.harvest_alicia(
        from_date=_incremental_from_date(incremental),
    )
    container.close()
    return {"harvested": result.get("ok", 0), "source": "alicia"}
