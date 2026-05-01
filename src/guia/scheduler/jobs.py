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


def reindex_opensearch_job(container: GUIAContainer) -> None:
    """Re-popula OpenSearch desde pgvector (M3 hotfix mientras llega outbox+celery).

    Se llama desde harvest_daily_job y harvest_koha_weekly_job al final del
    harvest, para mantener OpenSearch sincronizado con pgvector. Idempotente:
    sobreescribe los mismos docs en OS por su _id.

    No-op silencioso si SEARCH_BACKEND=pgvector o no hay OpenSearch adapter.
    """
    if _settings.search_backend == "pgvector":
        logger.info("reindex_skipped", reason="search_backend=pgvector")
        return
    if container.search_adapter is None:
        logger.warning("reindex_skipped", reason="no search_adapter configured")
        return

    import asyncio

    from sciback_vectorstore_pgvector import PgVectorStore

    from guia.services.reindex import ReindexService

    if not isinstance(container.store, PgVectorStore):
        logger.warning("reindex_skipped", reason=f"store is {type(container.store).__name__}")
        return

    os_port = container.search_adapter._os  # type: ignore[attr-defined]
    service = ReindexService(pg_store=container.store, os_port=os_port, skip_chunks=True)

    try:
        stats = asyncio.run(service.reindex_all(batch_size=200))
        logger.info(
            "reindex_complete",
            read=stats.total_read,
            indexed=stats.total_indexed,
            failed=stats.total_failed,
            skipped_chunks=stats.skipped_chunks,
        )
    except Exception:
        logger.exception("reindex_error")


def harvest_daily_job(container: GUIAContainer) -> None:
    """Job: cosecha incremental desde todas las fuentes configuradas.

    Corre con from_date = ayer para capturar items publicados recientemente.
    Después del harvest, reindexa OpenSearch (no-op si SEARCH_BACKEND=pgvector).
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
        return

    # Sincroniza OpenSearch con los nuevos docs del harvest
    reindex_opensearch_job(container)


def harvest_koha_weekly_job(container: GUIAContainer) -> None:
    """Job: re-indexación completa del catálogo Koha (semanal, domingos 1am).

    Koha no tiene OAI-PMH incremental, así que se re-cosecha completo.
    Después del harvest, reindexa OpenSearch.
    """
    logger.info("harvest_koha_weekly_start")
    try:
        result = container.harvester_service.harvest_koha()
        logger.info("harvest_koha_weekly_complete", result=result)
    except Exception:
        logger.exception("harvest_koha_weekly_error")
        return

    # Sincroniza OpenSearch con el catálogo Koha actualizado
    reindex_opensearch_job(container)


def backup_s3_job(container: GUIAContainer) -> None:
    """Job: backup de la base de datos a S3 (Sprint 0.7).

    Flujo:
      1. pg_dump -Fc del esquema completo (incluye sciback_vectors, audit_log,
         chat_sessions, chat_messages, user_profiles)
      2. gzip
      3. aws s3 cp con expiration tag
      4. Si AWS_S3_BACKUP_BUCKET no configurado, guarda local en /tmp y log.

    Retención: la lifecycle del bucket S3 (configurada aparte) gestiona
    la antigüedad. GUIA solo escribe.
    """
    import gzip
    import os
    import shutil
    import subprocess
    import tempfile
    from datetime import UTC, datetime

    bucket = _settings.aws_s3_backup_bucket
    db_url = _settings.pgvector_database_url
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"guia-pgvector-{timestamp}.dump.gz"

    # 1. pg_dump → archivo temporal
    pg_url = db_url.replace("postgresql+psycopg://", "postgresql://")
    tmp_dir = tempfile.mkdtemp(prefix="guia-backup-")
    raw_path = os.path.join(tmp_dir, "dump.bin")
    gz_path = os.path.join(tmp_dir, filename)

    try:
        logger.info("backup_pg_dump_start", bucket=bucket or "(local)")
        result = subprocess.run(
            ["pg_dump", "-Fc", "-f", raw_path, pg_url],
            capture_output=True,
            timeout=1800,
        )
        if result.returncode != 0:
            logger.error(
                "backup_pg_dump_failed",
                returncode=result.returncode,
                stderr=result.stderr.decode("utf-8", errors="replace")[:500],
            )
            return

        # 2. gzip
        with open(raw_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        size_mb = os.path.getsize(gz_path) / 1024 / 1024
        logger.info("backup_compressed", size_mb=round(size_mb, 1))

        # 3. Subir a S3 si está configurado
        if bucket:
            s3_key = f"guia/pgvector/{filename}"
            result = subprocess.run(
                [
                    "aws",
                    "s3",
                    "cp",
                    gz_path,
                    f"s3://{bucket}/{s3_key}",
                    "--no-progress",
                ],
                capture_output=True,
                timeout=900,
            )
            if result.returncode == 0:
                logger.info(
                    "backup_s3_uploaded",
                    bucket=bucket,
                    key=s3_key,
                    size_mb=round(size_mb, 1),
                )
            else:
                logger.error(
                    "backup_s3_upload_failed",
                    stderr=result.stderr.decode("utf-8", errors="replace")[:500],
                )
        else:
            # Sin bucket: guarda local en /var/backups/guia/ (montar volume si se quiere persistir)
            local_dir = "/var/backups/guia"
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, filename)
            shutil.move(gz_path, local_path)
            logger.info("backup_local_saved", path=local_path, size_mb=round(size_mb, 1))

    except subprocess.TimeoutExpired:
        logger.error("backup_timeout")
    except FileNotFoundError as exc:
        logger.error(
            "backup_tool_missing",
            tool=str(exc),
            msg="Ensure pg_dump (postgresql-client) y aws cli están instalados",
        )
    except Exception:
        logger.exception("backup_error")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
