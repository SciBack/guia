"""Presentación pura de respuestas del chat (sin dependencias de Chainlit ni DB).

Vive separado de `chainlit_app` porque ese módulo abre el Data Layer (Postgres)
al importarse; estas funciones son lógica de formato pura y deben ser testeables
sin servicios externos.
"""

from __future__ import annotations

from guia.domain.chat import ChatResponse

_SOURCE_LABELS = {
    "koha": "📕 Biblioteca UPeU",
    "ojs": "📄 Revistas UPeU",
    "dspace": "📦 Repositorio",
    "alicia": "🔬 ALICIA",
}
_MAX_LIST_ITEMS = 15


def render_results_list(response: ChatResponse) -> str:
    """Listado de resultados con enlace inline por ítem (answer_type == 'list').

    Cada resultado es un enlace clicable directo al recurso (OPAC de Koha /
    artículo OJS), agrupado por fuente. No se añade la sección "Fuente
    consultada" — los enlaces ya están en el listado, evitando duplicar títulos.
    """
    by_type: dict[str, list] = {}
    for s in response.sources:
        by_type.setdefault(s.source_type or "unknown", []).append(s)

    total = len(response.sources)
    plural = "s" if total != 1 else ""
    lines = [f"**{total} resultado{plural} encontrado{plural}**\n"]
    multi = len(by_type) > 1
    for stype, items in by_type.items():
        if multi:
            lines.append(f"\n**{_SOURCE_LABELS.get(stype, stype.title())}**")
        for s in items[:_MAX_LIST_ITEMS]:
            title = s.title[:80] + ("…" if len(s.title) > 80 else "")
            title_link = f"[{title}]({s.url})" if s.url else title
            meta_parts: list[str] = []
            if s.authors:
                meta_parts.append(", ".join(s.authors[:2]))
            if s.year:
                meta_parts.append(str(s.year))
            meta = f" — *{' · '.join(meta_parts)}*" if meta_parts else ""
            lines.append(f"- {title_link}{meta}")

    # Si un portal tiene más hits de los mostrados, ofrecer el enlace al portal.
    for bucket in response.source_buckets:
        shown = min(len(by_type.get(bucket.source_type, [])), _MAX_LIST_ITEMS)
        if bucket.count > shown:
            lines.append(f"\n[Ver más en {bucket.label} →]({bucket.url})")
    return "\n".join(lines)
