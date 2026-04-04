# GUIA

<div class="hero" markdown>

## Gateway Universitario de Informacion y Asistencia

*Open-source AI-native platform that unifies all university information into a single chat*

</div>

---

## The problem

Every university has 10+ disconnected systems. Students don't know where to look.

```mermaid
graph TD
    A["Student with a question"] --> B["Where do I search?"]
    B --> C["DSpace\nTheses & articles"]
    B --> D["OJS\nJournals"]
    B --> E["Koha\nLibrary"]
    B --> F["SIS\nEnrollment & grades"]
    B --> G["Moodle\nAssignments"]
    B --> H["ERP\nPayments"]
    B --> I["Email\nUsername & password"]

    style A fill:#1e3a5f,color:#fff
    style B fill:#c0392b,color:#fff
```

---

## The solution: GUIA

A single chat that connects all systems. Students ask in natural language, GUIA answers.

```mermaid
graph TD
    A["Student asks\nin chat"] --> GUIA["GUIA Node\nAI + RAG + Connectors"]
    GUIA --> C["DSpace"]
    GUIA --> D["OJS"]
    GUIA --> E["Koha"]
    GUIA --> F["SIS"]
    GUIA --> G["Moodle"]
    GUIA --> H["ERP"]
    GUIA --> I["LDAP"]

    style A fill:#1e3a5f,color:#fff
    style GUIA fill:#27ae60,color:#fff,stroke:#f39c12,stroke-width:3px
```

---

## Two products, one ecosystem

| Product | For whom | What it does |
|---------|---------|-------------|
| **GUIA Node** | Any university | AI assistant connecting all local systems |
| **GUIA Hub** | Consortia, networks, denominations | Federates nodes for unified research search |

---

## Open source

GUIA is open-core:

- **Core (Research):** Apache 2.0 — free forever
- **Campus connectors:** Commercial license (SciBack)
- **Managed support:** Monthly subscription

[:fontawesome-solid-arrow-right: Architecture](../arquitectura.md){ .md-button .md-button--primary }
[:fontawesome-solid-arrow-right: Business Model](../modelo-comercial.md){ .md-button }
