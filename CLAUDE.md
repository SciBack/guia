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
| **SciBack/guia-node** | PUBLIC (Apache 2.0) | Core open source: harvester, RAG, DSpace + OJS, chat, API |
| **SciBack/guia-campus** | PRIVATE | Conectores comerciales: Koha, SIS, ERP, midPoint, WhatsApp, Hub |
| **UPeU-Infra/guia-upeu** | PRIVATE | Config deploy UPeU: .env, overrides, scripts operacionales |

`UPeU-Infra/guia` → migrado a `SciBack/guia` (archivado con redirect).

---

## Productos

### GUIA Node (por universidad)

Asistente AI institucional que conecta todos los sistemas de una universidad y expone un chat unificado.

**Capa 1 — GUIA Research (core, open source):**
- Conecta a DSpace/OJS locales via OAI-PMH
- Procesa full-text -> chunks -> embeddings vectoriales (pgvector)
- RAG sobre produccion cientifica institucional
- "Que tesis hay sobre X?", "En que estado esta mi tesis?", "Mi articulo fue aceptado?"

**Capa 2 — GUIA Campus (conectores modulares, pago):**
- Koha -> prestamos, deudas de biblioteca
- SIS (sistema academico) -> matricula, notas, horarios
- ERP (finanzas) -> estado de cuenta, pagos pendientes
- AD/LDAP -> usuario de correo, credenciales
- Moodle -> tareas, cursos, calificaciones
- Indico -> eventos, congresos

**Canales de chat:**
- Chat web (widget embebible) — Fase 0
- Telegram bot — Fase 0 (gratis, sin costo de API)
- WhatsApp Business API — cuando haya presupuesto
- Microsoft Teams — canal institucional

**API y extensibilidad:**
- API REST para integraciones custom
- MCP server para agentes AI externos (Claude, GPT, etc.)

**Stack tecnico:**
- Python harvester + GROBID (full-text PDF) + pgvector + RAG engine + LLM
- Docker Compose (deploy estandar)

### GUIA Hub (por consorcio/red/pais)

Federador que agrega nodos GUIA de multiples universidades.

- Federation broker: resuelve queries que nodos locales no pueden
- Embeddings agregados de nodos miembro
- OAI-PMH endpoint para compatibilidad con redes nacionales (ALICIA, BDTD)
- Solo datos publicos (investigacion) — nunca datos campus privados

**Clientes potenciales del Hub:**
- Consorcios universitarios (ALTAMIRA, CINCEL, etc.)
- Redes denominacionales (IASD, catolicas, etc.)
- Sistemas universitarios estatales
- Redes tematicas (salud, teologia, ingenieria)

---

## Modelo comercial SciBack

**El codigo open source es el gancho de adopcion. El revenue viene del hosting, la implementacion y los conectores comerciales.** Modelo analogo a Red Hat / WordPress.com / DSpaceDirect.

### Fuentes de revenue

| Fuente | Que vendes | Por que pagan |
|--------|-----------|---------------|
| Hosting gestionado | SciBack despliega y mantiene el Node en AWS dedicado | La universidad no tiene DTI capaz de mantener Docker + pgvector + GROBID |
| Implementacion | SciBack conecta GUIA a los sistemas de la universidad | Cada universidad tiene sistemas distintos — la integracion es custom |
| Conectores Campus | Codigo privado (Koha, SIS, ERP, Moodle, midPoint) | No estan en el core open source |
| Soporte + SLA | Respuesta <4h, uptime garantizado, actualizaciones | Produccion necesita respaldo |
| Hub federado | SaaS central que agrega nodos | Valor de red — un Hub es mas util que N nodos aislados |

### Tiers de pricing

| Tier | Incluye | Precio | Revenue real |
|------|---------|--------|-------------|
| **Community** | Core open source (DSpace + OJS + RAG + chat web + Telegram) | Gratis (Apache 2.0) | Pipeline de clientes |
| **Managed Basic** | SciBack hospeda Node + DSpace + OJS + soporte email | ~$150-300/mes | Hosting + mantenimiento |
| **Managed Pro** | + Koha + SIS/ERP + Keycloak SSO + midPoint | ~$400-700/mes | Implementacion custom + conectores |
| **Managed Enterprise** | + WhatsApp + SLA 99.9% + analytics + soporte dedicado | ~$800-1500/mes | SLA + operaciones |
| **Implementacion** | Proyecto de integracion inicial (one-time) | ~$2K-5K | Consultoria + config por universidad |
| **Hub** | Federacion de nodos (SaaS) | ~$500-5000/mes | Valor de red |

