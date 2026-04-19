# Arquitectura

## Modelo de despliegue: Hibrido

GUIA no es SaaS puro ni self-hosted puro. Cada capa tiene su modelo de despliegue segun la sensibilidad de los datos.

```mermaid
graph TB
    subgraph saas["SaaS — Gestionado por SciBack"]
        HUB["GUIA Hub\nDatos publicos de investigacion"]
    end

    subgraph managed["Self-hosted o SciBack-managed — Por universidad"]
        NODE_A["GUIA Node\nUniversidad A"]
        NODE_B["GUIA Node\nUniversidad B"]
        NODE_C["GUIA Node\nUniversidad C"]
    end

    NODE_A -->|"Solo Capa 1\n(investigacion publica)"| HUB
    NODE_B -->|"Solo Capa 1"| HUB
    NODE_C -->|"Solo Capa 1"| HUB

    style saas fill:#1a4a2a,color:#fff
    style managed fill:#0d1b3e,color:#fff
    style HUB fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:3px
```

| Componente | Modelo | Razon |
|-----------|--------|-------|
| **GUIA Node** | Self-hosted o SciBack-managed | Datos sensibles (notas, deudas). Necesita acceso a red interna (AD, SIS) |
| **GUIA Hub** | SaaS (gestionado por SciBack) | Solo datos publicos. Un Hub central para N universidades |
| **Keycloak** | Co-desplegado con el Node | Cada universidad tiene su realm. Emite tokens OIDC |
| **midPoint IGA** | Co-desplegado (Campus+) | Estandarizador de identidad. Absorbe heterogeneidad de SIS, AD, ERP. GUIA siempre habla la misma API sin importar lo que haya detras |

---

## GUIA Node — Arquitectura completa

```mermaid
graph TB
    subgraph usuarios["Usuarios"]
        EST["Estudiante"]
        DOC["Docente"]
        BIB["Bibliotecario"]
        ADM["Administrativo"]
    end

    subgraph canales["Canales de chat"]
        WEB["Chat web\nChainlit (Fase 0)\nReact widget (Fase 1+)"]
        TG["Telegram bot\naiogram"]
        WA["WhatsApp\nBusiness API"]
        TEAMS["Microsoft Teams"]
    end

    subgraph auth["Autenticacion"]
        KC["Keycloak\nOIDC Provider\n1 realm por universidad"]
    end

    subgraph core["GUIA Node Core"]
        API["FastAPI\nREST + WebSocket"]
        AGENT["LlamaIndex FunctionAgent\nOrquesta tools segun la query"]

        subgraph tools["Tools del agente"]
            T_DS["QueryEngineTool\nDSpace (pgvector)"]
            T_OJS["QueryEngineTool\nOJS (pgvector)"]
            T_KOHA["FunctionTool\nKoha"]
            T_SIS["FunctionTool\nSIS"]
            T_ERP["FunctionTool\nERP"]
            T_MOODLE["FunctionTool\nMoodle"]
        end

        subgraph data["Data pipeline"]
            HARVEST["Harvester\nsickle (OAI-PMH)"]
            GROBID2["GROBID\nfull-text PDF"]
            EMBED["LlamaIndex\nchunking + embeddings"]
        end

        PG["PostgreSQL\npgvector + metadatos"]
        LLM["Claude API\n(o Ollama local)"]
    end

    subgraph apis["APIs externas"]
        REST["API REST\npara integraciones"]
        MCP_S["MCP Server\npara agentes AI"]
        DASH["Dashboard\nStreamlit + Plotly"]
    end

    usuarios --> canales
    canales -->|OIDC token| auth
    auth -->|JWT validado| API
    API --> AGENT
    AGENT --> tools
    AGENT --> LLM
    T_DS & T_OJS --> PG
    HARVEST --> GROBID2 --> EMBED --> PG
    API --> apis

    style core fill:#0d1b3e,color:#fff
    style tools fill:#1a4a2a,color:#fff
    style data fill:#2d1a4a,color:#fff
    style auth fill:#4a3a1a,color:#fff
    style AGENT fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:2px
    style PG fill:#1e3a5f,color:#fff,stroke:#e74c3c,stroke-width:2px
```

---

## Stack tecnico del Node

