# sciback-platform

Monorepo `SciBack/platform` con 12 paquetes Python que forman la base técnica del ecosistema GUIA.

Local: `/Users/alberto/proyectos/sciback/platform`

## sciback-core v0.11.0

Dominio CERIF y contratos hexagonales (puertos).

| Módulo | Contenido |
|--------|-----------|
| `sciback_core.model` | 13 entidades CERIF: Publication, Person, Project, OrgUnit, etc. |
| `sciback_core.ports` | LLMPort, VectorStorePort, EventBusPort, JobQueuePort, Repository, UnitOfWork |
| `sciback_core.services` | PublicationIngestService |
| `sciback_core.events` | DomainEvent, OutboxORM, relay worker |
| `sciback_core.export` | `to_dublin_core_xml()`, `to_datacite_xml()` |

## Estado

✅ 834 tests pasando. ruff limpio. Listo para ser consumido por guia-node.

## Paquetes disponibles

Ver [Adapters](adapters/index.md).
