# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (main) | ✅ |

## Reporting a Vulnerability

**Do NOT report security vulnerabilities via public GitHub Issues.**

GUIA handles sensitive institutional data (student records, library loans, academic grades). Security issues must be reported privately.

**Contact:** [security@sciback.com](mailto:security@sciback.com)

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive an acknowledgment within 48 hours. We aim to release a fix within 14 days for critical issues.

## Scope

This policy covers:
- `SciBack/guia` — documentation and website
- `SciBack/guia-node` — open source core (OAI-PMH harvester, RAG engine, API)

## Data handled by GUIA

GUIA Node may process:
- Public research metadata (OAI-PMH from DSpace/OJS) — low sensitivity
- Student academic records via Campus connectors (grades, enrollment, library loans) — **high sensitivity**

Deployments handling Campus data must follow their institution's data protection policy and applicable regulations (Peru: Ley 29733 — Protección de Datos Personales).