| Componente | Tecnologia | Licencia | Para que |
|-----------|-----------|----------|----------|
| RAG engine | LlamaIndex (FunctionAgent) | MIT | Chunking, embeddings, reranking, tool calling |
| OAI-PMH | sickle | BSD | Harvesting DSpace/OJS |
| PDF full-text | GROBID + grobid-client-python | Apache 2.0 | Extraccion de texto de papers |
| Vector store | pgvector (PostgreSQL) | MIT | Embeddings + busqueda semantica |
| API | FastAPI | MIT | REST + WebSocket, async |
| Chat web | Chainlit (Fase 0) / React (Fase 1+) | Apache 2.0 | Interfaz de chat |
| Telegram | aiogram | MIT | Bot gratis |
| Dashboard | Streamlit + Plotly | MIT | Visualizacion produccion cientifica |
| SSO | Keycloak | Apache 2.0 | OIDC, multi-tenant por realms |
| IGA | midPoint (Fase 1+) | EUPL | Usuario canonico multi-fuente |
| LLM | Claude API / Ollama | — | Generacion de respuestas |
| Deploy | Docker Compose | — | Un solo `docker compose up` |

---

## Docker Compose — Servicios del Node

```mermaid
graph LR
    subgraph compose["docker-compose.yml"]
        NG["nginx\nreverse proxy\nSSL termination"]
        API2["guia-api\nFastAPI + LlamaIndex"]
        CH["guia-chat\nChainlit"]
        TG2["guia-telegram\naiogram bot"]
        HV["guia-harvester\nsickle + GROBID client"]
        GR["grobid\nfull-text extraction"]
        PG2["postgres\npgvector extension"]
        KC2["keycloak\nOIDC provider"]
        DS2["streamlit-dash\nanalytics"]
    end

    NG --> API2
    NG --> CH
    NG --> KC2
    NG --> DS2
    API2 --> PG2
    API2 --> KC2
    CH --> API2
    TG2 --> API2
    HV --> GR
    HV --> PG2

    style compose fill:#0d1b3e,color:#fff
    style PG2 fill:#1e3a5f,color:#fff,stroke:#e74c3c,stroke-width:2px
    style API2 fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:2px
```

---

## Arquitectura de identidad

### Fase 0 — Keycloak solo (1 universidad, 1 fuente)

```mermaid
graph LR
    subgraph univ["Red interna universidad"]
        AD["Active Directory\no LDAP"]
        GOOGLE["Google Workspace\n(@univ.edu.pe)"]
        SIS_DB["SIS Database\n(si no hay AD)"]
    end

    KC3["Keycloak\nrealm: universidad-x"]

    subgraph guia["GUIA Node"]
        API3["FastAPI"]
        AGENT3["FunctionAgent"]
    end

    AD -->|"LDAP User\nFederation"| KC3
    GOOGLE -->|"OIDC Identity\nBrokering"| KC3
    SIS_DB -->|"Custom User\nStorage SPI"| KC3
    KC3 -->|"JWT tokens\n(roles, atributos)"| API3
    API3 --> AGENT3

    style KC3 fill:#4a3a1a,color:#fff,stroke:#f39c12,stroke-width:2px
    style guia fill:#0d1b3e,color:#fff
```

Keycloak maneja 3 escenarios comunes de universidades LATAM:

- **Tiene AD/LDAP:** User Federation directo
- **Tiene Google Workspace:** OIDC Identity Brokering (login con cuenta Google institucional)
- **Solo tiene base de datos:** Custom User Storage SPI o usuarios manuales en Keycloak

---

### Fase 0 (UPeU) / Fase 1+ (otras universidades) — midPoint + Keycloak

```mermaid
graph TB
    subgraph fuentes["Fuentes de identidad de la universidad"]
        AD2["Active Directory\nOn-premise"]
        ENTRA["Azure Entra ID\nCloud"]
        SIS2["SIS\nOracle / MySQL"]
        GOOGLE2["Google\nWorkspace"]
        KOHA2["Koha\nPatron DB"]
    end

    subgraph midpoint["midPoint (IGA)"]
        SYNC["ConnId Connectors\nSync bidireccional"]
        CANON["Usuario canonico\nCorrelacion por DNI/email"]
        RBAC["Roles dinamicos\nestudiante, docente, egresado"]
        LIFECYCLE["Lifecycle\nJoiner-Mover-Leaver"]
        MP_API["REST API\n/ws/rest/users/"]
    end

    subgraph auth2["Autenticacion"]
        KC4["Keycloak\nOIDC Provider"]
    end

    subgraph guia2["GUIA Node"]
        IDENTITY["IdentityConnector\n(MidPointConnector)"]
        AGENT4["FunctionAgent"]
    end

    fuentes --> SYNC
    SYNC --> CANON --> RBAC --> LIFECYCLE
    LIFECYCLE -->|"Provisioning\n(connector-keycloak)"| KC4
    MP_API --> IDENTITY
    KC4 -->|JWT tokens| AGENT4
    IDENTITY --> AGENT4

    style midpoint fill:#2d1a4a,color:#fff
    style CANON fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:2px
    style KC4 fill:#4a3a1a,color:#fff,stroke:#f39c12,stroke-width:2px
```

