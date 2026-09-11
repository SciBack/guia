"""Compara pesos de fusión sobre el banco. Mide las dos etapas por separado.

Se miden las dos porque hacen cosas distintas y solo una es recuperable: si
el documento no entra en la ventana de candidatos, el reranker no puede
rescatarlo por bueno que sea. Por eso importa tanto la posición tras la
fusión como la final.

  MRR   media de 1/posición — premia estar arriba, no solo estar
  R@5   fracción de casos con el documento en los cinco primeros
"""
import asyncio, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from banco_de_consultas import BANCO

from guia.config import GUIASettings
from guia.container import GUIAContainer

c = GUIAContainer(GUIASettings())
sa = c.search_adapter

PESOS = [(0.3, 0.7), (0.4, 0.6), (0.5, 0.5), (0.6, 0.4), (0.7, 0.3)]

def ident(x):
    if isinstance(x, dict):
        return str(x.get("id") or (x.get("metadata") or {}).get("id") or "")
    return str(getattr(x, "id", ""))

def rr(pos):
    return 1.0 / pos if pos else 0.0

async def medir(pesos):
    filas = []
    for q, target, tipo in BANCO:
        v = c.embedder.embed_query(q)
        v = getattr(v, "embedding", v)
        fus = await sa._fused(q, v, pesos, None)
        ids_f = [ident(h) for h in fus.hits]
        pos_f = ids_f.index(target) + 1 if target in ids_f else None

        final = await sa.hybrid_dicts(q, v, weights=pesos, limit=10)
        ids_r = [ident(d) for d in final]
        pos_r = ids_r.index(target) + 1 if target in ids_r else None
        filas.append((tipo, pos_f, pos_r))
    return filas

def resumen(filas):
    def agg(sub, i):
        if not sub:
            return (0.0, 0.0)
        mrr = sum(rr(f[i]) for f in sub) / len(sub)
        r5 = sum(1 for f in sub if f[i] and f[i] <= 5) / len(sub)
        return (mrr, r5)
    return agg(filas, 1), agg(filas, 2), {
        t: agg([f for f in filas if f[0] == t], 2)
        for t in ("lexico", "semantico", "agregado")
    }

async def main():
    print(f"{'pesos':14} {'fusión MRR':>11} {'final MRR':>10} {'final R@5':>10}   por tipo (MRR final)")
    for pesos in PESOS:
        filas = await medir(pesos)
        (mrr_f, _), (mrr_r, r5_r), por_tipo = resumen(filas)
        detalle = "  ".join(f"{t[:3]}={por_tipo[t][0]:.2f}" for t in por_tipo)
        marca = "  ← actual" if pesos == (0.3, 0.7) else ""
        print(f"  bm25={pesos[0]} knn={pesos[1]}  {mrr_f:>10.3f} {mrr_r:>10.3f} {r5_r:>10.0%}   {detalle}{marca}")

asyncio.run(main())
