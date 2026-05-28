"""Sonda rápida de latencia y soporte español sobre 5 modelos NIM candidatos.

Lanza UNA query académica representativa a cada modelo y mide latencia + calidad.
Filtra los que tardan >15s o no responden bien en español.
"""
from __future__ import annotations
import asyncio
import os
import time
import httpx

NIM_URL = os.environ["NVIDIA_NIM_BASE_URL"]
NIM_KEY = os.environ["NVIDIA_NIM_API_KEY"]

CANDIDATES = [
    "google/gemma-4-31b-it",
    "mistralai/mistral-small-4-119b-2603",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nemotron-3-nano-30b-a3b",
    "meta/llama-3.3-70b-instruct",
]

QUERY = "¿Qué normas peruanas regulan la ética en investigación con seres humanos? Responde en español, conciso, citando leyes específicas."
SYSTEM = "Eres GUIA, asistente académico UPeU. Responde en español, conciso (<200 palabras), citas leyes peruanas si aplica."


async def probe(client: httpx.AsyncClient, model: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{NIM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {NIM_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": QUERY},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            },
            timeout=120.0,
        )
        lat = time.perf_counter() - t0
        if r.status_code != 200:
            return {"model": model, "ok": False, "latency_s": round(lat, 1), "error": f"{r.status_code}: {r.text[:150]}"}
        d = r.json()
        msg = d["choices"][0]["message"]["content"]
        u = d.get("usage", {})
        return {
            "model": model,
            "ok": True,
            "latency_s": round(lat, 1),
            "tokens_out": u.get("completion_tokens"),
            "content": msg,
        }
    except Exception as e:
        return {"model": model, "ok": False, "latency_s": round(time.perf_counter() - t0, 1), "error": str(e)[:150]}


async def main():
    print(f"Sondeando {len(CANDIDATES)} modelos en paralelo...\n")
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[probe(client, m) for m in CANDIDATES])

    # Sort by latency (only OK ones)
    oks = sorted([r for r in results if r["ok"]], key=lambda x: x["latency_s"])
    errs = [r for r in results if not r["ok"]]

    print("=" * 80)
    print(f"{'Modelo':<50} {'Latencia':>10} {'Tokens':>8}")
    print("=" * 80)
    for r in oks:
        print(f"{r['model']:<50} {r['latency_s']:>9.1f}s {r['tokens_out']:>8}")
    for r in errs:
        print(f"{r['model']:<50} {'ERROR':>10} {r['error'][:80]}")
    print()

    for r in oks:
        print(f"\n--- {r['model']} ({r['latency_s']}s) ---")
        print(r["content"][:800])
        print()


if __name__ == "__main__":
    asyncio.run(main())