### Barrera de pago (que NO esta en Community)
1. **Conectores Campus** — Koha, SIS, ERP, Moodle (codigo privado en guia-campus)
2. **Identidad compleja** — midPoint + Keycloak con AD/Entra/LDAP de cada universidad
3. **Operaciones** — hosting, backups, SSL, monitoring, actualizaciones 24/7
4. **WhatsApp** — requiere Cloud API Meta, config por universidad
5. **Hub** — federacion, OAI-PMH server, MCP server

**Posicionamiento:** Alternativa open-source a EBSCO EDS / Ex Libris Primo / Summon.
- EDS: $20K-50K/ano. GUIA Managed Pro: ~$5K-8K/ano.
- Chat conversacional + WhatsApp en vez de formularios de busqueda.

---

## Estado actual (abril 2026)

### Completado
- Nombre oficial definido: GUIA
- Arquitectura tecnica definida (Node + Hub, dos capas)
- Modelo comercial open-core definido
- Sitio web (pendiente actualizar con nueva identidad)

### Pendiente inmediato (pre-Sprint 0.0)
- [ ] Confirmar URL OAI-PMH de DSpace UPeU (probar con `curl`)
- [ ] Confirmar URLs OAI-PMH de revistas OJS UPeU
- [ ] Decidir: EC2 existente (AWS-DSpace) o EC2 nuevo para GUIA
- [ ] API key de Claude API disponible en `~/.secrets/anthropic.env`
- [ ] Dominio guia.sciback.com apuntando al EC2
- [ ] Crear repo `SciBack/guia-node` (privado por ahora)

---

## Fases

| Fase | Periodo | Objetivo | Conectores |
|------|---------|----------|-----------|
| 0 | 2026 abr-sep | Node piloto UPeU: DSpace + OJS + RAG + chat | DSpace + OJS (Research) |
| 1 | 2026 oct-dic | Node empaquetado, 2-3 universidades, primer revenue | + Koha (Campus Basic) |
| 2 | 2027 H1 | Hub federado, OAI-PMH hacia redes nacionales | + SIS + ERP (Campus Pro) |
| 3 | 2028+ | Hub escalado, 50+ universidades, MCP publico | + Moodle + WhatsApp |

**Fase 0 enfocada en DSpace + OJS** — es lo que el 90% de universidades LATAM ya tienen.
Koha y conectores Campus entran en Fase 1 cuando el core Research este solido.

Plan operativo detallado semana a semana en `docs/roadmap.md`.

---

## Financiamiento

GUIA es producto comercial de SciBack. El financiamiento puede venir de multiples fuentes:

| Fuente | Tipo | Aplicabilidad |
|--------|------|---------------|
| Revenue SciBack | Suscripciones Campus/Hub | Principal a mediano plazo |
| IOI Fund | Grant para infra open science | Para el Hub federado |
| Mellon Foundation | Grant educacion superior | Para el core open source |
| SCOSS | Sostenibilidad recurrente | Fase 3+ (50+ instituciones) |
| Fondos denominacionales | Grants especificos | Para verticales (IASD, catolicas, etc.) |
| Fondos gubernamentales | CONCYTEC, CAPES, etc. | Por pais, para universidades especificas |

---

## Modelo de despliegue: Hibrido (self-hosted + managed + SaaS)

No es 100% SaaS ni 100% on-premise. Cada capa tiene su modelo:

| Componente | Modelo | Razon |
|-----------|--------|-------|
| **GUIA Node** | **Self-hosted** o **SciBack-managed** | Datos sensibles (notas, deudas, expedientes) deben quedarse en infra de la universidad o en AWS dedicado. Necesita acceso a red interna (AD, SIS, ERP) |
| **GUIA Hub** | **SaaS** (gestionado por SciBack) | Solo datos publicos de investigacion. Un Hub central sirve a N universidades |
| **Keycloak** | **Co-desplegado con el Node** | Cada universidad tiene su realm. Va junto al Node |
| **midPoint** | **Opcional, co-desplegado** | Solo para universidades con infra compleja (Tier Pro+) |

### Variantes de deploy del Node

| Variante | Para quien | Infra |
|----------|-----------|-------|
| **Self-hosted** | Universidades con DTI capaz y AWS/on-premise propio | Docker Compose en su EC2 o servidor fisico |
| **SciBack-managed** | Universidades sin infra propia | SciBack despliega en AWS dedicado por cliente, con VPN o peering a la red interna de la universidad |
| **Community** | Desarrolladores, pruebas | `docker compose up` local, solo Capa 1 Research |

