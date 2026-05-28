"""Smoke test del AgentOrchestrator (Día 1) con NIM real + SearchService fake.

Objetivo: validar que Mistral Small 4 vía NIM realmente:
1. Emite JSON válido del schema AgentAction
2. Sigue las instrucciones del system prompt
3. Llama search() apropiadamente
4. Cita doc_ids reales (no inventados)
5. Termina en ≤3 iteraciones

No prueba calidad del retrieval (FakeSearchService es trivial keyword matching).
Prueba el LOOP y el CONTRATO LLM↔JSON.

Uso:
    cd ~/proyectos/sciback/guia
    set -a && source ~/.secrets/nvidia-nim.env && set +a
    uv run --quiet python tests/eval/smoke_orchestrator_nim.py
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from sciback_core.ports.llm import LLMMessage
from sciback_core.ports.vector_store import VectorRecord
from sciback_llm_nim import NIMAdapter, NIMConfig

from guia.services.agent_orchestrator import (
    AgentOrchestrator,
    OrchestratorResult,
)

# -------- Datos fake estilo UPeU (mini-corpus) --------
DOCS: list[VectorRecord] = [
    VectorRecord(
        id="koha:t-001",
        vector=[0.0] * 8,
        score=0.0,
        metadata={
            "title": "Diabetes mellitus tipo 2 en adultos mayores: factores de riesgo en Lima Este",
            "author": "Garcia, L. M.",
            "year": 2023,
            "source": "koha",
            "text": "Tesis sobre prevalencia de diabetes mellitus tipo 2 en adultos mayores en Lima Este, Peru. Estudio transversal en 320 participantes.",
        },
    ),
    VectorRecord(
        id="koha:t-002",
        vector=[0.0]*8,
        score=0.0,
        metadata={
            "title": "Adherencia al tratamiento en pacientes diabeticos del Hospital Almenara",
            "author": "Mendoza, R.",
            "year": 2022,
            "source": "koha",
            "text": "Estudio sobre adherencia al tratamiento farmacologico de la diabetes en pacientes adultos atendidos en EsSalud.",
        },
    ),
    VectorRecord(
        id="ojs:a-101",
        vector=[0.0]*8,
        score=0.0,
        metadata={
            "title": "Etica en investigacion con seres humanos en universidades peruanas",
            "author": "Rojas, P.",
            "year": 2024,
            "source": "ojs",
            "text": "Revision de la normativa peruana sobre etica en investigacion: Ley 26842, DS 011-2017-JUS, rol del INS.",
        },
    ),
    VectorRecord(
        id="ojs:a-102",
        vector=[0.0]*8,
        score=0.0,
        metadata={
            "title": "El rol del CONCYTEC en el financiamiento de la investigacion universitaria 2018-2023",
            "author": "Torres, A.",
            "year": 2024,
            "source": "ojs",
            "text": "Analisis del rol del Consejo Nacional de Ciencia y Tecnologia (CONCYTEC) en programas como FONDECYT y PROCIENCIA.",
        },
    ),
    VectorRecord(
        id="koha:t-003",
        vector=[0.0]*8,
        score=0.0,
        metadata={
            "title": "Burnout academico en estudiantes de enfermeria UPeU",
            "author": "Quispe, M.",
            "year": 2023,
            "source": "koha",
            "text": "Estudio del burnout academico segun las dimensiones de Maslach en estudiantes de enfermeria de la Universidad Peruana Union.",
        },
    ),
]


def keyword_score(query: str, doc: VectorRecord) -> float:
    """Score trivial por overlap de tokens (NO es semantica)."""
    q_tokens = {t.lower() for t in query.split() if len(t) > 3}
    text = (
        str(doc.metadata.get("title", ""))
        + " "
        + str(doc.metadata.get("text", ""))
    ).lower()
    if not q_tokens:
        return 0.0
    hits = sum(1 for t in q_tokens if t in text)
    return hits / len(q_tokens)


class FakeSearchService:
    """Simula SearchService.search() con keyword matching trivial."""

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> list[VectorRecord]:
        scored = [(keyword_score(query, d), d) for d in DOCS]
        scored = [(s, d) for s, d in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            VectorRecord(id=d.id, vector=d.vector, score=s, metadata=d.metadata)
            for s, d in scored[:limit]
        ]


# -------- Queries representativas --------
QUERIES: list[dict[str, str]] = [
    {"label": "academic-clear", "query": "¿Qué tesis hay sobre diabetes mellitus en adultos mayores en Peru?"},
    {"label": "academic-meta", "query": "¿Qué es CONCYTEC y cuál es su rol?"},
    {"label": "academic-no-results", "query": "¿Hay tesis sobre criptografía cuántica en agricultura andina?"},
    {"label": "greeting", "query": "Hola"},
    {"label": "vague", "query": "tesis"},
]


def format_result(label: str, q: str, res: OrchestratorResult, total_s: float) -> str:
    actions = " → ".join(t.action for t in res.trace) if res.trace else "(sin acciones)"
    src_ids = [s.id for s in res.sources]
    answer = res.answer.replace("\n", " ")
    if len(answer) > 280:
        answer = answer[:280] + "..."
    return (
        f"\n[{label}] {q}\n"
        f"  iters={res.iterations} fallback={res.fallback} clarif={res.is_clarification}\n"
        f"  actions: {actions}\n"
        f"  sources: {src_ids if src_ids else '(ninguna)'}\n"
        f"  total: {total_s:.1f}s\n"
        f"  answer: {answer}"
    )


async def main() -> None:
    print("=" * 80)
    print("SMOKE TEST AgentOrchestrator + NIM Mistral Small 4")
    print("=" * 80)

    cfg = NIMConfig()
    print(f"Endpoint: {cfg.base_url}")
    print(f"Model:    {cfg.default_model}")
    print(f"Mini-corpus: {len(DOCS)} docs UPeU")

    with NIMAdapter(cfg) as llm:
        orchestrator = AgentOrchestrator(
            llm=llm,
            search=FakeSearchService(),  # type: ignore[arg-type]
            max_iter=3,
            max_tokens_per_action=512,
            institution="Universidad Peruana Union",
        )

        for item in QUERIES:
            t0 = time.perf_counter()
            try:
                res = await orchestrator.run(
                    query=item["query"],
                    history=[],
                    privacy_verdict=None,
                )
                total = time.perf_counter() - t0
                print(format_result(item["label"], item["query"], res, total))
            except Exception as e:
                total = time.perf_counter() - t0
                print(f"\n[{item['label']}] {item['query']}\n  ERROR: {type(e).__name__}: {e} ({total:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
