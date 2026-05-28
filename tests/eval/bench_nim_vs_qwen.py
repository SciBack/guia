"""Benchmark Qwen 7B (Mac Mini local) vs Nemotron 120B (NVIDIA NIM).

Mide latencia y captura respuestas para evaluación cualitativa antes de
decidir si NIM reemplaza a Qwen para síntesis L0/L1 en GUIA.

Uso:
    cd ~/proyectos/sciback/guia
    source ~/.secrets/macmini.env && source ~/.secrets/nvidia-nim.env
    uv run python tests/eval/bench_nim_vs_qwen.py

Salida:
    tests/eval/bench_results/bench_<timestamp>.json  (raw)
    tests/eval/bench_results/bench_<timestamp>.md    (tabla legible)
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

# ----- Config -----
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://192.168.62.73:8080")
OLLAMA_KEY = os.environ.get("OLLAMA_API_KEY", "")
NIM_URL = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")

QWEN_MODEL = "qwen2.5:7b"
NIM_MODEL = "nvidia/nemotron-3-super-120b-a12b"

SYSTEM_PROMPT = (
    "Eres GUIA, asistente académico de la Universidad Peruana Unión (UPeU). "
    "Respondes SIEMPRE en español. Conciso, preciso y citas fuentes cuando aplica. "
    "Si la pregunta es trivial (saludo, agradecimiento), responde en máximo una oración."
)

# 20 queries representativas — 5 saludos + 5 meta + 10 académicas
QUERIES: list[dict[str, str]] = [
    # Saludos / triviales
    {"category": "greeting", "query": "Hola"},
    {"category": "greeting", "query": "Buenos días, ¿cómo estás?"},
    {"category": "greeting", "query": "Gracias por la ayuda"},
    {"category": "greeting", "query": "Hasta luego"},
    {"category": "greeting", "query": "ok"},
    # Meta — sobre GUIA / la biblioteca
    {"category": "meta", "query": "¿Qué eres y qué puedes hacer?"},
    {"category": "meta", "query": "¿De qué fuentes obtienes información?"},
    {"category": "meta", "query": "¿Puedo descargar los textos completos de las tesis?"},
    {"category": "meta", "query": "¿Cómo cito una tesis encontrada aquí en APA?"},
    {"category": "meta", "query": "¿Manejas información personal de los usuarios?"},
    # Académicas — queries reales de discovery universitario
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


async def call_qwen(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    """Llama Qwen 7B local vía Ollama API OpenAI-compatible."""
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {OLLAMA_KEY}"},
            json={
                "model": QWEN_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            },
            timeout=120.0,
        )
        latency = time.perf_counter() - t0
        if resp.status_code != 200:
            return {"ok": False, "latency_s": latency, "error": f"{resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        msg = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "ok": True,
            "latency_s": round(latency, 2),
            "content": msg,
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
        }
    except Exception as e:
        return {"ok": False, "latency_s": round(time.perf_counter() - t0, 2), "error": str(e)[:200]}


async def call_nim(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    """Llama Nemotron 120B vía NVIDIA NIM."""
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{NIM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {NIM_KEY}", "Content-Type": "application/json"},
            json={
                "model": NIM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 4000,  # alto porque el modelo razona internamente
                "temperature": 0.3,
            },
            timeout=180.0,
        )
        latency = time.perf_counter() - t0
        if resp.status_code != 200:
            return {"ok": False, "latency_s": latency, "error": f"{resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        msg = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "ok": True,
            "latency_s": round(latency, 2),
            "content": msg,
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
        }
    except Exception as e:
        return {"ok": False, "latency_s": round(time.perf_counter() - t0, 2), "error": str(e)[:200]}


async def run_query(client: httpx.AsyncClient, item: dict[str, str], idx: int, total: int) -> dict[str, Any]:
    """Llama ambos modelos en paralelo para una query."""
    print(f"[{idx:02d}/{total}] {item['category']:8s} | {item['query'][:60]}...", flush=True)
    qwen, nim = await asyncio.gather(
        call_qwen(client, item["query"]),
        call_nim(client, item["query"]),
    )
    print(
        f"          Qwen: {qwen['latency_s']:5.1f}s {'OK' if qwen['ok'] else 'ERR'} | "
        f"NIM: {nim['latency_s']:6.1f}s {'OK' if nim['ok'] else 'ERR'}",
        flush=True,
    )
    return {**item, "qwen": qwen, "nim": nim}


async def main() -> None:
    if not OLLAMA_KEY:
        raise SystemExit("Falta OLLAMA_API_KEY — source ~/.secrets/macmini.env")
    if not NIM_KEY:
        raise SystemExit("Falta NVIDIA_NIM_API_KEY — source ~/.secrets/nvidia-nim.env")

    print(f"Qwen endpoint: {OLLAMA_URL} | model={QWEN_MODEL}")
    print(f"NIM  endpoint: {NIM_URL} | model={NIM_MODEL}")
    print(f"Queries: {len(QUERIES)}\n")

    async with httpx.AsyncClient() as client:
        results: list[dict[str, Any]] = []
        for i, item in enumerate(QUERIES, 1):
            res = await run_query(client, item, i, len(QUERIES))
            results.append(res)

    # ---- Aggregate ----
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(__file__).parent / "bench_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"bench_{ts}.json"
    md_path = out_dir / f"bench_{ts}.md"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # ---- Stats por categoría ----
    def lat(rows: list[dict], provider: str) -> tuple[float, float, int]:
        oks = [r[provider]["latency_s"] for r in rows if r[provider]["ok"]]
        errs = sum(1 for r in rows if not r[provider]["ok"])
        if not oks:
            return (0.0, 0.0, errs)
        return (statistics.median(oks), max(oks), errs)

    lines = [f"# Benchmark Qwen 7B vs Nemotron 120B — {ts}\n"]
    lines.append("## Resumen latencia (mediana / max / errores)\n")
    lines.append("| Categoría | N | Qwen mediana | Qwen max | Qwen err | NIM mediana | NIM max | NIM err |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for cat in ("greeting", "meta", "academic"):
        rows = [r for r in results if r["category"] == cat]
        qm, qmax, qerr = lat(rows, "qwen")
        nm, nmax, nerr = lat(rows, "nim")
        lines.append(f"| {cat} | {len(rows)} | {qm:.1f}s | {qmax:.1f}s | {qerr} | {nm:.1f}s | {nmax:.1f}s | {nerr} |")
    lines.append("")
    lines.append("## Respuestas (para evaluación cualitativa)\n")
    for r in results:
        lines.append(f"### [{r['category']}] {r['query']}\n")
        lines.append(f"**Qwen 7B** ({r['qwen'].get('latency_s')}s, {r['qwen'].get('tokens_out')} tok):\n")
        lines.append(f"> {r['qwen'].get('content', r['qwen'].get('error', '?'))[:1500]}\n")
        lines.append(f"**Nemotron 120B** ({r['nim'].get('latency_s')}s, {r['nim'].get('tokens_out')} tok):\n")
        lines.append(f"> {r['nim'].get('content', r['nim'].get('error', '?'))[:1500]}\n")
        lines.append("---\n")

    md_path.write_text("\n".join(lines))

    print(f"\n✅ Resultados:")
    print(f"   JSON: {json_path}")
    print(f"   MD:   {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