**Flujo:**

1. midPoint sincroniza identidades de todas las fuentes via ConnId
2. Crea un **usuario canonico** con reglas de correlacion (DNI, email)
3. Asigna **roles dinamicos** (estudiante activo, docente TC, egresado)
4. **Provisiona** el usuario en Keycloak via connector-keycloak
5. Keycloak emite **tokens OIDC** con roles y atributos
6. GUIA Node consulta **midPoint REST API** para atributos detallados

**Beneficio clave:** El codigo de GUIA Node es identico en todas las universidades. midPoint absorbe toda la heterogeneidad.

!!! success "Ya operativo en UPeU (piloto)"
    El stack midPoint + Keycloak + Koha + Azure EntraID esta en pre-produccion en UPeU desde 2026.
    Cuando GUIA Campus se despliegue en UPeU, esta capa ya esta construida y validada.

    | Sistema | Estado en UPeU |
    |---------|---------------|
    | midPoint 4.9.5 | UP — 192.168.15.230:8080 |
    | LAMB Academic (SIS/ERP) | Conectado via JDBC |
    | Koha (biblioteca) | Conectado via connector-koha v1.1.0 |
    | Azure EntraID | Conectado — tenant sciback.com |
    | Keycloak 26.6.0 | UP — federado con EntraID |
    | GLPI (helpdesk) | Pendiente (Fase Connect) |

---

### El patron de integracion: midPoint como hub de correlacion

midPoint no es "otro conector mas" — es la capa que hace posibles todos los conectores Campus. El problema que resuelve: **cada sistema universitario usa un ID distinto para el mismo usuario**.

```
Keycloak sabe al usuario como: "sub": "a3f9c..."  (UUID OIDC)
Koha lo conoce como:           patron_id: 1234
SIS lo conoce como:            student_id: UC-2021-00456
ERP lo conoce como:            account: FIN-9012
```

Sin midPoint, GUIA tendria que hacer su propia logica de correlacion por universidad. Con midPoint, esa logica ya esta resuelta — midPoint mantiene los `shadows` (cuentas) de cada usuario en cada sistema.

```mermaid
graph TB
    subgraph auth["1. Autenticacion (Keycloak)"]
        JWT["JWT token\nsub=a3f9c...\nroles=[estudiante_activo]"]
    end

    subgraph identity["2. Enriquecimiento de identidad (midPoint)"]
        MP2["MidPointConnector\nGET /ws/rest/users?q=name=a3f9c"]
        CANON2["Usuario canonico\nnombre: Juan Perez\nDNI: 12345678\nkoha_id: 1234\nsis_id: UC-2021-00456\nerp_id: FIN-9012\nroles: [estudiante_activo]"]
    end

    subgraph ops["3. Datos operacionales (conectores directos)"]
        KOHA3["KohaConnector\nget_loans(patron_id=1234)\n→ 2 libros, vence en 3 dias"]
        SIS3["SISConnector\nget_grades(student_id=UC-2021-00456)\n→ Estadistica: 16, Calculo: 14"]
        ERP3["ERPConnector\nget_balance(account=FIN-9012)\n→ Debe S/. 450"]
    end

    subgraph answer["4. Respuesta GUIA"]
        RESP["'Tienes 2 libros por vencer en 3 dias,\ntu nota de Estadistica es 16\ny debes S/. 450 de matricula'"]
    end

    JWT --> MP2 --> CANON2
    CANON2 --> KOHA3 & SIS3 & ERP3
    KOHA3 & SIS3 & ERP3 --> RESP

    style identity fill:#2d1a4a,color:#fff
    style ops fill:#1e3a5f,color:#fff
    style answer fill:#1a4a2a,color:#fff
```

**Regla clara:**

| Pregunta | Quien responde |
|----------|---------------|
| Quien es este usuario? | midPoint |
| Que ID tiene en Koha/SIS/ERP? | midPoint (shadows) |
| Que libros tiene prestados? | Koha (directo, con el ID de midPoint) |
| Cuales son sus notas? | SIS (directo, con el ID de midPoint) |
| Cuanto debe? | ERP (directo, con el ID de midPoint) |

### Implementacion del MidPointConnector

