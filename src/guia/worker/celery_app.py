"""Celery application — GUIA Node (M1, ADR-013)."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

# Las colas harvester/grobid/health están predeclaradas por
# docker/rabbitmq/definitions.json con dead-letter hacia sciback.events.dlx.
# Celery DEBE declararlas con los mismos argumentos o RabbitMQ rechaza con
# PRECONDITION_FAILED (406). Ver definitions.json. La cola "indexer" es propia
# de Celery (no canónica → sin args). La canónica del bus es "search.indexer".
_DLX_ARGS = {
    "x-dead-letter-exchange": "sciback.events.dlx",
    "x-dead-letter-routing-key": "dlq",
}

broker_url = os.environ.get(
    "CELERY_BROKER_URL",
    "amqp://guia:changeme@rabbitmq:5672/sciback",
)
result_backend = os.environ.get(
    "CELERY_RESULT_BACKEND",
    "redis://redis:6379/1",
)

app = Celery(
    "guia",
    broker=broker_url,
    backend=result_backend,
    include=[
        "guia.worker.tasks.indexer",
        "guia.worker.tasks.harvester",
        "guia.worker.tasks.grobid",
        "guia.worker.tasks.health",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "guia.worker.tasks.indexer.*": {"queue": "indexer"},
        "guia.worker.tasks.harvester.*": {"queue": "harvester"},
        "guia.worker.tasks.grobid.*": {"queue": "grobid"},
        "guia.worker.tasks.health.*": {"queue": "health"},
    },
    # Declarar colas con los argumentos que definitions.json ya fijó en RabbitMQ.
    task_queues=[
        Queue("indexer"),
        Queue("harvester", queue_arguments=_DLX_ARGS),
        Queue("grobid", queue_arguments=_DLX_ARGS),
        Queue("health", queue_arguments=_DLX_ARGS),
    ],
    beat_schedule={
        "harvest-dspace-daily": {
            "task": "guia.worker.tasks.harvester.harvest_dspace",
            "schedule": crontab(hour=2, minute=0),
        },
        "harvest-ojs-daily": {
            "task": "guia.worker.tasks.harvester.harvest_ojs",
            "schedule": crontab(hour=2, minute=30),
        },
        "harvest-alicia-weekly": {
            "task": "guia.worker.tasks.harvester.harvest_alicia",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),
        },
        "check-external-resources-weekly": {
            "task": "guia.worker.tasks.health.check_external_resources",
            "schedule": crontab(hour=4, minute=0, day_of_week=1),
        },
        "generate-catalog-snapshot-monthly": {
            "task": "guia.worker.tasks.indexer.generate_catalog_snapshot",
            "schedule": crontab(hour=1, minute=0, day_of_month=1),
        },
    },
)
