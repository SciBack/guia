# CLAUDE.md — Proyecto GUIA

## Que es este proyecto

**GUIA** (Gateway Universitario de Informacion y Asistencia) es una plataforma open-source AI-native que unifica el acceso a toda la informacion universitaria en un solo punto conversacional. En vez de que estudiantes, docentes y administrativos naveguen 10 plataformas distintas, GUIA conecta todos los sistemas institucionales y responde via chat (web, Telegram, WhatsApp, Teams).

**Nombre:** GUIA = Gateway Universitario de Informacion y Asistencia. Termina en IA intencionalmente.
**Modelo:** Open-core. Core gratuito (Apache 2.0), conectores Campus + hosting gestionado + implementacion = pago.
**Empresa:** SciBack (Alberto Sanchez, fundador).
**Piloto:** Universidad Peruana Union (UPeU), Lima, Peru.
**Sitio web:** https://guia.sciback.com (GitHub Pages con custom domain)

### Repositorios GitHub

| Repo | Visibilidad | Contenido |
|------|------------|-----------|
| **SciBack/guia** | PUBLIC | Docs + landing + sitio web del producto (MkDocs) |
| **SciBack/guia-node** | PUBLIC (Apache 2.0) | Core open source: harvester, RAG, FastAPI, chat, Telegram |
| **SciBack/guia-campus** | PRIVATE | Conectores comerciales: Koha, SIS, ERP, midPoint, WhatsApp, Hub |
| **UPeU-Infra/guia-upeu** | PRIVATE | Config deploy UPeU: .env, overrides, scripts operacionales |
| **SciBack/platform** | PRIVATE | sciback-core + todos los adapters (base de GUIA) |

---

## Fundacion: sciback-platform

**GUIA no construye sus propios clientes HTTP ni harvesters.** Todo eso ya existe en `SciBack/platform`.

`SciBack/platform` es un monorepo uv con 12 paquetes listos (834 tests, ruff limpio):

| Paquete | Que provee a GUIA |
|---------|------------------|
| `sciback-core` v0.11.0 | Domain CERIF, ports hexagonales (LLMPort, VectorStorePort, EventBusPort, JobQueuePort) |
| `sciback-adapter-dspace` | DSpace 7.x REST API + OAI-PMH harvesting, mapeo DC→Publication |
| `sciback-adapter-ojs` | OJS REST API v3 + OAI-PMH, soporte titulo multilang |
| `sciback-adapter-alicia` | CONCYTEC OAI-PMH + validacion ALICIA 2.1.0 + vocabulario DRIVER/COAR |
| `sciback-adapter-orcid` | ORCID Public API v3.0, checksum ISO 7064 MOD 11-2 |
| `sciback-adapter-crossref` | Crossref REST polite pool |
| `sciback-adapter-openalex` | OpenAlex API |
| `sciback-adapter-ror` | Research Organization Registry |
| `sciback-llm-claude` | Anthropic Claude API → LLMPort |
| `sciback-llm-ollama` | Ollama HTTP API → LLMPort (Mac Mini M4) |
| `sciback-embeddings-e5` | multilingual-e5-large-instruct via Ollama con prefijos passage/query |
| `sciback-vectorstore-pgvector` | SQLAlchemy + pgvector, cosine similarity, IVFFlat index |

**GUIA consume estos paquetes como dependencias.** No reimplementa ningun cliente HTTP, harvester, ni conector de base de datos vectorial.

---

## Productos

### GUIA Node (por universidad)

Asistente AI institucional que conecta todos los sistemas de una universidad y expone un chat unificado.

**Capa 1 — GUIA Research (core, open source):**
- Cosecha DSpace/OJS via `sciback-adapter-dspace` y `sciback-adapter-ojs`
- Valida y normaliza ALICIA 2.1.0 via `sciback-adapter-alicia`
- Embeddings multilingues via `sciback-embeddings-e5`
- Almacenamiento vectorial via `sciback-vectorstore-pgvector`
- RAG sobre produccion cientifica institucional con LlamaIndex
- LLM via `sciback-llm-claude` (modo HYBRID) o `sciback-llm-ollama` (modo LOCAL)

