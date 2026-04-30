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
- **Sprint 0.4 en curso** (mayo 2026): GROBID full-text, cl.Step CoT, cl.Pdf, scheduler semanal
- Servicios operativos en `src/guia/services/`: `harvester`, `chat`, `search`, `router`, `intent`, `profile`, `cache`, `history`
- Despliegue piloto UPeU: VM 192.168.15.167 con Koha + OJS indexados (DSpace bloqueado por 403, ver memoria)

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