```python
@dataclass
class CanonicalUser:
    """Usuario canonico tal como lo ve GUIA — construido desde midPoint."""
    name: str
    display_name: str
    email: str
    dni: str
    archetype: str              # ESTUDI / DOCEN / ADMIN / EGRES
    is_active: bool
    # IDs de shadows — para consultar sistemas operacionales
    koha_patron_id: str | None
    sis_student_id: str | None
    erp_account_id: str | None
    moodle_user_id: str | None
    azure_object_id: str | None


class MidPointConnector(IdentityConnector):
    """
    Consulta midPoint REST API para obtener el usuario canonico
    con todos sus IDs de sistemas externos (account shadows).

    midPoint sabe QUIEN es el usuario y en QUE sistemas existe.
    Los conectores operacionales usan esos IDs para consultar datos reales.
    """
    def get_canonical_user(self, keycloak_sub: str) -> CanonicalUser:
        # GET /ws/rest/users?q=name={keycloak_sub}
        # Extrae shadows de cada recurso configurado
        ...

    def get_user_info(self, user_id: str) -> dict:
        return asdict(self.get_canonical_user(user_id))

    def get_user_roles(self, user_id: str) -> list[str]:
        user = self.get_canonical_user(user_id)
        return [user.archetype.lower(), "active" if user.is_active else "inactive"]


class KeycloakDirectConnector(IdentityConnector):
    """
    Fallback para Fase 0 o universidades sin midPoint.
    Solo puede dar info basica del token — sin IDs de sistemas externos.
    """
    def get_user_info(self, user_id: str) -> dict:
        # Consulta Keycloak Admin API — solo nombre, email, roles
        # NO sabe el patron_id en Koha ni el student_id en SIS
        ...
```

**Beneficio del patron:** Los conectores operacionales son simples y uniformes — siempre reciben el ID correcto, sin necesidad de busquedas por email o DNI que pueden fallar por inconsistencias de datos.

```python
# Conector Koha: simple porque ya tiene el ID correcto
class KohaConnector(GUIAConnector):
    def get_loans(self, user_context: CanonicalUser) -> list[Loan]:
        if not user_context.koha_patron_id:
            return []  # usuario sin cuenta en Koha
        return self.koha_api.get_patron_checkouts(user_context.koha_patron_id)
```

---

## Arquitectura de agentes

### Fase 0: RAG simple → Fase 0.5: FunctionAgent con tools

```mermaid
graph TB
    USER["Usuario: Puedo graduarme\neste semestre?"]

    subgraph agent["LlamaIndex FunctionAgent"]
        PLAN["Planificacion\n(Claude decide que tools llamar)"]

        subgraph tools2["Tools disponibles"]
            T1["QueryEngineTool\nDSpace pgvector\n'Buscar reglamento\nde grados'"]
            T2["FunctionTool\nSIS.get_credits\n'180/180 completos'"]
            T3["FunctionTool\nKoha.get_debts\n'0 deudas biblioteca'"]
            T4["FunctionTool\nERP.get_payments\n'0 pendientes'"]
            T5["FunctionTool\nDSpace.get_thesis_status\n'Aprobada 2025-12-01'"]
        end

        SYNTH["Sintesis\nSi, cumples todos\nlos requisitos..."]
    end

    USER --> PLAN
    PLAN --> T1 & T2 & T3 & T4 & T5
    T1 & T2 & T3 & T4 & T5 --> SYNTH

    style agent fill:#0d1b3e,color:#fff
    style PLAN fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:2px
    style SYNTH fill:#1a4a2a,color:#fff
```

### Ruta de escalado de agentes

```mermaid
graph LR
    F0["Fase 0\nRAG simple\nLlamaIndex\n+ pgvector"]
    F05["Fase 0.5\nFunctionAgent\n3-4 tools\n(DSpace+Koha+SIS)"]
    F1["Fase 1\nMCP Server\nfastapi-mcp\n(datos publicos)"]
    F2["Fase 2\nMulti-agente\nAgentWorkflow\no LangGraph"]

    F0 -->|"Agregar tools\nal agente"| F05
    F05 -->|"Exponer\ncomo MCP"| F1
    F1 -->|"Orquestacion\ncompleja"| F2

    style F0 fill:#1a4a2a,color:#fff
    style F05 fill:#1e3a5f,color:#fff
    style F1 fill:#4a3a1a,color:#fff
    style F2 fill:#2d1a4a,color:#fff
```

---

## GUIA Hub — Federacion

