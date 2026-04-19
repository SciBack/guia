# GUIA

**Gateway Universitario de Información y Asistencia**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-guia.sciback.com-green)](https://guia.sciback.com)

Open source AI-native platform that unifies access to all university information in a single conversational interface. Instead of navigating 10 different systems, students, faculty, and staff ask GUIA — and GUIA answers via web chat, Telegram, WhatsApp, or Microsoft Teams.

> "What thesis exist about climate change?" · "Is my library loan overdue?" · "When does enrollment close?" — all in one place.

---

## How it works

GUIA connects institutional systems via a modular connector architecture:

- **Research layer (open source):** harvests DSpace and OJS via OAI-PMH, processes full-text PDFs with GROBID, builds vector embeddings with pgvector, and answers research queries via RAG.
- **Campus layer (commercial connectors):** Koha (library), SIS (academic records), ERP (finance), Moodle (LMS), Keycloak SSO.
- **Hub (federation):** aggregates nodes from multiple universities, exposes OAI-PMH endpoint compatible with national networks (ALICIA, LA Referencia, OpenAIRE).

---

## Repositories

| Repository | Visibility | Contents |
|-----------|-----------|----------|
| **SciBack/guia** (this repo) | Public | Documentation + project website (MkDocs) |
| **SciBack/guia-node** | Public (Apache 2.0) | Open source core: harvester, RAG, DSpace+OJS connectors, API, chat |
| **SciBack/guia-campus** | Private | Commercial connectors: Koha, SIS, ERP, WhatsApp, Hub |

---

## Documentation

Full documentation at **[guia.sciback.com](https://guia.sciback.com)**

- [Architecture](https://guia.sciback.com/arquitectura/) — Node + Hub design, identity, agent framework
- [Standards](https://guia.sciback.com/estandares/) — ALICIA 2.1.0, COAR, RENATI, OpenAIRE metadata schemas
- [Connectors](https://guia.sciback.com/conectores/) — GUIAConnector interface and available integrations
- [Roadmap](https://guia.sciback.com/roadmap/) — Phase 0–3 plan with weekly sprints

---

## Local development (docs site)

```bash
git clone https://github.com/SciBack/guia.git
cd guia
pip install -r requirements.txt
python3 -m mkdocs serve
# → http://localhost:8000
```

---

## Who is GUIA for?

- **Universities** in Latin America with DSpace and/or OJS installations
- **Developers** who want to contribute connectors or extend the RAG engine
- **Researchers** building on top of open academic repository infrastructure

Pilot institution: **Universidad Peruana Unión (UPeU)**, Lima, Perú.

---

## Compliance

GUIA is designed to comply with Peruvian and Latin American open access mandates:

- CONCYTEC / ALICIA 2.1.0 — institutional repository metadata
- SUNEDU / RENATI — thesis and academic work metadata
- Ley 30035 (Peru) — interoperable institutional repositories
- OpenAIRE v4 / OAI-PMH — international interoperability

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute documentation or report issues.
For code contributions, see `SciBack/guia-node`.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## Security

To report a security vulnerability, see [SECURITY.md](SECURITY.md). Do not use public issues.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Copyright 2024–2026 [SciBack](https://sciback.com)
