"""Dashboard de producción científica GUIA (Sprint 0.6 — Streamlit).

Muestra métricas del repositorio indexado consultando pgvector metadata
y audit_log. Diseñado para demo DTI UPeU.

Arranque:
    streamlit run src/guia/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from guia.config import GUIASettings

st.set_page_config(
    page_title="GUIA — Dashboard UPeU",
    page_icon="📚",
    layout="wide",
)

_settings = GUIASettings()


@st.cache_resource
def get_container() -> object:
    """Carga el container GUIA (cacheado por Streamlit)."""
    from guia.container import GUIAContainer

    return GUIAContainer(_settings)


@st.cache_data(ttl=300)  # 5 min
def _stats_by_source() -> list[dict]:
    """Conteo de docs (parents) por fuente."""
    container = get_container()
    from sqlalchemy import text

    engine = container.store._engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT metadata->>'source' AS source,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (
                           WHERE metadata->>'is_chunk' IS NULL
                              OR metadata->>'is_chunk' = 'false'
                       ) AS parents,
                       COUNT(*) FILTER (
                           WHERE metadata->>'is_chunk' = 'true'
                       ) AS chunks
                FROM sciback_vectors
                GROUP BY metadata->>'source'
                ORDER BY total DESC
                """
            )
        ).fetchall()
    return [
        {"Fuente": r[0] or "?", "Total": r[1], "Parents": r[2], "Chunks": r[3]}
        for r in rows
    ]