**Capa 2 — GUIA Campus (conectores modulares, pago):**
- Koha → prestamos, deudas de biblioteca
- SIS (sistema academico) → matricula, notas, horarios
- ERP (finanzas) → estado de cuenta, pagos pendientes
- AD/LDAP → usuario de correo, credenciales
- Moodle → tareas, cursos, calificaciones
- Indico → eventos, congresos

**Canales de chat:**
- Chat web (Chainlit, embebible) — Fase 0
- Telegram bot — Fase 0
- WhatsApp Business API — cuando haya presupuesto
- Microsoft Teams — canal institucional

**API y extensibilidad:**
- API REST para integraciones custom
- MCP server para agentes AI externos (Claude, GPT, etc.)

### GUIA Hub (por consorcio/red/pais)

Federador que agrega nodos GUIA de multiples universidades.

- Federation broker: resuelve queries que nodos locales no pueden
- OAI-PMH endpoint compatible con redes nacionales (ALICIA, BDTD, La Referencia)
- Solo datos publicos (investigacion) — nunca datos campus privados

---

## Modelo comercial SciBack

El codigo open source es el gancho de adopcion. El revenue viene del hosting, la implementacion y los conectores comerciales (modelo Red Hat / WordPress.com / DSpaceDirect).

### Tres planes comerciales

| Plan | Incluye | Precio mensual |
|------|---------|---------------|
| **GUIA Research** (Community) | Core: DSpace + OJS + RAG + chat web + Telegram | Gratis (Apache 2.0) |
| **GUIA Research** (Managed) | SciBack hospeda + soporte | ~$150-300 |
| **GUIA Campus** | Research + Koha + SIS + ERP + Moodle + Keycloak SSO | ~$400-700 |
| **GUIA Connect** | Campus + Helpdesk + Teams + CRM + MCP Server | ~$800-1500 |
| **Implementacion** | Integracion inicial (one-time) | $1K-6K |
| **Hub** | Federacion de nodos (SaaS, add-on) | ~$200-500 |

### Barrera de pago (que NO esta en Community)
1. Conectores Campus — Koha, SIS, ERP, Moodle (codigo privado)
2. Conectores Connect — Helpdesk, Calendarios, Teams, CRM, Webhooks
3. MCP Server — expone GUIA para Claude, GPT, Copilot
4. Identidad compleja — midPoint + Keycloak con AD/Entra/LDAP
5. Operaciones — hosting, backups, SSL, monitoring 24/7
6. Hub — federacion, OAI-PMH server, valor de red

### Competencia y posicionamiento

**Competidor principal: OpenAlex + Perplexity**
GUIA no compite en contenido publico. Compite en el **estrato institucional privado**:
- Tesis no indexadas, datos de campus, cumplimiento ALICIA/RENATI, y ACCION (no solo consulta)
- GUIA Research: "La capa que Perplexity no puede ver" ($1.8K-3.6K/ano vs $20K-50K de EDS)
- GUIA Campus: "El asistente que conoce toda tu vida universitaria" (sin competidor directo en LATAM)

---

## Estado actual (abril 2026)

### Completado
- Nombre oficial definido: GUIA
- Arquitectura tecnica definida (Node + Hub, dos capas)
- Modelo comercial open-core con 3 planes (Research, Campus, Connect)
- `SciBack/platform` con 12 paquetes listos (sciback-core + adapters) — 834 tests
- Documentacion open source del repo auditada y completa (LICENSE, CONTRIBUTING, etc.)

### Pendiente inmediato (pre-Sprint 0.0)
- [ ] Confirmar URL OAI-PMH de DSpace UPeU: `curl https://repositorio.upeu.edu.pe/oai?verb=Identify`
- [ ] Confirmar URLs OAI-PMH de revistas OJS UPeU
- [ ] Decidir: EC2 existente (AWS-DSpace 18.188.164.130) o EC2 nuevo para GUIA
- [ ] API key Claude disponible en `~/.secrets/anthropic.env`
- [ ] Dominio guia.sciback.com → EC2 GUIA
- [ ] Crear repos `SciBack/guia-node` y `SciBack/guia-campus`

---

## Fases

