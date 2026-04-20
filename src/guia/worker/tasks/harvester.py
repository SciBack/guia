"""Celery tasks — harvesting OAI-PMH (ADR-013)."""

from __future__ import annotations

from guia.worker.celery_app import app


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
    result = container.harvester_service.harvest_dspace(incremental=incremental)
    return {"harvested": result.count, "source": "dspace"}


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
    result = container.harvester_service.harvest_ojs(incremental=incremental)
    return {"harvested": result.count, "source": "ojs"}


@app.task(
    name="guia.worker.tasks.harvester.harvest_alicia",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
)
def harvest_alicia(self: object) -> dict:
    """Cosecha ALICIA CONCYTEC OAI-PMH."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)
    container = GUIAContainer(settings)
    result = container.harvester_service.harvest_alicia()
    return {"harvested": result.count, "source": "alicia"}
