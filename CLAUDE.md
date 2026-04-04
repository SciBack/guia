# CLAUDE.md — Proyecto GUIA

## Que es este proyecto

**GUIA** (Gateway Universitario de Informacion y Asistencia) es una plataforma open-source AI-native que unifica el acceso a toda la informacion universitaria en un solo punto conversacional. En vez de que estudiantes, docentes y administrativos naveguen 10 plataformas distintas, GUIA conecta todos los sistemas institucionales y responde via chat (web, Telegram, WhatsApp, Teams).

**Nombre:** GUIA = Gateway Universitario de Informacion y Asistencia. Termina en IA intencionalmente.
**Modelo:** Open-core. Core gratuito (Apache 2.0), conectores Campus y soporte gestionado = pago.
**Empresa:** SciBack (Alberto Sanchez, fundador).
**Piloto:** Universidad Peruana Union (UPeU), Lima, Peru.
**Dominio Fase 1:** guia.sciback.com (subdominio SciBack, disponible de inmediato).
**Sitio web:** https://upeu-infra.github.io/ariel/ (pendiente migrar repo)
**Repo GitHub:** https://github.com/UPeU-Infra/ariel (pendiente renombrar)

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

| Tier | Incluye | Precio estimado |
|------|---------|----------------|
| **Community** | Research core (DSpace + OJS + RAG) | Gratis (open source) |
| **Campus Basic** | + Koha + directorio LDAP | ~$100-200/mes |
| **Campus Pro** | + SIS + ERP + Moodle | ~$300-500/mes |
| **Campus Enterprise** | + WhatsApp + analytics + SLA | ~$500-1000/mes |
| **Hub** | Federacion de nodos | ~$500-5000/mes segun miembros |

**Posicionamiento:** Alternativa open-source a EBSCO EDS / Ex Libris Primo / Summon.
- EDS: $20K-50K/ano. GUIA: ~$50-100/mes para el core.
- Chat conversacional + WhatsApp en vez de formularios de busqueda.

---

## Estado actual (abril 2026)

### Completado
- Nombre oficial definido: GUIA
- Arquitectura tecnica definida (Node + Hub, dos capas)
- Modelo comercial open-core definido
- Sitio web (pendiente actualizar con nueva identidad)

### Pendiente inmediato (Fase 0)
- Actualizar sitio web y documentacion con identidad GUIA
- Renombrar repo de ariel a guia
- Reunir con DTI UPeU — presentar como piloto
- Configurar subdominio guia.sciback.com
- Construir el Node piloto: harvester + RAG + chat basico
- Primer conector: DSpace UPeU (OAI-PMH)
- Segundo conector: Koha UPeU (SIP2/API REST)

---

## Fases

| Fase | Periodo | Objetivo |
|------|---------|----------|
| 0 | 2026 Q2-Q3 | Node piloto UPeU (1 DSpace + 1 OJS + 1 Koha) |
| 1 | 2026 Q4 | Node empaquetado Docker Compose, 2-3 universidades |
| 2 | 2027 | Hub federado piloto, OAI-PMH para redes nacionales |
| 3 | 2028+ | Hub escalado + MCP server publico |

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

## Arquitectura tecnica

### GUIA Node (por universidad)

```
┌─────────────────────────────────────────────┐
│              GUIA Node                      │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  Capa 1: Research (core, OSS)       │    │
│  │  - DSpace connector (OAI-PMH)       │    │
│  │  - OJS connector (OAI-PMH)          │    │
│  │  - GROBID (full-text PDF)           │    │
│  │  - Embeddings + pgvector            │    │
│  │  - RAG engine                       │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  Capa 2: Campus (conectores, pago)  │    │
│  │  - Koha (prestamos, deudas)         │    │
│  │  - SIS (matricula, notas)           │    │
│  │  - ERP (estado de cuenta)           │    │
│  │  - AD/LDAP (usuario, correo)        │    │
│  │  - Moodle (tareas, cursos)          │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  Motor: pgvector + RAG + LLM               │
│  Canales: Chat web · Telegram · WhatsApp    │
│  API: REST + MCP server                     │
└─────────────────────────────────────────────┘
         │
         │ Solo Capa 1 federa hacia arriba
         ▼
┌─────────────────────────────────────────────┐
│              GUIA Hub                       │
│  (por consorcio / red / pais)               │
│  - Solo datos publicos de investigacion     │
│  - OAI-PMH para redes nacionales            │
│  - MCP server publico                       │
└─────────────────────────────────────────────┘
```

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

```
~/proyectos/upeu/ariel/   (pendiente renombrar a guia/)
├── CLAUDE.md                  <- este archivo
├── landing.html               <- landing page del producto
├── mkdocs.yml                 <- config MkDocs Material bilingue ES/EN
├── requirements.txt
├── docs/
│   ├── index.md               <- que es GUIA, para quien
│   ├── arquitectura.md        <- Node + Hub + conectores
│   ├── quickstart.md          <- "levanta tu Node en 15 min"
│   ├── modelo-comercial.md    <- tiers, precios, comparacion
│   ├── conectores/
│   │   ├── dspace.md
│   │   ├── ojs.md
│   │   ├── koha.md
│   │   └── moodle.md
│   └── en/                    <- version en ingles
└── .github/workflows/
    └── deploy.yml             <- build MkDocs -> landing -> deploy
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