### Por que NO SaaS puro para el Node
- Los datos campus (notas, deudas, matricula) son sensibles y regulados
- El Node necesita acceso a AD/LDAP/SIS que estan en la red interna
- Universidades latinoamericanas no confian en "mis datos en la nube de un tercero"
- Latencia: el harvester debe estar cerca del DSpace/OJS local

### Por que SI SaaS para el Hub
- Solo agrega datos publicos de investigacion (ya estan en acceso abierto)
- Un Hub central es mas eficiente que N Hubs independientes
- SciBack controla la calidad y disponibilidad del servicio federado

---

## Decisiones tecnicas (abril 2026)

### Stack definitivo del Node

| Componente | Tecnologia | Licencia | Justificacion |
|-----------|-----------|----------|---------------|
| RAG engine | **LlamaIndex** (FunctionAgent + pgvector) | MIT | Mejor framework Python para RAG en produccion |
| OAI-PMH harvester | **oaipmh-scythe** (fork moderno de sickle) | BSD | v1.0.0 sept 2025, async, type hints |
| DSpace REST API | **dspace-rest-client** | BSD | v0.1.13, DSpace 7+ CRUD completo |
| PDF academicos | **GROBID** + grobid-client-python | Apache 2.0 | Gold standard para papers. F1 mas alto en benchmarks |
| PDF genericos | **Docling** (IBM) | MIT | Estructura semantica, tablas, nativo en LlamaIndex |
| Embeddings | **intfloat/multilingual-e5-large-instruct** | MIT | Top MTEB multilingue, excelente en espanol academico, local, gratis |
| Vector store | **pgvector** (extension PostgreSQL) | MIT | Sin infraestructura adicional — usa el mismo Postgres |
| API | **FastAPI** | MIT | ASGI async, OpenAPI nativo, 15K+ req/s |
| Chat web (Fase 0) | **Chainlit** | Apache 2.0 | Nativo LlamaIndex, auth OIDC, streaming |
| Chat web (Fase 1+) | **React** widget embebible | — | Cuando necesitemos UI custom con branding por universidad |
| Telegram bot | **aiogram** v3 | MIT | 100% async, FSM para conversaciones con estado |
| WhatsApp (Fase 1+) | **pywa** | MIT | Cloud API oficial Meta, FastAPI webhook nativo |
| Dashboard | **Streamlit + Plotly** (Fase 0) → **Metabase** (Fase 1+) | MIT / AGPL | Visualizacion de produccion cientifica |
| SSO/Auth | **Keycloak** + authlib + fastapi-keycloak-middleware + PyJWT | Apache 2.0 | OIDC, multi-tenant por realms |
| IGA (Fase 1+) | **midPoint** | EUPL | Usuario canonico multi-fuente, lifecycle, gobernanza |
| Dep. management | **uv** (Astral) | MIT | 10-100x mas rapido que pip, Docker-friendly, lockfile universal |
| Deploy | **Docker Compose** | — | Un solo `docker compose up` |

### Boilerplates de referencia
- **stevereiner/flexible-graphrag** — FastAPI + LlamaIndex + pgvector + MCP Server + Docker Compose + monitoring (Apache 2.0)
- **pmaske-aihub/rag-application** — LlamaIndex + pgvector + FastAPI minimal (punto de partida mas limpio)
- **create-llama** (`npx create-llama@latest`) — Scaffolding oficial de LlamaIndex

### Lo que SI hay que construir desde cero
1. `OAIPMHReader` para LlamaIndex (no existe en llamahub) — potencialmente publicable
2. Conector Koha SIP2/REST — no hay libreria Python mantenida
3. Servidor OAI-PMH en FastAPI para el Hub — ~500 lineas, protocolo simple
4. Validador ALICIA/RENATI — CONCYTEC no ha publicado herramientas Python

### Por que Python (y no otra cosa)

- **Backend:** Obligatorio. LlamaIndex, GROBID client, sickle, aiogram — todo el ecosistema AI/ML es Python. No hay alternativa viable.
- **Frontend:** Chainlit (Python) para Fase 0. React para Fase 1+ cuando haya UI custom.
- Python NO es para el frontend final — es para el backend + RAG + agentes.

### Framework de agentes

