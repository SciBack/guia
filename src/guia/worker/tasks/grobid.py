"""Celery tasks — GROBID PDF extraction (ADR-013 / ADR-033)."""

from __future__ import annotations

from guia.worker.celery_app import app


@app.task(
    name="guia.worker.tasks.grobid.extract_pdf",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    time_limit=600,
)
def extract_pdf(self: object, publication_id: str, pdf_url: str) -> dict:
    """Descarga PDF, extrae texto con GROBID, guarda derivado en MinIO.

    Flujo (ADR-033): descarga temp → GROBID TEI → derivados bucket → descarta PDF.
    """
    # Implementación completa en M2 (GROBID + StoragePort)
    return {"publication_id": publication_id, "status": "queued"}
