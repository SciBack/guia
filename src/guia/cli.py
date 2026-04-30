"""CLI de GUIA — comandos de operación.

Uso:
    uv run python -m guia serve
    uv run python -m guia harvest
    uv run python -m guia migrate
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="guia",
    help="GUIA — Gateway Universitario de Información y Asistencia",
    add_completion=False,
)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host de escucha"),
    port: int = typer.Option(8000, help="Puerto de escucha"),
    reload: bool = typer.Option(False, help="Hot reload (solo desarrollo)"),
) -> None:
    """Inicia el servidor FastAPI de GUIA."""
    import uvicorn

    from guia.api.app import create_app
    from guia.config import GUIASettings

    settings = GUIASettings()
    create_app(settings)  # Valida la config al instanciar

    uvicorn.run(
        "guia.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # Usamos structlog
    )


@app.command()
def harvest(
    source: str = typer.Option("all", help="Fuente: dspace | ojs | alicia | all"),
    from_date: str | None = typer.Option(None, help="Fecha inicio ISO 8601 (ej: 2024-01-01)"),
) -> None:
    """Cosecha publicaciones desde las fuentes configuradas."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer
    from guia.logging import configure_logging

    settings = GUIASettings()
    configure_logging(level=settings.log_level, json_logs=False)

    typer.echo(f"Iniciando cosecha: {source} (from_date={from_date})")

    container = GUIAContainer(settings)
    harvester = container.harvester_service

    results: dict[str, dict[str, int]] = {}

    if source in ("dspace", "all"):
        results["dspace"] = harvester.harvest_dspace(from_date=from_date)

    if source in ("ojs", "all"):
        results["ojs"] = harvester.harvest_ojs()

    if source in ("alicia", "all"):
        results["alicia"] = harvester.harvest_alicia(from_date=from_date)

    for src, stats in results.items():
        typer.echo(f"  {src}: {stats}")

    container.close()
    typer.echo("Cosecha completada.")


@app.command()
def migrate() -> None:
    """Inicializa / migra el schema de base de datos."""
    from guia.config import GUIASettings
    from guia.logging import configure_logging

    settings = GUIASettings()
    configure_logging(level=settings.log_level, json_logs=False)

    typer.echo("Inicializando vector store (CREATE EXTENSION vector + tabla)...")

    from sciback_vectorstore_pgvector import PgVectorConfig, PgVectorStore

    config = PgVectorConfig()
    with PgVectorStore(config) as store:
        typer.echo("Schema inicializado correctamente.")

        if hasattr(store, "count"):
            count = store.count()
            typer.echo(f"Vectores existentes: {count}")


@app.command()
def reindex(
    target: str = typer.Option(
        "opensearch",
        help="Destino del reindex: opensearch (única opción hoy)",
    ),
    batch_size: int = typer.Option(100, help="Documentos por batch SQL + bulk_index"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Solo cuenta documentos, no escribe a OpenSearch",
    ),
    skip_chunks: bool = typer.Option(
        True,
        help="No reindexar chunks (is_chunk=True). Default True — solo padres.",
    ),
    rebuild_index: bool = typer.Option(
        False,
        "--rebuild-index",
        help="Borra y recrea el index OpenSearch antes de reindex (mapping knn_vector). "
        "Usar la primera vez o tras cambios de mapping.",
    ),
) -> None:
    """Reindex pgvector → OpenSearch (M3 hotfix mientras llega outbox+celery)."""
    import asyncio

    from guia.config import GUIASettings
    from guia.container import GUIAContainer
    from guia.logging import configure_logging
    from guia.services.reindex import ReindexService

    if target != "opensearch":
        typer.echo(f"target '{target}' no soportado. Usar 'opensearch'.", err=True)
        raise typer.Exit(2)

    settings = GUIASettings()
    configure_logging(level=settings.log_level, json_logs=False)

    if settings.search_backend == "pgvector":
        typer.echo(
            "ERROR: SEARCH_BACKEND=pgvector — no hay OpenSearch para indexar.\n"
            "       Cambiar SEARCH_BACKEND=dual o opensearch antes de reindex.",
            err=True,
        )
        raise typer.Exit(2)

    typer.echo(f"Reindex pgvector → OpenSearch (batch={batch_size}, dry_run={dry_run})")

    container = GUIAContainer(settings)
    try:
        if container.search_adapter is None:
            typer.echo("ERROR: search_adapter no configurado en el container.", err=True)
            raise typer.Exit(2)

        # search_adapter._os es el OpenSearchSearchPort interno
        os_port = container.search_adapter._os  # type: ignore[attr-defined]
        # container.store es el VectorStorePort, pero necesitamos el concreto PgVectorStore
        from sciback_vectorstore_pgvector import PgVectorStore

        if not isinstance(container.store, PgVectorStore):
            typer.echo(
                f"ERROR: store es {type(container.store).__name__}, "
                "se esperaba PgVectorStore.",
                err=True,
            )
            raise typer.Exit(2)

        service = ReindexService(
            pg_store=container.store,
            os_port=os_port,
            skip_chunks=skip_chunks,
        )

        total = service.count_documents()
        typer.echo(f"Documentos en pgvector: {total}")

        if rebuild_index and not dry_run:
            typer.echo("Recreando index OpenSearch (mapping knn_vector)...")
            asyncio.run(os_port.rebuild_index("publication"))
            typer.echo("Index recreado.")

        stats = asyncio.run(
            service.reindex_all(batch_size=batch_size, dry_run=dry_run)
        )

        typer.echo("\n── Resultado ──")
        typer.echo(f"  leídos:    {stats.total_read}")
        typer.echo(f"  indexados: {stats.total_indexed}")
        typer.echo(f"  fallidos:  {stats.total_failed}")
        typer.echo(f"  chunks omitidos: {stats.skipped_chunks}")
        if stats.errors:
            typer.echo(f"\n  primeros errores ({len(stats.errors)}):")
            for err in stats.errors[:5]:
                typer.echo(f"    · {err[:200]}")

        if stats.total_failed > 0:
            raise typer.Exit(1)
    finally:
        container.close()


@app.command()
def shell() -> None:
    """Abre un shell interactivo con el container GUIA inyectado."""
    from guia.config import GUIASettings
    from guia.container import GUIAContainer
    from guia.logging import configure_logging

    settings = GUIASettings()
    configure_logging(level=settings.log_level, json_logs=False)

    container = GUIAContainer(settings)

    import code
    code.interact(
        banner="GUIA shell — variables disponibles: container, settings",
        local={"container": container, "settings": settings},
    )

    container.close()


if __name__ == "__main__":
    app()
