"""Discovery layer: serendipia controlada en respuestas RAG.

Genera 3 piezas que enriquecen las respuestas de búsqueda sin perder el foco:

1. **source_buckets** — agrupa los hits ya recuperados por fuente, con link al
   portal original con la query pre-cargada (p.ej. OPAC Koha, OJS).
2. **explore_in** — links a fuentes externas NO indexadas en GUIA (DSpace
   bloqueado, ALICIA), para abrir el horizonte cuando aplica.
3. **related_terms** — keywords sacadas de los `subjects` del top-K, sin
   repetir palabras de la query. Sirven como "búsquedas relacionadas".

Solo se invoca cuando el intent es de búsqueda real (RESEARCH/GENERAL) Y hay
hits o el index alternativo puede tener algo. NO se ejecuta para GREETING,
OUT_OF_SCOPE o CAMPUS (ese flujo tiene su propio render).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from guia.domain.chat import ExploreLink, SourceBucket

if TYPE_CHECKING:
    from guia.config import GUIASettings


_SOURCE_LABELS = {
    "koha": "Biblioteca UPeU (catálogo Koha)",
    "ojs": "Revistas UPeU (OJS)",
    "dspace": "Repositorio institucional (DSpace)",
    "alicia": "ALICIA — producción científica nacional",
}


def _koha_search_url(base: str, query: str) -> str:
    # OPAC Koha: /cgi-bin/koha/opac-search.pl?q=<query>
    return f"{base.rstrip('/')}/cgi-bin/koha/opac-search.pl?q={quote_plus(query)}"


def _ojs_search_url(base: str, query: str) -> str:
    # OJS site-wide search: /index.php/index/search/search?query=<q>
    return f"{base.rstrip('/')}/index.php/index/search/search?query={quote_plus(query)}"


def _dspace_search_url(base: str, query: str) -> str:
    # DSpace 7 UI: /search?query=<q>
    return f"{base.rstrip('/')}/search?query={quote_plus(query)}"


def _alicia_search_url(base: str, query: str) -> str:
    # ALICIA usa search?q=<query>
    return f"{base.rstrip('/')}/search?q={quote_plus(query)}"


def build_source_buckets(
    hits: list[dict],
    query: str,
    settings: GUIASettings,
) -> list[SourceBucket]:
    """Agrupa los hits por `source` y devuelve un bucket por cada fuente
    presente en el top-K, con link a la búsqueda en el portal correspondiente.

    Si la URL base de un portal no está configurada, ese bucket se omite (no
    inventamos links rotos).
    """
    if not hits:
        return []

    counts: Counter[str] = Counter()
    for h in hits:
        st = (h.get("source") or h.get("source_type") or "").strip().lower()
        if not st:
            # Inferir por prefijo del ID cuando el campo no viene del index
            hit_id = str(h.get("id", ""))
            if hit_id.startswith("koha:"):
                st = "koha"
            elif hit_id.startswith("ojs:"):
                st = "ojs"
            elif hit_id.startswith("dspace:"):
                st = "dspace"
        if st:
            counts[st] += 1

    buckets: list[SourceBucket] = []
    for source_type, count in counts.most_common():
        url: str | None = None
        if source_type == "koha" and settings.koha_opac_base_url:
            url = _koha_search_url(settings.koha_opac_base_url, query)
        elif source_type == "ojs" and settings.ojs_base_url:
            url = _ojs_search_url(settings.ojs_base_url, query)
        elif source_type == "dspace" and settings.dspace_base_url:
            url = _dspace_search_url(settings.dspace_base_url, query)
        elif source_type == "alicia" and settings.alicia_base_url:
            url = _alicia_search_url(settings.alicia_base_url, query)

        if not url:
            continue  # sin URL configurada → omitimos para no mentir

        buckets.append(
            SourceBucket(
                source_type=source_type,
                label=_SOURCE_LABELS.get(source_type, source_type),
                url=url,
                count=count,
            )
        )
    return buckets


def build_explore_links(
    query: str,
    buckets: list[SourceBucket],
    settings: GUIASettings,
) -> list[ExploreLink]:
    """Construye links a fuentes del ecosistema que NO están en `buckets`
    (porque no aportaron hits o porque no están indexadas en GUIA).

    Solo expone fuentes externas (DSpace, ALICIA) cuando están marcadas como
    no-indexadas. Si una fuente está indexada y no aparece en buckets es
    porque no tenía resultados relevantes — no la sugerimos para no generar
    ruido.
    """
    bucket_types = {b.source_type for b in buckets}
    links: list[ExploreLink] = []

    if (
        not settings.dspace_indexed
        and settings.dspace_base_url
        and "dspace" not in bucket_types
    ):
        links.append(
            ExploreLink(
                source_type="dspace",
                label=_SOURCE_LABELS["dspace"],
                url=_dspace_search_url(settings.dspace_base_url, query),
                available=False,
            )
        )

    if (
        not settings.alicia_indexed
        and settings.alicia_base_url
        and "alicia" not in bucket_types
    ):
        links.append(
            ExploreLink(
                source_type="alicia",
                label=_SOURCE_LABELS["alicia"],
                url=_alicia_search_url(settings.alicia_base_url, query),
                available=True,  # ALICIA siempre está pública
            )
        )

    return links


# Stopwords mínimas para filtrar términos ruido del query y de subjects.
# No es exhaustivo — la idea es solo evitar lo más evidente.
_QUERY_STOPWORDS = {
    "y", "o", "de", "del", "la", "el", "los", "las", "un", "una", "para",
    "con", "sin", "por", "sobre", "estoy", "buscando", "libros", "libro",
    "articulos", "artículos", "tesis", "informacion", "información", "que",
    "qué", "como", "cómo", "donde", "dónde", "ese", "esta", "este", "tema",
    "temas", "algo", "hay", "tienen", "tiene", "necesito", "quiero", "puedo",
    "puedes",
}


def _tokens(text: str) -> set[str]:
    """Extrae tokens normalizados de un texto (lowercase, sin puntuación)."""
    if not text:
        return set()
    # split por whitespace y puntuación; mantiene tildes
    raw = re.findall(r"[a-záéíóúñü]+", text.lower())
    return {t for t in raw if len(t) > 2 and t not in _QUERY_STOPWORDS}


def extract_related_terms(
    hits: list[dict],
    query: str,
    max_terms: int = 6,
) -> list[str]:
    """Extrae términos relacionados desde `subjects` / `subjects_ocde` de los hits.

    Excluye los términos que ya aparecen en la query (no sugerimos lo mismo
    que el usuario pidió). Ordena por frecuencia en el top-K.
    """
    if not hits:
        return []

    query_tokens = _tokens(query)
    counter: Counter[str] = Counter()

    for h in hits:
        for field in ("subjects", "subjects_ocde"):
            value = h.get(field) or []
            if isinstance(value, str):
                value = [value]
            for subj in value:
                if not isinstance(subj, str):
                    continue
                subj_norm = subj.strip()
                if not subj_norm or len(subj_norm) < 3:
                    continue
                # Si TODOS los tokens del subject ya están en la query, lo
                # consideramos redundante.
                subj_tokens = _tokens(subj_norm)
                if subj_tokens and subj_tokens.issubset(query_tokens):
                    continue
                counter[subj_norm] += 1

    return [term for term, _ in counter.most_common(max_terms)]