| Fase | Capacidad | Herramienta |
|------|-----------|-------------|
| 0 | RAG simple (busqueda semantica) | LlamaIndex + pgvector |
| 0.5 | FunctionAgent con tools (DSpace + Koha + SIS en 1 query) | LlamaIndex FunctionAgent |
| 1 | MCP server del Hub (datos publicos) | FastMCP / fastapi-mcp |
| 1+ | Estado persistente, workflows complejos | LangGraph (si se necesita) |
| 2 | Multi-agente con handoff | LlamaIndex AgentWorkflow o LangGraph |

No usar en Fase 0: LangGraph, CrewAI, AutoGen (complejidad innecesaria para 1 desarrollador).

### Arquitectura de identidad

**Problema:** Cada universidad tiene infra distinta (AD, LDAP, Azure Entra ID, Google WS, bases de datos custom, o nada).

**Solucion por fases:**

| Fase | Componente | Rol |
|------|-----------|-----|
| 0 | **Keycloak** solo | SSO via OIDC. Federa con AD/LDAP o broker de Google/Entra ID |
| 1+ | **midPoint + Keycloak** | midPoint sincroniza fuentes heterogeneas y crea usuario canonico. Keycloak emite tokens |

**midPoint como estandarizador:** Absorbe la heterogeneidad de cada universidad. GUIA Node siempre consulta la misma API de midPoint, sin importar si detras hay AD, Google o un SIS en Oracle.

**Interfaz de identidad abstracta:**
```python
class IdentityConnector(GUIAConnector):
    def get_user_info(self, user_id: str) -> dict: ...
    def get_user_roles(self, user_id: str) -> list[str]: ...

class KeycloakDirectConnector(IdentityConnector):
    """Fase 0: consulta Keycloak Admin API"""

class MidPointConnector(IdentityConnector):
    """Fase 1+: consulta midPoint REST API (usuario canonico)"""
```

### Estandares y schemas de metadatos

**Principio rector:** "Recolectar con amplitud, almacenar lo util, exponer lo requerido."

| # | Estandar | Soportado | Fase | Modo | Complejidad |
|---|---------|-----------|------|------|-------------|
| 1 | Dublin Core (Qualified) | SI | 0 | Consumir + Exponer | Baja |
| 2 | COAR Vocabularies (tipos, acceso) | SI | 0 | Consumir + almacenar como URIs | Baja |
| 3 | ALICIA 2.1.0 / CONCYTEC (38 campos) | SI | 0 | Consumir | Baja |
| 4 | RENATI / SUNEDU (namespace renati.*) | SI | 0 | Consumir | Baja |
| 5 | OpenAIRE v3 (consumir de DSpace) | SI | 0 | Consumir (ya compatible) | Baja |
| 6 | OpenAIRE v4 (exponer del Hub) | SI | 2 | Exponer (oai_openaire) | Media |
| 7 | schema.org / JSON-LD | SI | 1 | Exponer en HTML del Hub | Baja |
| 8 | DataCite | PARCIAL | 2 | Consumir (DOI, ORCID ya en modelo) | Media |
| 9 | DRIVER Guidelines | NO | — | Solo tabla traduccion DRIVER→COAR | — |
| 10 | CERIF | SI | 1+ (Person) / 2 (full) | DSpace-CRIS entidades: Person, Project, Patent, Equipment | Media |
| 11 | VIVO | NO | — | Usar ORCID API en su lugar | Alta |
| 12 | MODS / METS | NO | — | Overkill para RAG | Alta |
| 13 | ETD-MS | PARCIAL | 0 | Ya cubierto por campos RENATI | Baja |

**3 decisiones de diseno criticas:**
1. **URIs COAR en el modelo interno, nunca strings.** No guardar "Tesis" — guardar `http://purl.org/coar/resource_type/c_db06`
2. **Consumir `metadataPrefix=dim`** (DSpace Intermediate Metadata) ademas de `oai_dc`. Asi obtenemos campos `renati.*` y `thesis.*`
3. **El abstract es el campo mas importante para RAG.** En Fase 0 sin GROBID, la calidad depende 100% de `dc.description.abstract`

**11 campos OBLIGATORIOS universales de ALICIA 2.1.0:**
`dc.contributor.author`, `dc.title`, `dc.publisher`, `dc.date.issued`, `dc.type` (URI COAR), `dc.language.iso`, `dc.rights` (URI COAR), `dc.description.abstract`, `dc.subject`, `dc.subject.ocde`, `dc.identifier.uri`

**Campos adicionales para TESIS (RENATI):**
`renati.author.dni`, `dc.contributor.advisor`, `renati.advisor.orcid`, `renati.type`, `thesis.degree.name`, `renati.level`, `thesis.degree.discipline`, `thesis.degree.grantor`, `renati.juror`

