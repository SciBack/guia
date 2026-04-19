# Ecosistema GUIA — Documentación

Documentación centralizada de todos los componentes del ecosistema GUIA.

## Aplicaciones

| Componente | Descripción | Repo |
|-----------|-------------|------|
| [GUIA Node](guia-node/index.md) | Asistente AI institucional por universidad | SciBack/guia-node |
| [GUIA Campus](guia-campus/index.md) | Conectores comerciales (Koha, SIS, ERP, midPoint) | SciBack/guia-campus |
| [GUIA Hub](guia-hub/index.md) | Federador multi-universidad | SciBack/guia-hub |

## Plataforma SciBack

| Paquete | Descripción |
|---------|-------------|
| [sciback-core](platform/index.md) | Dominio CERIF + puertos hexagonales |
| [Adapters](platform/adapters/index.md) | DSpace, OJS, ALICIA, ORCID, Crossref, OpenAlex, ROR |

## Integraciones

| Sistema | Rol en el ecosistema |
|---------|---------------------|
| [DSpace](integraciones/dspace/index.md) | Repositorio institucional — fuente primaria de tesis y artículos |
| [OJS](integraciones/ojs/index.md) | Revistas académicas — harvesting OAI-PMH |
| [ALICIA / CONCYTEC](integraciones/alicia/index.md) | Repositorio nacional peruano — validación y cumplimiento |
| [midPoint](integraciones/midpoint/index.md) | Hub de identidad — usuario canónico multi-fuente |
| [Keycloak](integraciones/keycloak/index.md) | SSO OIDC — autenticación institucional |
| [Koha](integraciones/koha/index.md) | Sistema de biblioteca — préstamos y deudas |
| [Zammad](integraciones/zammad/index.md) | Hub multi-canal — chat, Telegram, WhatsApp, Teams |
| [Mac Mini M4](integraciones/mac-mini/index.md) | Servidor de inferencia IA — Ollama + modelos + embeddings |
