"""Benchmark Qwen 7B (Mac Mini) vs Mistral Small 4 (NIM) vs Nemotron 3 Nano 30B (NIM).

Las 20 queries del bench original, esta vez con candidatos rápidos para ver
si alguno sirve de hub agéntico interactivo (<10s mediana, calidad ≥ Qwen).
"""
from __future__ import annotations
import asyncio
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

OLLAMA_URL = os.environ["OLLAMA_BASE_URL"]
OLLAMA_KEY = os.environ["OLLAMA_API_KEY"]
NIM_URL = os.environ["NVIDIA_NIM_BASE_URL"]
NIM_KEY = os.environ["NVIDIA_NIM_API_KEY"]

PROVIDERS = [
    {"name": "qwen2.5:7b", "base": OLLAMA_URL + "/v1", "key": OLLAMA_KEY, "model": "qwen2.5:7b"},
    {"name": "mistral-small-4", "base": NIM_URL, "key": NIM_KEY, "model": "mistralai/mistral-small-4-119b-2603"},
    {"name": "nemotron-nano-30b", "base": NIM_URL, "key": NIM_KEY, "model": "nvidia/nemotron-3-nano-30b-a3b"},
]

SYSTEM = (
    "Eres GUIA, asistente académico de la Universidad Peruana Unión (UPeU). "
    "Respondes SIEMPRE en español. Conciso, preciso, citas fuentes cuando aplica. "
    "Si la pregunta es trivial (saludo), responde en máximo una oración."
)

QUERIES: list[dict[str, str]] = [
    {"category": "greeting", "query": "Hola"},
    {"category": "greeting", "query": "Buenos días, ¿cómo estás?"},
    {"category": "greeting", "query": "Gracias por la ayuda"},
    {"category": "greeting", "query": "Hasta luego"},
    {"category": "greeting", "query": "ok"},
    {"category": "meta", "query": "¿Qué eres y qué puedes hacer?"},
    {"category": "meta", "query": "¿De qué fuentes obtienes información?"},
    {"category": "meta", "query": "¿Puedo descargar los textos completos de las tesis?"},
    {"category": "meta", "query": "¿Cómo cito una tesis encontrada aquí en APA?"},
    {"category": "meta", "query": "¿Manejas información personal de los usuarios?"},
    {"category": "academic", "query": "¿Qué tesis hay sobre diabetes mellitus tipo 2 en adultos mayores en Perú?"},
    {"category": "academic", "query": "Resumen de los métodos de investigación cuantitativa más usados en tesis de enfermería peruanas"},
    {"category": "academic", "query": "Diferencia entre estudio transversal y longitudinal en epidemiología"},
    {"category": "academic", "query": "¿Qué autores peruanos han publicado sobre educación adventista en la última década?"},
    {"category": "academic", "query": "Explica el modelo de creencias en salud aplicado a prevención de COVID-19"},
    {"category": "academic", "query": "Compara el enfoque cualitativo vs mixto para tesis en ciencias de la salud"},
    {"category": "academic", "query": "¿Qué normas peruanas regulan la ética en investigación con seres humanos?"},
    {"category": "academic", "query": "Tesis sobre teletrabajo y salud mental en docentes universitarios peruanos"},
    {"category": "academic", "query": "Define burnout académico y menciona sus principales dimensiones según Maslach"},
    {"category": "academic", "query": "¿Qué es CONCYTEC y cuál es su rol en la investigación universitaria peruana?"},
]


async def call(client: httpx.AsyncClient, prov: dict, query: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{prov['base']}/chat/completions",
            headers={"Authorization": f"Bearer {prov['key']}", "Content-Type": "application/json"},
            json={
                "model": prov["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 1200,
                "temperature": 0.3,
            },
            timeout=120.0,
        )
        lat = time.perf_counter() - t0
        if r.status_code != 200:
            return {"ok": False, "latency_s": round(lat, 1), "error": f"{r.status_code}: {r.text[:150]}"}
        d = r.json()
        msg = d["choices"][0]["message"]["content"]
        u = d.get("usage", {})
        return {
            "ok": True,
            "latency_s": round(lat, 2),
            "content": msg,
            "tokens_in": u.get("prompt_tokens"),
            "tokens_out": u.get("completion_tokens"),
        }
    except Exception as e:
        return {"ok": False, "latency_s": round(time.perf_counter() - t0, 1), "error": str(e)[:150]}


async def run_query(client: httpx.AsyncClient, item: dict, idx: int, total: int) -> dict:
    print(f"[{idx:02d}/{total}] {item['category']:8s} | {item['query'][:55]}...", flush=True)
    results = await asyncio.gather(*[call(client, p, item["query"]) for p in PROVIDERS])
    row = dict(item)
    for prov, res in zip(PROVIDERS, results):
        row[prov["name"]] = res
        status = "OK" if res["ok"] else "ERR"
        print(f"   {prov['name']:<22} {res['latency_s']:>5.1f}s {status}", flush=True)
    return row


async def main():
    print("Providers:", [p["name"] for p in PROVIDERS])
    print(f"Queries: {len(QUERIES)}\n")
    async with httpx.AsyncClient() as client:
        results = []
        for i, item in enumerate(QUERIES, 1):
            results.append(await run_query(client, item, i, len(QUERIES)))

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(__file__).parent / "bench_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"multi_{ts}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # Resumen
    lines = [f"# Benchmark multi-provider — {ts}\n", "## Latencia mediana / max / err\n"]
    header = "| Categoría | N |"
    sep = "|---|---|"
    for p in PROVIDERS:
        header += f" {p['name']} med | max | err |"
        sep += "---|---|---|"
    lines.append(header)
    lines.append(sep)
    for cat in ("greeting", "meta", "academic"):
        rows = [r for r in results if r["category"] == cat]
        line = f"| {cat} | {len(rows)} |"
        for p in PROVIDERS:
            oks = [r[p["name"]]["latency_s"] for r in rows if r[p["name"]]["ok"]]
            errs = sum(1 for r in rows if not r[p["name"]]["ok"])
            if oks:
                line += f" {statistics.median(oks):.1f}s | {max(oks):.1f}s | {errs} |"
            else:
                line += f" - | - | {errs} |"
        lines.append(line)
    lines.append("\n## Respuestas\n")
    for r in results:
        lines.append(f"### [{r['category']}] {r['query']}\n")
        for p in PROVIDERS:
            res = r[p["name"]]
            lines.append(f"**{p['name']}** ({res.get('latency_s')}s, {res.get('tokens_out')} tok):")
            lines.append(f"> {res.get('content', res.get('error', '?'))[:1500]}\n")
        lines.append("---\n")
    (out_dir / f"multi_{ts}.md").write_text("\n".join(lines))

    print(f"\n✅ JSON: bench_results/multi_{ts}.json")
    print(f"✅ MD:   bench_results/multi_{ts}.md")


if __name__ == "__main__":
    asyncio.run(main())
