"""Tests del QueryRewriter — pipeline NLP orquestador (ADR-044)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_rewrite_saludo_prefijado() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None)
    result = await rw.rewrite("hola, ¿tienes libros sobre excel?")
    assert result.is_search_query
    assert "hola" not in result.cleaned.lower()
    assert not result.used_llm


@pytest.mark.asyncio
async def test_rewrite_preserva_query_limpia() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None)
    query = "tesis de inteligencia artificial"
    result = await rw.rewrite(query)
    assert result.is_search_query
    assert "inteligencia artificial" in result.cleaned.lower()
    assert not result.used_llm


@pytest.mark.asyncio
async def test_rewrite_extrae_fecha() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None)
    result = await rw.rewrite("tesis del año pasado sobre IA")
    assert result.date_filters is not None
    assert "gte" in result.date_filters
    assert not result.used_llm


@pytest.mark.asyncio
async def test_rewrite_solo_saludo_no_es_busqueda() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None)
    result = await rw.rewrite("hola")
    assert not result.is_search_query
    assert not result.used_llm


@pytest.mark.asyncio
async def test_rewrite_sin_historia_no_usa_llm() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None, enable_llm_fallback=True)
    result = await rw.rewrite("y los del año anterior?", history=None)
    assert not result.used_llm


@pytest.mark.asyncio
async def test_rewrite_query_vacia() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter()
    result = await rw.rewrite("")
    assert not result.is_search_query
    assert result.cleaned == ""


@pytest.mark.asyncio
async def test_rewrite_expande_siglas() -> None:
    from guia.services.query_rewriter import QueryRewriter
    rw = QueryRewriter(fast_llm=None)
    result = await rw.rewrite("proyectos de IA y TIC")
    assert "inteligencia artificial" in result.cleaned.lower()