| Fase | Periodo | Objetivo | Conectores |
|------|---------|----------|-----------|
| 0 | 2026 abr-sep | Node piloto UPeU: DSpace + OJS + RAG + chat | sciback-adapter-dspace + sciback-adapter-ojs |
| 1 | 2026 oct-dic | Node empaquetado, 2-3 universidades, primer revenue | + Koha (Campus Basic) |
| 2 | 2027 H1 | Hub federado, OAI-PMH hacia redes nacionales | + SIS + ERP (Campus Pro) |
| 3 | 2028+ | Hub escalado, 50+ universidades, MCP publico | + Moodle + WhatsApp |

---

## Financiamiento

| Fuente | Tipo | Aplicabilidad |
|--------|------|---------------|
| Revenue SciBack | Suscripciones Campus/Hub | Principal a mediano plazo |
| **NLnet NGI Zero Commons Fund** | **Grant open source hasta €50,000** | **PRIORITARIO — deadline 1 junio 2026** |
| IOI Fund | Grant infra open science | Para el Hub federado |
| Mellon Foundation | Grant educacion superior | Para el core open source |
| SCOSS | Sostenibilidad recurrente | Fase 3+ |
| Fondos gubernamentales | CONCYTEC, CAPES, etc. | Por pais |

### NLnet NGI Zero Commons Fund

**URL:** https://nlnet.nl/commonsfund/
**Deadline:** 1 junio 2026 — **ACCION INMEDIATA**
**Monto:** hasta €50,000 (no reembolsable, sin equity, sin empresa constituida)

**Entregables open source que califican:**
1. `sciback-adapter-dspace` + `sciback-adapter-ojs` — harvesters OAI-PMH tipo-safe (ya construidos en platform)
2. Validador ALICIA/RENATI en Python — `sciback-adapter-alicia` (ya construido)
3. Servidor OAI-PMH en FastAPI — para el Hub (por construir)
4. `guia-node` core RAG — infraestructura publica para acceso abierto en universidades LATAM

**Framing:** postular las **piezas open source que le faltan al ecosistema global**, no el producto comercial. El modelo open-core no es problema para NLnet.

---

## Modelo de despliegue: Hibrido

| Componente | Modelo | Razon |
|-----------|--------|-------|
| **GUIA Node** | Self-hosted o SciBack-managed | Datos sensibles (notas, deudas) — quedan en infra de la universidad |
| **GUIA Hub** | SaaS (gestionado por SciBack) | Solo datos publicos de investigacion |
| **Keycloak** | Co-desplegado con el Node | 1 realm por universidad |
| **midPoint** | Opcional, co-desplegado | Solo para universidades con infra compleja (Tier Pro+) |

### Variantes de deploy

| Variante | Para quien | Infra |
|----------|-----------|-------|
| Self-hosted | DTI capaz + AWS/on-premise propio | Docker Compose en su EC2 |
| SciBack-managed | Universidades sin infra propia | AWS dedicado por cliente |
| Community | Desarrolladores, pruebas | `docker compose up` local |

---

## Decisiones tecnicas (abril 2026)

### Stack definitivo del Node

| Componente | Tecnologia | Rol | Fuente |
|-----------|-----------|-----|--------|
| Dominio + puertos | `sciback-core` v0.11.0 | Contratos hexagonales (LLMPort, VectorStorePort, EventBusPort) | SciBack/platform |
| Harvesting DSpace | `sciback-adapter-dspace` | OAI-PMH + REST API + mapper DC→Publication | SciBack/platform |
| Harvesting OJS | `sciback-adapter-ojs` | OAI-PMH + REST API v3 | SciBack/platform |
| Validacion ALICIA | `sciback-adapter-alicia` | CONCYTEC OAI-PMH, DRIVER/COAR | SciBack/platform |
| LLM modo CLOUD | `sciback-llm-claude` | Claude API → LLMPort | SciBack/platform |
| LLM modo LOCAL | `sciback-llm-ollama` | Ollama HTTP API → LLMPort | SciBack/platform |
| Embeddings | `sciback-embeddings-e5` | multilingual-e5-large via Ollama | SciBack/platform |
| Vector store | `sciback-vectorstore-pgvector` | pgvector + IVFFlat + cosine similarity | SciBack/platform |
| RAG engine | LlamaIndex (FunctionAgent + VectorStoreIndex) | Orquestacion RAG | PyPI |
| API | FastAPI + uvicorn | REST + WebSocket | PyPI |
| Chat web (F0) | Chainlit | Auth OIDC + streaming nativo LlamaIndex | PyPI |
| Chat web (F1+) | React widget | Branding por universidad | Custom |
| Telegram | aiogram v3 | 100% async, FSM | PyPI |
| WhatsApp (F1+) | pywa | Cloud API oficial Meta | PyPI |
| Dashboard | Streamlit (F0) → Metabase (F1+) | Visualizacion produccion cientifica | PyPI / AGPL |
| SSO/Auth | Keycloak + authlib + PyJWT | OIDC multi-tenant | Apache 2.0 |
| IGA (F1+) | midPoint | Usuario canonico multi-fuente | EUPL |
| Cache semantico | Redis | 40-60% hit rate esperado | PyPI |
| PDF academicos | GROBID + grobid-client | Gold standard papers (Fase 1) | Apache 2.0 |
| PDF genericos | Docling (IBM) | Estructura semantica, tablas (Fase 1) | MIT |
| Dep. management | uv | Workspace monorepo | MIT |
| Deploy | Docker Compose | Un solo `docker compose up` | — |

