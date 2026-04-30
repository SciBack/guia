# CLAUDE.md — SciBack/guia

Repo del **app GUIA** (Gateway Universitario de Informacion y Asistencia).

> **Toda la documentacion, contexto, roadmap y decisiones tecnicas del ecosistema** estan en
> `SciBack/sciback-core-docs` → `~/proyectos/sciback/sciback-core-docs/CLAUDE.md`

## Políticas de git

- **Ramas:** solo `main` es permanente. Las ramas de trabajo se fusionan a `main` una vez verificadas y se eliminan inmediatamente.
- **Documentos:** solo se conserva la versión más reciente de cada doc en `main`. El historial de git reemplaza el archivo.
- **`gh-pages`** es excepción: rama de despliegue automático, no se toca manualmente.

## Este repo

- Sprint 0.0 pendiente: inicializar con uv, FastAPI, Docker Compose
- El codigo del app va aqui (guia-node, guia-campus en Fase 1)
- Depende de `SciBack/sciback-core` (12 paquetes Python ya listos)

## Dependencias clave

```toml
"sciback-core>=0.11",
"sciback-adapter-dspace>=0.1",
"sciback-adapter-ojs>=0.1",
"sciback-adapter-alicia>=0.1",
"sciback-llm-claude>=0.1",
"sciback-llm-ollama>=0.1",
"sciback-embeddings-e5>=0.1",
"sciback-vectorstore-pgvector>=0.1",
```
