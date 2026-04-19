# Adapters — sciback-platform

Todos los adapters están en `SciBack/platform/packages/`. Cada uno es instalable de forma independiente.

## Adapters CERIF-nativos (Capa 2)

| Paquete | Versión | Qué hace | Tests |
|---------|---------|----------|-------|
| `sciback-adapter-dspace` | 0.1.0 | DSpace 7.x REST API + OAI-PMH + mapper DC→Publication | 5 ✅ |
| `sciback-adapter-ojs` | 0.1.0 | OJS REST API v3 + OAI-PMH, título multilang | 5 ✅ |
| `sciback-adapter-alicia` | 0.1.0 | CONCYTEC OAI-PMH + validación ALICIA 2.1.0 + DRIVER/COAR | 3 ✅ |
| `sciback-adapter-orcid` | 0.1.0 | ORCID Public API v3.0 + checksum ISO 7064 MOD 11-2 | 6 ✅ |
| `sciback-adapter-crossref` | 0.1.0 | Crossref REST polite pool | ✅ |
| `sciback-adapter-openalex` | 0.1.0 | OpenAlex API | ✅ |
| `sciback-adapter-ror` | 0.1.0 | Research Organization Registry | ✅ |

## Adapters de tecnología genérica (Capa 3)

| Paquete | Versión | Qué hace | Tests |
|---------|---------|----------|-------|
| `sciback-llm-claude` | 0.1.0 | Anthropic Claude API → LLMPort | ✅ |
| `sciback-llm-ollama` | 0.1.0 | Ollama HTTP API → LLMPort | ✅ |
| `sciback-embeddings-e5` | 0.1.0 | multilingual-e5-large-instruct via Ollama | ✅ |
| `sciback-vectorstore-pgvector` | 0.1.0 | pgvector + cosine similarity + IVFFlat | 14 ✅ |

## Patrón de uso en guia-node

```python
from sciback_adapter_dspace import DSpaceAdapter, DSpaceSettings
from sciback_embeddings_e5 import E5Adapter, E5Settings
from sciback_vectorstore_pgvector import PgVectorStore, PgVectorConfig
from sciback_core.ports.llm import LLMPort
```

Cada adapter implementa el puerto correspondiente de `sciback-core`. `guia-node` importa solo las interfaces, nunca las implementaciones directamente.