### pyproject.toml de guia-node (dependencias)

```toml
[project]
name = "guia-node"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    # Plataforma SciBack (todos del workspace SciBack/platform)
    "sciback-core>=0.11",
    "sciback-adapter-dspace>=0.1",
    "sciback-adapter-ojs>=0.1",
    "sciback-adapter-alicia>=0.1",
    "sciback-llm-claude>=0.1",
    "sciback-llm-ollama>=0.1",
    "sciback-embeddings-e5>=0.1",
    "sciback-vectorstore-pgvector>=0.1",
    # RAG + API
    "llama-index>=0.12",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "chainlit>=2.0",
    # Canales
    "aiogram>=3.15",
    # Cache + auth
    "redis>=5.0",
    "authlib>=1.3",
    "pyjwt>=2.9",
    # Config
    "pydantic-settings>=2.5",
]
```

### Selector de modo LLM

GUIA opera en 3 modos configurables via variable de entorno `GUIA_LLM_MODE`:

| Modo | LLM | Embeddings | Cuando usar |
|------|-----|-----------|-------------|
| `LOCAL` | `sciback-llm-ollama` (Qwen 2.5 7B) | `sciback-embeddings-e5` | Datos sensibles, queries campus |
| `HYBRID` | Ollama para clasificacion, Claude para sintesis | `sciback-embeddings-e5` | Default para Research |
| `CLOUD` | `sciback-llm-claude` | `sciback-embeddings-e5` | Alta calidad, demo inicial |

### Arquitectura hexagonal de guia-node

```
┌─────────────────────────────────────────────────────────┐
│                  Canales de entrada                      │
│         (FastAPI, Chainlit, aiogram, pywa)              │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│              GUIA Application Layer                      │
│   ChatService / HarvesterService / SearchService        │
│   (orquesta puertos — NO importa adapters directamente) │
└──────┬──────────────┬──────────────┬────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼────────────────────┐
│  LLMPort    │ │VectorStore │ │  DSpacePort / OJSPort   │
│  (sciback-  │ │  Port      │ │  (sciback-adapter-*)    │
│  llm-*)     │ │ (pgvector) │ │                         │
└─────────────┘ └────────────┘ └─────────────────────────┘
       │              │              │
       └──────────────┼──────────────┘
                      │
              sciback-core (dominio CERIF, contratos)
```

**Regla:** `guia-node` importa interfaces de `sciback_core.ports`, no implementaciones de adapters. Los adapters se inyectan via config/DI.

### Lo que GUIA SÍ construye desde cero (no en platform)

1. **`HarvesterService`** — orquesta `DSpaceAdapter` + `AliciaHarvester` + `OjsAdapter` → embeds → pgvector
2. **`ChatService`** — intent classification + LlamaIndex FunctionAgent + selector de modo LLM
3. **`OaiPmhServer`** — endpoint FastAPI OAI-PMH del Hub (exponer, no consumir) — ~500 lineas
4. **Conectores Campus** — Koha, SIS, ERP (codigo privado guia-campus)
5. **UI y canales** — Chainlit, aiogram, pywa

### Framework de agentes

