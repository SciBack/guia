"""Chunking helpers — Parent-Document Retrieval (P3.1, ADR-037).

Cuando un texto es más largo que el límite de tokens del embedder
(`multilingual-e5-large` soporta ~512 tokens ≈ 250 words ≈ 1500 chars),
se chunkea en pasajes con overlap. Cada chunk lleva metadata:

    {
        "parent_id": "<pub_id>",
        "chunk_index": 0..N-1,
        "chunk_total": N,
        "is_chunk": True,
    }

En retrieval, varios chunks del mismo padre pueden aparecer entre los
top-K. El SearchService.search() (función dedupe_by_parent) los colapsa
y devuelve el documento padre completo (recuperándolo de la Capa B del
document store si no estaba en los hits).
"""

from __future__ import annotations

from collections.abc import Iterator

# Defaults alineados con multilingual-e5-large (512 tokens ≈ 250 words).
DEFAULT_MAX_WORDS = 250
DEFAULT_OVERLAP = 50


def chunk_text(
    text: str,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Divide texto en chunks de ~max_words palabras con overlap.

    Args:
        text: Texto fuente.
        max_words: Tamaño objetivo del chunk en palabras.
        overlap: Palabras de overlap entre chunks consecutivos.

    Returns:
        Lista de strings, cada uno con ≤ max_words palabras.
        Si el texto cabe en un solo chunk, retorna [text].

    Notas:
        - Splits por whitespace (no por sentencia). Para chunking
          sentence-aware ver _chunk_text_sentences (futuro, requiere NLTK).
        - overlap=0 produce chunks disjuntos.
        - overlap >= max_words es inválido (loop infinito) → ValueError.
    """
    if max_words <= 0:
        raise ValueError("max_words debe ser > 0")
    if overlap < 0:
        raise ValueError("overlap debe ser >= 0")
    if overlap >= max_words:
        raise ValueError(f"overlap ({overlap}) debe ser < max_words ({max_words})")

    text = text.strip()
    if not text:
        return []

    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks: list[str] = []
    step = max_words - overlap
    i = 0
    while i < len(words):
        chunk_words = words[i : i + max_words]
        chunks.append(" ".join(chunk_words))
        i += step
        # Evita un último chunk degenerado de sobra-overlap
        if i + overlap >= len(words):
            break

    # Si quedan words al final no cubiertos, agregar último chunk
    last_end = (len(chunks) - 1) * step + max_words
    if last_end < len(words):
        chunks.append(" ".join(words[-max_words:]))

    return chunks


def make_chunk_id(parent_id: str, chunk_index: int) -> str:
    """ID determinístico de un chunk a partir del parent_id."""
    return f"{parent_id}#chunk_{chunk_index}"


def make_chunk_metadata(
    parent_id: str,
    chunk_index: int,
    chunk_total: int,
    parent_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Construye metadata mínima para un chunk.

    Hereda title / source / authors del padre (para que el chunk sea
    auto-contenido en retrieval), pero NO el abstract/toc/description_full
    completos (esos viven solo en el padre — Capa B).
    """
    meta: dict[str, object] = {
        "parent_id": parent_id,
        "chunk_index": chunk_index,
        "chunk_total": chunk_total,
        "is_chunk": True,
    }
    if parent_meta:
        for k in ("title", "source", "authors", "year", "kind"):
            if k in parent_meta:
                meta[k] = parent_meta[k]
    return meta


def iter_chunks_for_publication(
    parent_id: str,
    parent_text: str,
    parent_meta: dict[str, object],
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap: int = DEFAULT_OVERLAP,
) -> Iterator[tuple[str, str, dict[str, object]]]:
    """Genera (chunk_id, chunk_text, chunk_metadata) por chunk.

    Si el texto cabe en un solo chunk, no yield-ea nada — el padre ya
    se indexa por separado en el flujo principal del harvester.
    """
    chunks = chunk_text(parent_text, max_words=max_words, overlap=overlap)
    if len(chunks) <= 1:
        return  # solo padre, no hay chunks extra

    for i, ct in enumerate(chunks):
        cid = make_chunk_id(parent_id, i)
        cmeta = make_chunk_metadata(parent_id, i, len(chunks), parent_meta)
        yield cid, ct, cmeta