@st.cache_data(ttl=300)
def _stats_by_year() -> list[dict]:
    """Distribución de docs por año (top 15)."""
    container = get_container()
    from sqlalchemy import text

    engine = container.store._engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT (metadata->>'year')::int AS year, COUNT(*) AS total
                FROM sciback_vectors
                WHERE metadata->>'year' IS NOT NULL
                  AND metadata->>'year' ~ '^[0-9]+$'
                  AND (metadata->>'is_chunk' IS NULL OR metadata->>'is_chunk' = 'false')
                GROUP BY metadata->>'year'
                ORDER BY year DESC
                LIMIT 15
                """
            )
        ).fetchall()
    return [{"Año": r[0], "Documentos": r[1]} for r in rows]


@st.cache_data(ttl=300)
def _top_keywords(limit: int = 15) -> list[dict]:
    """Top keywords más frecuentes."""
    container = get_container()
    from sqlalchemy import text

    engine = container.store._engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT lower(trim(kw)) AS keyword, COUNT(*) AS total
                FROM sciback_vectors,
                     jsonb_array_elements_text(metadata->'keywords') AS kw
                WHERE jsonb_typeof(metadata->'keywords') = 'array'
                  AND length(trim(kw)) > 3
                  AND (metadata->>'is_chunk' IS NULL OR metadata->>'is_chunk' = 'false')
                GROUP BY lower(trim(kw))
                ORDER BY total DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
    return [{"Keyword": r[0], "Documentos": r[1]} for r in rows]


@st.cache_data(ttl=300)
def _top_authors(limit: int = 10) -> list[dict]:
    """Top autores con más documentos."""
    container = get_container()
    from sqlalchemy import text

    engine = container.store._engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT trim(author) AS author, COUNT(*) AS total
                FROM sciback_vectors,
                     jsonb_array_elements_text(metadata->'authors') AS author
                WHERE jsonb_typeof(metadata->'authors') = 'array'
                  AND length(trim(author)) > 3
                  AND (metadata->>'is_chunk' IS NULL OR metadata->>'is_chunk' = 'false')
                GROUP BY trim(author)
                ORDER BY total DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
    return [{"Autor": r[0], "Documentos": r[1]} for r in rows]


@st.cache_data(ttl=60)
def _audit_metrics() -> dict:
    """Métricas del audit_log de los últimos 7 días."""
    container = get_container()
    repo = container.audit_repo  # type: ignore[union-attr]
    if repo._conn is None:  # type: ignore[union-attr]
        return {}
    try:
        rows = repo._conn.execute(  # type: ignore[union-attr]
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS last_24h,
                COUNT(*) FILTER (WHERE cached) AS cached,
                COUNT(*) FILTER (WHERE pii_detected) AS pii_detected,
                COUNT(*) FILTER (WHERE pii_redacted) AS pii_redacted,
                COUNT(*) FILTER (WHERE privacy_level = 'always_local') AS always_local,
                AVG(latency_ms)::int AS avg_latency_ms
            FROM audit_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        ).fetchone()
        return {
            "total_7d": int(rows[0] or 0),
            "last_24h": int(rows[1] or 0),
            "cached": int(rows[2] or 0),
            "pii_detected": int(rows[3] or 0),
            "pii_redacted": int(rows[4] or 0),
            "always_local": int(rows[5] or 0),
            "avg_latency_ms": int(rows[6] or 0),
        }
    except Exception:
        return {}


@st.cache_data(ttl=60)
def _audit_by_provider() -> list[dict]:
    """Queries últimas 7d por provider LLM."""
    container = get_container()
    repo = container.audit_repo  # type: ignore[union-attr]
    if repo._conn is None:  # type: ignore[union-attr]
        return []
    try:
        rows = repo._conn.execute(  # type: ignore[union-attr]
            """
            SELECT llm_provider, COUNT(*) AS total
            FROM audit_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY llm_provider
            ORDER BY total DESC
            """
        ).fetchall()
        return [{"Provider": r[0] or "?", "Queries": r[1]} for r in rows]
    except Exception:
        return []


@st.cache_data(ttl=60)
def _audit_by_intent() -> list[dict]:
    """Queries últimas 7d por intent."""
    container = get_container()
    repo = container.audit_repo  # type: ignore[union-attr]
    if repo._conn is None:  # type: ignore[union-attr]
        return []
    try:
        rows = repo._conn.execute(  # type: ignore[union-attr]
            """
            SELECT intent, gate_used, COUNT(*) AS total
            FROM audit_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY intent, gate_used
            ORDER BY total DESC
            """
        ).fetchall()
        return [
            {"Intent": r[0], "Gate": r[1], "Queries": r[2]} for r in rows
        ]
    except Exception:
        return []


@st.cache_data(ttl=60)
def _opensearch_status() -> dict:
    """Estado del cluster OpenSearch."""
    container = get_container()
    if container.search_adapter is None:  # type: ignore[union-attr]
        return {"enabled": False}
    try:
        import httpx

        url = _settings.opensearch_url or "http://opensearch:9200"
        h = httpx.get(f"{url}/_cluster/health", timeout=3).json()
        c = httpx.get(f"{url}/guia-publication/_count", timeout=3).json()
        return {
            "enabled": True,
            "status": h.get("status"),
            "nodes": h.get("number_of_nodes"),
            "docs": int(c.get("count", 0)),
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)[:80]}


def main() -> None:
    """Renderiza el dashboard."""
    st.title("📚 GUIA — Producción Científica UPeU")
    st.caption(
        f"Entorno: {_settings.environment} · LLM: {_settings.guia_llm_mode} · "
        f"Search: {_settings.search_backend}"
    )

    try:
        container = get_container()
        store = container.store  # type: ignore[union-attr]
    except Exception as exc:
        st.error(f"Error conectando: {exc}")
        return

    # ── KPIs principales ──────────────────────────────────────────────────
    st.header("Indicadores generales")
    by_src = _stats_by_source()
    total_parents = sum(s["Parents"] for s in by_src)
    total_chunks = sum(s["Chunks"] for s in by_src)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Documentos (parents)", f"{total_parents:,}")
    with col2:
        st.metric("Chunks (P3.1)", f"{total_chunks:,}")
    with col3:
        st.metric("Fuentes", len(by_src))
    with col4:
        os_st = _opensearch_status()
        if os_st.get("enabled") and "docs" in os_st:
            st.metric(f"OS [{os_st.get('status', '?')}]", f"{os_st['docs']:,}")
        else:
            st.metric("OpenSearch", "off")

    # ── Distribución por fuente ───────────────────────────────────────────
    st.subheader("Por fuente")
    if by_src:
        st.dataframe(by_src, use_container_width=True, hide_index=True)

    # ── Año ───────────────────────────────────────────────────────────────
    col_year, col_kw = st.columns(2)
    with col_year:
        st.subheader("Distribución por año")
        years = _stats_by_year()
        if years:
            st.bar_chart({"Documentos": {str(y["Año"]): y["Documentos"] for y in years}})
        else:
            st.info("Sin metadata de año disponible.")

    with col_kw:
        st.subheader("Top keywords")
        kws = _top_keywords(limit=15)
        if kws:
            st.dataframe(kws, use_container_width=True, hide_index=True, height=400)
        else:
            st.info("Sin keywords disponibles.")

    # ── Autores ───────────────────────────────────────────────────────────
    st.subheader("Top autores")
    authors = _top_authors(limit=10)
    if authors:
        st.dataframe(authors, use_container_width=True, hide_index=True)
    else:
        st.info("Sin autores indexados.")

    # ── Métricas de uso (audit_log) ───────────────────────────────────────
    st.header("Uso (últimos 7 días)")
    audit = _audit_metrics()
    if audit:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Queries 7d", f"{audit['total_7d']:,}")
        with c2:
            st.metric("Últimas 24h", f"{audit['last_24h']:,}")
        with c3:
            st.metric("Cache hits", f"{audit['cached']:,}")
        with c4:
            st.metric("Force local (privacidad)", f"{audit['always_local']:,}")
        with c5:
            st.metric("Latencia media", f"{audit['avg_latency_ms']} ms")

        col_p, col_i = st.columns(2)
        with col_p:
            st.subheader("Por proveedor LLM")
            providers = _audit_by_provider()
            if providers:
                st.dataframe(providers, use_container_width=True, hide_index=True)
        with col_i:
            st.subheader("Por intent + gate")
            intents = _audit_by_intent()
            if intents:
                st.dataframe(intents, use_container_width=True, hide_index=True)

        col_pii1, col_pii2 = st.columns(2)
        with col_pii1:
            st.metric("PII detectado en queries", audit["pii_detected"])
        with col_pii2:
            st.metric("PII redactado antes de cloud", audit["pii_redacted"])
    else:
        st.info("Sin datos de audit_log todavía. Las métricas aparecen tras las primeras queries.")

    # ── Búsqueda de prueba ────────────────────────────────────────────────
    st.header("🔎 Búsqueda semántica")
    query = st.text_input(
        "Consulta de prueba:",
        placeholder="inteligencia artificial educación superior",
    )
    if st.button("Buscar", type="primary") and query:
        try:
            search_svc = container.search_service  # type: ignore[union-attr]
            results = search_svc.search(query, limit=5)
            if not results:
                st.info("No se encontraron resultados.")
            else:
                st.subheader(f"Resultados ({len(results)})")
                for i, record in enumerate(results, 1):
                    title = record.metadata.get("title", record.id)
                    score = record.score
                    src = record.metadata.get("source", "?")
                    with st.expander(f"{i}. [{src}] {title} — score {score:.3f}"):
                        st.json(record.metadata)
        except Exception as exc:
            st.error(f"Error en búsqueda: {exc}")


if __name__ == "__main__":
    main()
