"""Fixtures compartidas para los tests de GUIA."""

from __future__ import annotations

import pytest
from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter


@pytest.fixture
def stub_llm() -> InMemoryLLMAdapter:
    """LLM stub con respuesta canned configurable."""
    return InMemoryLLMAdapter(canned_response="Respuesta de prueba GUIA", embedding_dim=8)


@pytest.fixture
def stub_store() -> InMemoryVectorStoreAdapter:
    """Vector store in-memory (dim=8 para tests rápidos)."""
    return InMemoryVectorStoreAdapter(dim=8)


@pytest.fixture
def stub_store_with_data(stub_store: InMemoryVectorStoreAdapter) -> InMemoryVectorStoreAdapter:
    """Vector store con datos pre-cargados para tests de búsqueda."""
    stub_store.upsert(
        "pub-001",
        [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        metadata={
            "title": "Inteligencia Artificial en Educación Superior",
            "abstract": "Estudio sobre el impacto de la IA en universidades peruanas.",
            "source": "dspace",
            "year": 2023,
            "authors": ["García, J.", "López, M."],
        },
    )
    stub_store.upsert(
        "pub-002",
        [0.0, 0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
        metadata={
            "title": "Repositorios institucionales y acceso abierto",
            "abstract": "Análisis de repositorios DSpace en universidades LATAM.",
            "source": "ojs",
            "year": 2022,
            "authors": ["Pérez, A."],
        },
    )
    return stub_store
