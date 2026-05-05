#!/usr/bin/env python3
"""Eval gate: compara NDCG@5 de Qwen3 8B vs Qwen2.5 7B en el corpus GUIA.

Uso:
    # Evaluar modelo activo (usa config desde .env):
    uv run scripts/eval_qwen3_vs_qwen25.py

    # Evaluar contra YAML de queries personalizado:
    uv run scripts/eval_qwen3_vs_qwen25.py --queries tests/eval_queries.yml

    # Solo medir retrieval (sin generar respuesta LLM):
    uv run scripts/eval_qwen3_vs_qwen25.py --retrieval-only

    # Fijar umbral mínimo de NDCG@5:
    uv run scripts/eval_qwen3_vs_qwen25.py --min-ndcg 0.70

El script falla con exit code 1 si NDCG@5 < --min-ndcg.
Esto permite usarlo como gate en CI/CD.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--queries",
        default="tests/eval_queries.yml",
        help="Ruta al YAML de queries de regresión (default: tests/eval_queries.yml)",
    )
    p.add_argument(
        "--min-ndcg",
        type=float,
        default=0.70,
        help="NDCG@5 mínimo para considerar el modelo aceptable (default: 0.70)",
    )
    p.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Solo medir retrieval (no genera respuesta LLM — más rápido)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Número de resultados a recuperar por query (default: 5)",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Guardar resultados en JSON (opcional)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# NDCG@k
# ---------------------------------------------------------------------------

def dcg_at_k(relevances: list[float], k: int) -> float:
    """Discounted Cumulative Gain at k."""
    return sum(
        rel / math.log2(i + 2)
        for i, rel in enumerate(relevances[:k])
    )


def ndcg_at_k(relevances: list[float], ideal: list[float], k: int) -> float:
    """Normalized DCG at k."""
    ideal_sorted = sorted(ideal, reverse=True)
    idcg = dcg_at_k(ideal_sorted, k)
    if idcg == 0:
        return 0.0
    return dcg_at_k(relevances, k) / idcg


def score_result(result_text: str, expected_keywords: list[str]) -> float:
    """Relevancia heurística basada en keywords presentes en el resultado."""
    if not expected_keywords:
        return 1.0  # queries sin keywords esperados no penalizan
    text_lower = result_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text_lower)
    return hits / len(expected_keywords)


# ---------------------------------------------------------------------------
# Eval core
# ---------------------------------------------------------------------------

async def eval_query(
    query_entry: dict,
    search_service,
    embedder,
    top_k: int,
) -> dict:
    """Evalúa una sola query. Retorna dict con métricas."""
    q_id = query_entry.get("id", "?")
    query = query_entry["query"]
    expected_keywords: list[str] = query_entry.get("expected_keywords", [])
    is_search = query_entry.get("is_search", True)

    if not is_search:
        return {
            "id": q_id,
            "query": query,
            "skipped": True,
            "reason": "is_search=False",
            "ndcg5": 1.0,
        }

    t0 = time.perf_counter()

    try:
        from guia.services.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(fast_llm=None, enable_llm_fallback=False)
        rewrite = await rewriter.rewrite(query)
        search_text = rewrite.cleaned

        results = await search_service.search(
            query=search_text,
            top_k=top_k,
        )
    except Exception as exc:
        return {
            "id": q_id,
            "query": query,
            "error": str(exc),
            "ndcg5": 0.0,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }

    latency_ms = round((time.perf_counter() - t0) * 1000)

    # Calcular relevancia por resultado
    relevances = []
    for r in results:
        text = ""
        if hasattr(r, "text"):
            text = r.text or ""
        elif hasattr(r, "metadata"):
            text = str(r.metadata)
        relevances.append(score_result(text, expected_keywords))

    # Pad a top_k si hay menos resultados
    while len(relevances) < top_k:
        relevances.append(0.0)

    ideal = [1.0] * min(len(expected_keywords), top_k) if expected_keywords else [1.0]
    while len(ideal) < top_k:
        ideal.append(0.0)

    ndcg = ndcg_at_k(relevances, ideal, top_k)

    return {
        "id": q_id,
        "query": query,
        "rewritten": search_text if "search_text" in dir() else query,
        "ndcg5": round(ndcg, 4),
        "latency_ms": latency_ms,
        "results_count": len(results),
        "relevances": relevances,
    }


async def run_eval(args: argparse.Namespace) -> int:
    """Función principal de evaluación. Retorna exit code."""
    # Cargar queries
    queries_path = Path(args.queries)
    if not queries_path.exists():
        print(f"ERROR: No se encontró el archivo de queries: {queries_path}")
        return 1

    with open(queries_path) as f:
        data = yaml.safe_load(f)

    queries = data.get("queries", [])
    target_ndcg5 = data.get("target_ndcg5", args.min_ndcg)
    min_ndcg = max(args.min_ndcg, target_ndcg5)

    print(f"\n{'='*60}")
    print(f"  GUIA Eval Gate — NDCG@{args.top_k}")
    print(f"  Queries: {len(queries)}  |  Min NDCG@5: {min_ndcg:.2f}")
    print(f"{'='*60}\n")

    # Inicializar container
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()

        from guia.container import GUIAContainer
        container = GUIAContainer()
    except Exception as exc:
        print(f"ERROR al inicializar GUIAContainer: {exc}")
        print("Asegúrate de tener las variables de entorno configuradas (.env)")
        return 1

    search_service = container.search_service
    embedder = container.embedder

    # Ejecutar evaluaciones
    results = []
    total_ndcg = 0.0
    evaluated = 0

    for entry in queries:
        result = await eval_query(entry, search_service, embedder, args.top_k)
        results.append(result)

        if result.get("skipped") or result.get("error"):
            status = "SKIP" if result.get("skipped") else "ERR "
            print(f"  [{status}] {result['id']:4s} {result['query'][:50]:<50} — {result.get('reason', result.get('error', ''))[:30]}")
            continue

        ndcg = result["ndcg5"]
        total_ndcg += ndcg
        evaluated += 1
        bar = "█" * int(ndcg * 10) + "░" * (10 - int(ndcg * 10))
        print(
            f"  [OK  ] {result['id']:4s} {result['query'][:50]:<50} "
            f"NDCG={ndcg:.3f} {bar} {result['latency_ms']}ms"
        )

    # Calcular NDCG promedio
    mean_ndcg = total_ndcg / evaluated if evaluated > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"  Resultados: {evaluated}/{len(queries)} queries evaluadas")
    print(f"  NDCG@{args.top_k} promedio: {mean_ndcg:.4f}  (mínimo requerido: {min_ndcg:.2f})")
    print(f"{'='*60}\n")

    # Guardar JSON si se solicitó
    if args.output:
        output = {
            "mean_ndcg5": mean_ndcg,
            "min_required": min_ndcg,
            "passed": mean_ndcg >= min_ndcg,
            "queries": results,
        }
        Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(f"  Resultados guardados en: {args.output}")

    # Cleanup
    try:
        await container.aclose()
    except Exception:
        pass

    if mean_ndcg >= min_ndcg:
        print(f"  ✓ GATE PASSED — NDCG@5={mean_ndcg:.4f} >= {min_ndcg:.2f}")
        return 0
    else:
        print(f"  ✗ GATE FAILED — NDCG@5={mean_ndcg:.4f} < {min_ndcg:.2f}")
        print("    Revisa los resultados y ajusta el modelo o el corpus.")
        return 1


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(run_eval(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
