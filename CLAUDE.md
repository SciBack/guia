# CLAUDE.md — SciBack/guia

Repo del **app GUIA** (Gateway Universitario de Informacion y Asistencia).

> **Toda la documentacion, contexto, roadmap y decisiones tecnicas del ecosistema** estan en
> `SciBack/sciback-core-docs` → `~/proyectos/sciback/sciback-core-docs/CLAUDE.md`

## Políticas de git

- **Solo `main`:** todo va directo a main. No se crean ramas de feature ni PRs — el historial de git lineal reemplaza el flujo de ramas. Esto evita ramas obsoletas que causen confusión.
- **Documentos:** solo se conserva la versión más reciente de cada doc en `main`. El historial de git reemplaza el archivo.
- **`gh-pages`** es excepción: rama de despliegue automático, no se toca manualmente.

## Este repo

- **Sprints 0.0–0.3 ✅ completos** (Setup → Harvester DSpace → Embeddings + RAG → Chainlit + OAuth Keycloak)
- **Sprints 0.4–0.7 ✅** (GROBID full-text, cl.Step CoT, cl.Pdf, scheduler, dashboard KPIs, backup S3, Telegram @GUIA_UPeU_bot)
- **AgentOrchestrator (ADR-050)** en canary 5% web+API desde 2026-05-30 (NIM Mistral, flag `GUIA_AGENT_MODE_ENABLED`, guarda `GUIA_AGENT_TIMEOUT_S`=25s → fallback legacy). Ver `docs/architecture/ADR-050-agent-orchestrator.md`.
- Servicios en `src/guia/services/`: `harvester`, `chat`, `search`, `router`, `intent`, `profile`, `cache`, `history`, `agent_orchestrator`, `query_rewriter`, `_bucket`. Render del chat: `channels/render.py` (listado enlazado vs narrativa, `ChatResponse.answer_type`).
- Despliegue piloto UPeU: VM 192.168.15.167, Koha (~34,985) + OJS (~744) indexados (DSpace bloqueado por 403, ver memoria).
  - **Deploy = `git pull` + `docker compose up -d --force-recreate --no-build`** (código montado en `/src`). NO rebuild en la VM (disco insuficiente, ver memoria). El compose tiene `tmpfs` en `/app/.files` (fix permisos uid 1000).

## Dependencias clave (`pyproject.toml`)

```toml
# Plataforma SciBack (path deps — no están en PyPI aún)
"sciback-core>=0.12",
"sciback-adapter-dspace>=0.1",
"sciback-adapter-ojs>=0.1",
"sciback-adapter-alicia>=0.1",
"sciback-adapter-koha>=0.1",
"sciback-llm-claude>=0.1",
"sciback-llm-ollama>=0.1",
"sciback-embeddings-e5>=0.1",
"sciback-embeddings-fastembed>=0.1",
"sciback-vectorstore-pgvector>=0.1",
# M2 (ADR-029 / ADR-033 / ADR-034)
"sciback-search-opensearch>=0.1",
"sciback-storage-s3>=0.1",
"sciback-identity-keycloak>=0.1",
"sciback-identity-midpoint>=0.1",
```