| Fase | Capacidad | Herramienta |
|------|-----------|-------------|
| 0 | RAG simple (busqueda semantica) | LlamaIndex VectorStoreIndex + sciback-vectorstore-pgvector |
| 0.5 | FunctionAgent con tools (DSpace + Koha + SIS en 1 query) | LlamaIndex FunctionAgent |
| 1 | MCP server del Hub (datos publicos) | FastMCP / fastapi-mcp |
| 2+ | Multi-agente con handoff | LlamaIndex AgentWorkflow |

No usar en Fase 0: LangGraph, CrewAI, AutoGen (complejidad innecesaria para 1 desarrollador).

### Arquitectura de identidad

| Fase | Componente | Rol |
|------|-----------|-----|
| 0 | Keycloak solo | SSO via OIDC |
| 0 (UPeU) | midPoint + Keycloak | Ya operativo: LAMB → midPoint → Koha + EntraID → Keycloak |
| 1+ | midPoint + Keycloak | Usuario canonico multi-fuente, lifecycle |

**Estado IGA UPeU (pre-produccion abril 2026):**
- midPoint 4.9.5 UP en 192.168.15.230:8080
- LAMB Academic (PostgreSQL SIS/ERP) via JDBC
- Koha via `connector-koha` v1.1.0 (UPeU-Infra/connector-koha)
- Azure EntraID conectado — tenant sciback.com
- Keycloak 26.6.0 federado con EntraID
- 10 usuarios ficticios sci-* probados end-to-end (3 shadows: LAMB + Koha + Azure)

### Estandares y schemas de metadatos

| Estandar | Soportado | Fase | Quien lo maneja |
|---------|-----------|------|-----------------|
| Dublin Core (Qualified) | SI | 0 | `sciback-adapter-dspace` / `sciback-adapter-ojs` |
| COAR Vocabularies (URIs) | SI | 0 | `sciback-adapter-alicia` (DRIVER→COAR) |
| ALICIA 2.1.0 / CONCYTEC | SI | 0 | `sciback-adapter-alicia` |
| RENATI / SUNEDU | SI | 0 | `sciback-adapter-dspace` (campos `renati.*`) |
| OpenAIRE v3 | SI | 0 | Compatible via DSpace |
| CERIF | SI | 0+ | `sciback-core` domain model |
| DataCite | PARCIAL | 2 | `sciback-core` `to_datacite_xml()` |

**3 decisiones de diseno criticas (no cambian):**
1. URIs COAR en el modelo interno, nunca strings
2. Consumir `metadataPrefix=dim` ademas de `oai_dc` (para `renati.*` y `thesis.*`)
3. El abstract es el campo mas importante para RAG (Fase 0 sin GROBID)

### Mac Mini M4 — Servidor IA dedicado

**Rol:** inferencia compartida para toda la plataforma SciBack (incluye GUIA).

- Ollama runtime con backend MLX (ARM64)
- Modelos: Qwen 2.5 3B, Qwen 2.5 7B, DeepSeek R1 Distill, multilingual-e5-large-instruct
- Reverse proxy Caddy con autenticacion por API key
- API HTTP en `ia.guia.upeu.edu.pe`

`sciback-llm-ollama` y `sciback-embeddings-e5` ya saben como hablar con este servidor (variable de entorno `OLLAMA_BASE_URL`).

### Que NO se usa y por que

| Descartado | Razon |
|-----------|-------|
| oaipmh-scythe / sickle | Ya incluido en sciback-adapter-dspace y sciback-adapter-ojs |
| Llamadas directas a Anthropic SDK | Usar sciback-llm-claude (abstraccion sobre LLMPort) |
| SQLAlchemy raw para pgvector | Usar sciback-vectorstore-pgvector |
| Onyx (ex Danswer) | Competidor directo, 20 contenedores, 8GB+ RAM |
| RAGFlow | Stack pesado (Go + Elasticsearch) |
| AnythingLLM | Node.js, orientado a uso personal |
| LangChain | LlamaIndex mas eficiente para RAG puro |
| Zitadel | AGPL desde 2025, incompatible con SaaS |

---

## Estructura de archivos

### Este repo (SciBack/guia) — Docs + sitio web