### Orquestacion de equipo de desarrollo

**Paperclip** (paperclip.ing) — plataforma open-source MIT para orquestar agentes AI como una empresa (org chart, presupuesto, auditoria). 47K+ GitHub stars.
- **No para Fase 0:** Overkill para 1 desarrollador con <5 agentes
- **Evaluar en Fase 2+:** Cuando GUIA tenga harvester + RAG + respuesta + monitoreo corriendo coordinadamente
- **Sin lock-in:** MIT license, self-hosted, sin costo de plataforma (solo costo de API de LLMs)

Para Fase 0-1: Claude Code + GitHub Issues/Projects es suficiente.

### Que NO se usa y por que

| Descartado | Razon |
|-----------|-------|
| Onyx (ex Danswer) | Competidor directo, 20 contenedores, 8GB+ RAM |
| RAGFlow | Stack pesado (Go + Elasticsearch), harvesting manual |
| AnythingLLM | Node.js, orientado a uso personal |
| Open WebUI | Frontend de LLMs, no plataforma RAG |
| LangChain (como RAG) | LlamaIndex es mas eficiente para RAG puro |
| ClustPy | Libreria de clustering academico, sin relevancia para GUIA |
| MiroFish | Simulador social, AGPL incompatible con open-core |
| Zitadel | AGPL desde 2025, incompatible con SaaS |
| FreeIPA | Invasivo, solo Linux, no multi-tenant |

---

## Arquitectura tecnica

Diagramas detallados en `docs/arquitectura.md` (Mermaid, renderizados en MkDocs).

### Interfaz de conectores

```python
class GUIAConnector:
    def search(query, user_context) -> list[Result]
    def get_user_info(user_id) -> dict
    def get_status(user_id, entity) -> dict
```

---

## Competencia

| Producto | Precio | Modelo | GUIA vs. |
|----------|--------|--------|----------|
| EBSCO EDS | $20K-50K/ano | Propietario, solo busqueda | GUIA: open source, conversacional, multi-sistema |
| Ex Libris Primo | $30K-80K/ano | Propietario, ProQuest | GUIA: 100x mas barato, AI-native |
| Summon (ProQuest) | Similar a Primo | Propietario | GUIA: chat vs formulario |
| Google Scholar | Gratis | Solo papers publicos | GUIA: datos institucionales privados tambien |

---

## Archivos del proyecto

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
│   ├── conectores.md          <- interfaz GUIAConnector + conectores disponibles
│   ├── roadmap.md             <- plan operativo con sprints semanales
│   └── en/
│       └── index.md           <- version en ingles
└── .github/workflows/
    └── deploy.yml             <- build MkDocs -> landing -> deploy
```

### SciBack/guia-node — Core open source (por crear en Sprint 0.0)

```
guia-node/
├── docker-compose.yml
├── pyproject.toml             <- uv project
├── uv.lock
├── .env.example
├── src/guia/
│   ├── api/                   <- FastAPI app
│   ├── connectors/            <- DSpace, OJS (solo Research, open source)
│   ├── harvester/             <- OAI-PMH + normalizer + embedder
│   ├── rag/                   <- LlamaIndex FunctionAgent
│   └── config.py
├── docker/
│   ├── Dockerfile
│   ├── grobid/
│   └── postgres/init.sql
└── tests/
```

### SciBack/guia-campus — Conectores comerciales (por crear en Fase 1)

```
guia-campus/
├── connectors/
│   ├── koha.py                <- SIP2 / REST API
│   ├── sis.py                 <- Sistema academico (custom por universidad)
│   ├── erp.py                 <- Finanzas
│   ├── moodle.py              <- LMS
│   └── identity/
│       ├── keycloak.py        <- KeycloakDirectConnector
│       └── midpoint.py        <- MidPointConnector
├── hub/                       <- Federation broker
├── whatsapp/                  <- pywa integration
└── pyproject.toml
```

---

## Notas tecnicas

### Deploy workflow
El workflow hace: `mkdocs build --strict` -> `cp landing.html site/index.html` -> `peaceiris/actions-gh-pages`.
El `cp` sobreescribe el index.html generado por MkDocs con la landing del producto.

### Regulacion por pais (relevante para el pitch)
- Peru: Ley 30035 (repositorios interoperables obligatorios)
- Colombia: Resolucion 0777/2022
- Brasil: CAPES OA
Conectarse a GUIA permite cumplir la normativa nacional **y** tener asistente AI unificado en un solo movimiento.
