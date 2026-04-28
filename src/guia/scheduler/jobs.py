"""Jobs programados de GUIA con APScheduler (Sprint 0.7).

Jobs implementados:
- harvest_daily: cosecha incremental de DSpace + OJS + ALICIA
- backup_s3: placeholder backup S3
- metrics_report: log de métricas diarias

Arranque:
    python -m guia.scheduler
"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=True)
logger = get_logger(__name__)


def _get_yesterday_iso() -> str:
    """Retorna fecha de ayer en formato ISO 8601 para cosecha incremental."""
    from datetime import timedelta
    yesterday = datetime.now(UTC) - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def harvest_daily_job(container: GUIAContainer) -> None:
    """Job: cosecha incremental desde todas las fuentes configuradas.

    Corre con from_date = ayer para capturar items publicados recientemente.
    """
    from_date = _get_yesterday_iso()
    logger.info("harvest_daily_start", from_date=from_date)

    try:
        results = container.harvester_service.harvest_all(from_date=from_date)
        total_ok = sum(r.get("ok", 0) for r in results.values())
        total_err = sum(r.get("error", 0) for r in results.values())
        logger.info(
            "harvest_daily_complete",
            results=results,
            total_ok=total_ok,
            total_error=total_err,
        )
    except Exception:
        logger.exception("harvest_daily_error")


def harvest_koha_weekly_job(container: GUIAContainer) -> None:
    """Job: re-indexación completa del catálogo Koha (semanal, domingos 1am).

    Koha no tiene OAI-PMH incremental, así que se re-cosecha completo.
    """
    logger.info("harvest_koha_weekly_start")
    try:
        result = container.harvester_service.harvest_koha()
        logger.info("harvest_koha_weekly_complete", result=result)
    except Exception:
        logger.exception("harvest_koha_weekly_error")


def backup_s3_job(container: GUIAContainer) -> None:
    """Job: backup de la base de datos vectorial a S3 (placeholder Sprint 0.7).

    TODO: implementar pg_dump + upload a S3 usando aws s3 cp.
    Por ahora solo registra que el job se ejecutó.
    """
    bucket = _settings.aws_s3_backup_bucket
    if not bucket:
        logger.info("backup_s3_skipped", reason="AWS_S3_BACKUP_BUCKET not configured")
        return

    logger.info("backup_s3_start", bucket=bucket)
    # TODO Sprint 0.7: implementar pg_dump + s3 upload
    # pg_dump -Fc $PGVECTOR_DATABASE_URL -f /tmp/guia_backup.dump
    # aws s3 cp /tmp/guia_backup.dump s3://<bucket>/guia/<date>.dump
    logger.info("backup_s3_placeholder", msg="Backup not yet implemented")


def metrics_report_job(container: GUIAContainer) -> None:
    """Job: reporta métricas diarias del vector store."""
    try:
        store = container.store
        if hasattr(store, "count"):
            count = store.count()  # type: ignore[union-attr]
            logger.info("metrics_daily", total_vectors=count)
    except Exception:
        logger.exception("metrics_report_error")


def run_scheduler() -> None:
    """Arranca el scheduler bloqueante con todos los jobs configurados."""
    logger.info("scheduler_starting")

    container = GUIAContainer(_settings)
    scheduler = BlockingScheduler(timezone="America/Lima")

    # Parsear cron de configuración (ej: "0 2 * * *")
    cron_parts = _settings.harvest_cron.split()
    if len(cron_parts) == 5:
        minute, hour, day, month, day_of_week = cron_parts
    else:
        minute, hour, day, month, day_of_week = "0", "2", "*", "*", "*"

    # Job: cosecha diaria
    scheduler.add_job(
        harvest_daily_job,
        trigger=CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        ),
        args=[container],
        id="harvest_daily",
        name="Cosecha diaria incremental",
        misfire_grace_time=3600,
    )

    # Job: re-indexación completa Koha (domingos 1am Lima)
    scheduler.add_job(
        harvest_koha_weekly_job,
        trigger=CronTrigger(hour=1, minute=0, day_of_week="sun"),
        args=[container],
        id="harvest_koha_weekly",
        name="Re-indexación semanal Koha",
        misfire_grace_time=7200,
    )

    # Job: backup S3 (3am Lima)
    scheduler.add_job(
        backup_s3_job,
        trigger=CronTrigger(hour=3, minute=0),
        args=[container],
        id="backup_s3",
        name="Backup S3",
        misfire_grace_time=3600,
    )

    # Job: métricas (6am Lima)
    scheduler.add_job(
        metrics_report_job,
        trigger=CronTrigger(hour=6, minute=0),
        args=[container],
        id="metrics_report",
        name="Reporte de métricas",
        misfire_grace_time=3600,
    )

    logger.info(
        "scheduler_jobs_registered",
        jobs=["harvest_daily", "harvest_koha_weekly", "backup_s3", "metrics_report"],
        harvest_cron=_settings.harvest_cron,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")
    finally:
        container.close()


if __name__ == "__main__":
    run_scheduler()