```
~/proyectos/sciback/guia/
├── CLAUDE.md                  <- este archivo (fuente de verdad del proyecto)
├── landing.html               <- landing page del producto
├── mkdocs.yml                 <- config MkDocs Material bilingue ES/EN
├── requirements.txt
├── docs/
│   ├── index.md               <- que es GUIA, para quien
│   ├── arquitectura.md        <- diagramas Mermaid (Node, Hub, identidad, agentes)
│   ├── estandares.md          <- schemas, ALICIA 2.1.0, COAR, CERIF, modelo canonico
│   ├── modelo-comercial.md    <- tiers, pricing, revenue, comparacion
│   ├── conectores.md          <- interface GUIAConnector + conectores disponibles
│   ├── roadmap.md             <- plan operativo con sprints semanales
│   └── en/
│       └── index.md           <- version en ingles
└── .github/workflows/
    └── deploy.yml             <- build MkDocs -> landing -> deploy
```

### SciBack/guia-node — Core open source (por crear en Sprint 0.0)

```
guia-node/
├── pyproject.toml             <- uv project, depende de sciback-platform packages
├── uv.lock
├── docker-compose.yml
├── .env.example
├── src/
│   └── guia/
│       ├── api/               <- FastAPI app (endpoints REST + WebSocket)
│       ├── services/
│       │   ├── harvester.py   <- HarvesterService (orquesta adapters de platform)
│       │   ├── search.py      <- SearchService (LlamaIndex + VectorStorePort)
│       │   └── chat.py        <- ChatService (intent + FunctionAgent + LLMPort)
│       ├── channels/
│       │   ├── web.py         <- Chainlit
│       │   └── telegram.py    <- aiogram v3
│       └── config.py          <- GUIASettings (pydantic-settings)
├── docker/
│   ├── Dockerfile
│   └── postgres/init.sql      <- habilitar pgvector
└── tests/
```

### SciBack/guia-campus — Conectores comerciales (por crear en Fase 1)

```
guia-campus/
├── connectors/
│   ├── koha.py                <- SIP2 / REST API Koha
│   ├── sis.py                 <- Sistema academico (custom por universidad)
│   ├── erp.py                 <- Finanzas
│   ├── moodle.py              <- LMS
│   └── identity/
│       ├── keycloak.py        <- KeycloakDirectConnector (Fase 0)
│       └── midpoint.py        <- MidPointConnector (Fase 1+)
├── hub/                       <- Federation broker
├── whatsapp/                  <- pywa integration
└── pyproject.toml
```

---

## Variables de entorno (.env.example)

```env
# Modo LLM: LOCAL | HYBRID | CLOUD
GUIA_LLM_MODE=HYBRID

# Fuentes de datos
DSPACE_BASE_URL=https://repositorio.upeu.edu.pe
DSPACE_OAI_PMH_URL=https://repositorio.upeu.edu.pe/oai
OJS_BASE_URL=https://revistas.upeu.edu.pe

# LLM (sciback-llm-claude)
ANTHROPIC_API_KEY=sk-ant-...

# LLM local (sciback-llm-ollama + sciback-embeddings-e5)
OLLAMA_BASE_URL=http://ia.guia.upeu.edu.pe
OLLAMA_API_KEY=...
OLLAMA_DEFAULT_MODEL=qwen2.5:7b
E5_MODEL=multilingual-e5-large-instruct

# Vector store (sciback-vectorstore-pgvector)
PGVECTOR_DATABASE_URL=postgresql://guia:password@postgres:5432/guia_db

# Auth
KEYCLOAK_URL=https://keycloak.guia.sciback.com
KEYCLOAK_REALM=upeu
KEYCLOAK_CLIENT_ID=guia-node
KEYCLOAK_CLIENT_SECRET=...

# Telegram
TELEGRAM_BOT_TOKEN=...

# Redis (cache semantico)
REDIS_URL=redis://redis:6379

# Deploy
GUIA_BASE_URL=https://guia.upeu.edu.pe
ENVIRONMENT=production
```

---

## Notas tecnicas

### Deploy workflow del sitio
`mkdocs build --strict` → `cp landing.html site/index.html` → `peaceiris/actions-gh-pages`.
El `cp` sobreescribe el index.html generado por MkDocs con la landing del producto.

### Regulacion por pais
- Peru: Ley 30035 (repositorios interoperables obligatorios)
- Colombia: Resolucion 0777/2022
- Brasil: CAPES OA

Conectarse a GUIA permite cumplir la normativa **y** tener asistente AI unificado en un solo movimiento.