```mermaid
graph TB
    subgraph nodes["GUIA Nodes (self-hosted por universidad)"]
        N1["Node UPeU\nLima, Peru"]
        N2["Node UNASP\nSao Paulo, Brasil"]
        N3["Node UNACh\nChillan, Chile"]
        N4["Node Univ. Adventista\nMedellin, Colombia"]
    end

    subgraph hub["GUIA Hub — SaaS SciBack"]
        FED["Federation Broker\nResuelve queries\ncross-universidad"]
        AGG["Embeddings\nagregados"]
        OAI["OAI-PMH\nendpoint"]
        MCP_HUB["MCP Server\npublico"]
        DASH_HUB["Dashboard\nanalyticas por red"]
    end

    subgraph upstream["Redes nacionales y globales"]
        ALICIA["ALICIA\n(Peru)"]
        LAREF["LA Referencia\n(LATAM)"]
        OAIRE["OpenAIRE"]
        OALEX["OpenAlex"]
    end

    subgraph agents["Agentes AI externos"]
        CLAUDE["Claude Desktop"]
        GPT["ChatGPT"]
        CURSOR["Cursor / IDE"]
    end

    N1 -->|"Solo Capa 1\n(datos publicos)"| FED
    N2 -->|"Solo Capa 1"| FED
    N3 -->|"Solo Capa 1"| FED
    N4 -->|"Solo Capa 1"| FED

    FED --> AGG
    FED --> OAI
    FED --> MCP_HUB
    FED --> DASH_HUB

    OAI --> upstream
    MCP_HUB --> agents

    style hub fill:#1a4a2a,color:#fff
    style FED fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:3px
    style nodes fill:#0d1b3e,color:#fff
```

**Datos que fluyen al Hub:** Solo Capa 1 (investigacion publica): metadatos Dublin Core, abstracts, full-text de acceso abierto.

**Datos que NUNCA salen del Node:** Capa 2 (campus): notas, deudas, matricula, prestamos, credenciales.

---

## Notificaciones proactivas (Fase 0.5)

```mermaid
sequenceDiagram
    participant CRON as APScheduler (8am diario)
    participant KOHA as Koha API
    participant SIS as SIS API
    participant TPL as Template Engine
    participant TG as Telegram Bot
    participant USER as Estudiante

    CRON->>KOHA: get_loans_due_in(days=3)
    KOHA-->>CRON: [{user: jperez, book: "Metodologia...", due: 2026-04-07}]
    CRON->>SIS: get_thesis_deadlines(days=7)
    SIS-->>CRON: [{user: jperez, deadline: 2026-04-11, stage: "revision"}]
    CRON->>TPL: render_reminder(user, events)
    TPL-->>CRON: "Hola Juan, tienes 1 libro por vencer y tu revision de tesis es en 7 dias"
    CRON->>TG: send_message(jperez_telegram_id, message)
    TG->>USER: Push notification
```

En Fase 0.5 las notificaciones usan templates sin LLM. En Fase 1+ el LLM personaliza ("vi que tu tesis es sobre X, hay 3 nuevos articulos en OJS que podrian ser utiles").

---

## Infraestructura AWS — Node piloto UPeU

| Servicio | Especificacion | Costo estimado |
|---------|---------------|----------------|
| EC2 | t3.xlarge (4 vCPU, 16GB RAM) | ~$120/mes |
| EBS | 100GB gp3 | ~$8/mes |
| S3 | Backups y PDFs | ~$5/mes |
| CloudWatch | Logs y alertas | ~$5/mes |
| **Total** | | **~$138/mes** |

Deploy: Docker Compose con Nginx reverse proxy + SSL (Let's Encrypt).

Servicios en el compose: nginx, guia-api (FastAPI), guia-chat (Chainlit), guia-telegram (aiogram), guia-harvester (sickle), grobid, postgres (pgvector), keycloak, streamlit-dash.

---

## Fases de desarrollo

```mermaid
timeline
    title GUIA — Hoja de ruta
    section 2026
        Q2-Q3 : Fase 0 — Node piloto UPeU
               : DSpace + OJS harvesting (sickle + GROBID)
               : RAG con LlamaIndex + pgvector
               : Chat web (Chainlit) + Telegram (aiogram)
               : Keycloak SSO basico
               : Dashboard Streamlit
        Q4 : Fase 1 — Node empaquetado
            : Docker Compose listo para N universidades
            : FunctionAgent con tools (DSpace + Koha + SIS)
            : MCP Server del Hub (datos publicos)
            : React widget embebible
            : midPoint para clientes con infra compleja
    section 2027
        H1 : Fase 2 — Hub federado
            : Federacion de nodos (solo Capa 1)
            : OAI-PMH hacia ALICIA / LA Referencia
            : Conectores SIS y ERP
            : Multi-agente con handoff
        H2 : Escala LATAM
            : 10+ universidades
            : WhatsApp Business API
            : Metabase para analytics
    section 2028+
        Todo el ano : Fase 3 — Hub escalado
                    : MCP server publico
                    : 50+ universidades
                    : Sostenibilidad comercial
```
