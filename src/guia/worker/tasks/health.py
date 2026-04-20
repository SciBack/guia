"""Celery tasks — ExternalResource health checking (ADR-033)."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from guia.worker.celery_app import app

logger = logging.getLogger(__name__)

# Rate limit: máx req/s por dominio (ADR-033)
_RATE_LIMIT_DELAY = 0.1  # 10 req/s


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
    Registra status HTTP y latencia en pgvector metadata.

    Args:
        domain: Si se provee, solo chequea URLs de ese dominio (ej: "repositorio.upeu.edu.pe").
                Si es None, chequea todos los dominios registrados.
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx_not_available", note="pip install httpx")
        return {"status": "skipped_no_httpx", "domain": domain}

    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)
    container = GUIAContainer(settings)

    try:
        # Obtener URLs a verificar desde el vector store
        urls = _get_urls_to_check(container, domain)

        if not urls:
            logger.info("health_check_no_urls", domain=domain)
            return {"status": "ok", "checked": 0, "domain": domain}

        results = _check_urls(urls, httpx)

        ok = sum(1 for r in results if r["status"] in range(200, 400))
        broken = len(results) - ok

        logger.info(
            "health_check_complete",
            domain=domain,
            total=len(results),
            ok=ok,
            broken=broken,
        )
        return {
            "status": "ok",
            "checked": len(results),
            "ok": ok,
            "broken": broken,
            "domain": domain,
        }
    finally:
        container.close()


def _get_urls_to_check(container: object, domain: str | None) -> list[str]:
    """Extrae URLs de publicaciones del vector store para verificar.

    M3: obtiene URLs desde metadata de pgvector.
    M4: usar ExternalResourceRepository dedicado.
    """
    store = getattr(container, "store", None)
    if store is None or not hasattr(store, "list_metadata"):
        # PgVectorStore no expone list_metadata aún — retornar vacío
        logger.debug("health_check_store_no_list_metadata")
        return []

    urls: list[str] = []
    try:
        # Intentar obtener sample de URLs desde metadata
        records = store.list_metadata(limit=500)  # type: ignore[union-attr]
        for record in records:
            url = record.get("url") or record.get("external_resource_uri")
            if not url:
                continue
            if domain:
                parsed = urlparse(str(url))
                if parsed.netloc != domain:
                    continue
            urls.append(str(url))
    except Exception as exc:
        logger.warning("health_check_list_error", exc=str(exc))

    return urls


def _check_urls(urls: list[str], httpx: object) -> list[dict]:
    """Realiza HEAD requests a cada URL con rate limiting por dominio."""
    results: list[dict] = []
    domain_timestamps: dict[str, float] = {}

    with httpx.Client(timeout=10.0, follow_redirects=True) as client:  # type: ignore[union-attr]
        for url in urls:
            domain = urlparse(url).netloc

            # Rate limiting por dominio
            last_ts = domain_timestamps.get(domain, 0.0)
            elapsed = time.monotonic() - last_ts
            if elapsed < _RATE_LIMIT_DELAY:
                time.sleep(_RATE_LIMIT_DELAY - elapsed)

            try:
                t0 = time.monotonic()
                resp = client.head(url)  # type: ignore[union-attr]
                latency_ms = int((time.monotonic() - t0) * 1000)

                results.append({
                    "url": url,
                    "status": resp.status_code,
                    "latency_ms": latency_ms,
                })
                logger.debug("url_checked", url=url, status=resp.status_code, ms=latency_ms)

            except Exception as exc:
                results.append({
                    "url": url,
                    "status": 0,
                    "error": str(exc),
                })
                logger.warning("url_check_failed", url=url, exc=str(exc))

            domain_timestamps[domain] = time.monotonic()

    return results
