# Arquitectura

## GUIA Node — por universidad

Cada universidad instala un GUIA Node que conecta sus sistemas locales y expone un chat unificado.

```mermaid
graph TD
    subgraph canales["Canales de chat"]
        WEB["Chat web\n(widget embebible)"]
        TG["Telegram bot"]
        WA["WhatsApp\nBusiness API"]
        TEAMS["Microsoft Teams"]
    end

    subgraph node["GUIA Node"]
        RAG["RAG Engine\npgvector + LLM"]
        subgraph capa1["Capa 1: Research (OSS)"]
            DS["DSpace\nOAI-PMH"]
            OJS2["OJS\nOAI-PMH"]
            GROBID2["GROBID\nfull-text PDF"]
        end
        subgraph capa2["Capa 2: Campus (pago)"]
            KOHA["Koha\nSIP2 / API"]
            SIS["SIS\nAPI"]
            ERP["ERP\nAPI"]
            LDAP["AD/LDAP"]
            MOODLE["Moodle\nAPI"]
        end
    end

    subgraph api["APIs"]
        REST["API REST"]
        MCP["MCP Server"]
    end

    canales --> RAG
    capa1 --> RAG
    capa2 --> RAG
    RAG --> api

    style node fill:#0d1b3e,color:#fff
    style capa1 fill:#1a4a2a,color:#fff
    style capa2 fill:#4a1a1a,color:#fff
    style RAG fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:2px
```

---

## Stack tecnico

| Componente | Tecnologia | Notas |
|-----------|-----------|-------|
| Harvester | Python + pyoaiharvest | Cosecha OAI-PMH cada 24h |
| Full-text | GROBID | Extrae texto de PDFs cientificos |
| Embeddings | pgvector (PostgreSQL) | Vectores para busqueda semantica |
| RAG | LangChain / LlamaIndex | Orquestacion de retrieval + generacion |
| LLM | Claude API / Ollama local | Segun presupuesto del cliente |
| Chat web | Widget JS embebible | <script> tag en cualquier pagina |
| Telegram | python-telegram-bot | Gratis, sin costo de API |
| WhatsApp | WhatsApp Business API | Requiere cuenta Meta Business verificada |
| Deploy | Docker Compose | Un solo `docker compose up` |

---

## Interfaz de conectores

Cada conector implementa una interfaz estandar:

```python
class GUIAConnector:
    """Interfaz base para conectores GUIA."""

    def search(self, query: str, user_context: dict) -> list[Result]:
        """Busqueda semantica sobre el sistema conectado."""
        ...

    def get_user_info(self, user_id: str) -> dict:
        """Info personalizada del usuario (prestamos, notas, deudas)."""
        ...

    def get_status(self, user_id: str, entity: str) -> dict:
        """Estado de un proceso (tesis, articulo, pago)."""
        ...
```

Esto permite que cualquier desarrollador cree conectores nuevos para sistemas no cubiertos.

---

## GUIA Hub — por consorcio/red

El Hub agrega multiples Nodes para busqueda federada de investigacion.

```mermaid
graph TD
    subgraph nodes["GUIA Nodes"]
        N1["Node Universidad A\nDSpace + OJS + Koha"]
        N2["Node Universidad B\nDSpace + Moodle"]
        N3["Node Universidad C\nOJS + SIS"]
    end

    HUB["GUIA Hub\nFederation Broker"]

    subgraph upstream["Redes y agregadores"]
        LA["LA Referencia"]
        OA["OpenAIRE"]
        OALEX["OpenAlex"]
        BASE2["BASE / CORE"]
    end

    N1 -->|"Solo Capa 1\n(investigacion)"| HUB
    N2 -->|"Solo Capa 1"| HUB
    N3 -->|"Solo Capa 1"| HUB
    HUB -->|OAI-PMH| upstream

    style HUB fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:3px
    style nodes fill:#1a4a2a,color:#fff
```

**Funciones del Hub:**
- Federation broker: resuelve queries que un nodo local no puede
- Embeddings agregados de todos los nodos miembro
- OAI-PMH endpoint para compatibilidad con redes nacionales
- MCP server publico (corpus completo accesible desde agentes AI)
- Dashboard de visibilidad y analiticas

---

## Infraestructura (AWS)

Para el piloto UPeU:

| Servicio | Especificacion | Costo estimado |
|---------|---------------|----------------|
| EC2 | t3.xlarge (4 vCPU, 16GB RAM) | ~$120/mes |
| EBS | 100GB gp3 | ~$8/mes |
| S3 | Backups y PDFs | ~$5/mes |
| CloudWatch | Logs y alertas | ~$5/mes |
| **Total** | | **~$138/mes** |

Deploy: Docker Compose con Nginx reverse proxy + SSL (Let's Encrypt).

---

## Fases de desarrollo

```mermaid
timeline
    title GUIA — Hoja de ruta
    section 2026
        Q2-Q3 : Fase 0 — Node piloto UPeU
               : DSpace + OJS + Koha
               : Chat web + Telegram
               : RAG basico funcionando
        Q4 : Fase 1 — Node empaquetado
            : Docker Compose listo
            : 2-3 universidades piloto
            : Primeros clientes SciBack
    section 2027
        H1 : Fase 2 — Hub piloto
            : Federacion de nodos
            : OAI-PMH hacia redes nacionales
            : Conectores SIS y ERP
        H2 : Escala LATAM
            : 10+ universidades
            : WhatsApp Business API
    section 2028+
        Todo el ano : Fase 3 — Hub escalado
                    : MCP server publico
                    : 50+ universidades
                    : Sostenibilidad comercial
```
