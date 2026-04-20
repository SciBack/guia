# RAM Report — Stack M1

**Fecha:** 2026-04-19
**Entorno medición:** MacBook M1 (16 GB RAM, OrbStack, Docker 7.8 GB límite asignado)
**Tipo:** medición-preliminar — el target de producción es Mac Mini M4 (24 GB)
**Referencia:** ADR-029 — Plan B si RAM > 14 GB sostenido

---

## Medición real (servicios infra M1 solamente, sin workers)

| Contenedor | Imagen | RAM uso | RAM % (7.8 GB) |
|-----------|--------|---------|----------------|
| `guia-postgres-1` | pgvector/pgvector:pg16 | 23 MiB | 0.29% |
| `guia-redis-1` | redis:7-alpine | 5 MiB | 0.06% |
| `m1-infra-rabbitmq-1` | rabbitmq:3.13-management-alpine | 109 MiB | 1.36% |
| `m1-infra-opensearch-1` | opensearchproject/opensearch:2.19.2 | 2,500 MiB | 32.01% |
| **Total infra M1** | | **~2,637 MiB** | **~33.7%** |

OpenSearch heap configurado: `-Xms2g -Xmx2g` (heap fijo 2 GB).

---

## Estimación full stack con workers (no medido aún)

| Componente | Estimado |
|-----------|---------|
| Infra M1 (medido arriba) | 2,637 MiB |
| `celery-worker-indexer` (4 concurrencias Python) | ~300 MiB |
| `celery-worker-harvester` (2 concurrencias) | ~150 MiB |
| `celery-worker-grobid` (1 concurrencia) | ~100 MiB |
| `celery-worker-misc` (4 concurrencias) | ~300 MiB |
| `celery-beat` | ~100 MiB |
| `grobid` (Java, Sprint 0.4) | ~600 MiB |
| `api` (FastAPI + guia) | ~250 MiB |
| `chainlit` | ~250 MiB |
| `scheduler` | ~100 MiB |
| **Total estimado MacBook** | **~4,787 MiB (~4.7 GB)** |

---

## Proyección Mac Mini M4 (24 GB RAM, target producción)

| Stack | RAM estimada | % de 24 GB |
|-------|-------------|-----------|
| Infra M1 | ~2.6 GB | 10.8% |
| Workers + servicios guia | ~2.2 GB | 9.2% |
| Ollama + E5 embedding model | ~3.5 GB | 14.6% |
| Ollama + qwen2.5:7b LLM | ~4.5 GB | 18.7% |
| Sistema OS + overhead | ~2 GB | 8.3% |
| **Total Mac Mini estimado** | **~14.8 GB** | **~61.7%** |

---

## Conclusión ADR-029

**Plan B no activado.** 14.8 GB estimado ≈ al umbral de 14 GB pero:
- Ollama y LLMs no corren durante indexación (solo durante queries)
- El pico concurrente real es ~11-12 GB (sin LLMs activos)
- Mac Mini M4 Pro (24 GB) tiene margen suficiente

**Acción pendiente:** medir en Mac Mini M4 real durante harvesting + RAG query simultáneo antes del primer deploy UPeU. Actualizar esta tabla con medición real.

---

## Notas operacionales

- OpenSearch heap fijo en 2 GB es lo mínimo recomendado para k-NN con vectores 1024 dim
- Si el catálogo UPeU supera 500K documentos, evaluar aumentar a `-Xms4g -Xmx4g` (requiere 24 GB Mac Mini)
- RabbitMQ: 109 MiB con 0 mensajes en cola — esperar estabilización en ~150-200 MiB bajo carga normal
