# DSpace — Integración GUIA

DSpace es la fuente primaria de tesis, artículos y producción científica institucional.

## Rol en el ecosistema

- Harvesting OAI-PMH → `sciback-adapter-dspace` → pgvector → RAG
- REST API DSpace 7.x para descarga de PDFs (GROBID full-text, Fase 1)
- Fuente de entidades CERIF: Person (autores), Publication (items)

## Instancias relevantes

| Instancia | URL | Estado |
|-----------|-----|--------|
| DSpace UPeU | `https://repositorio.upeu.edu.pe` | En transición (consultor → DTI UPeU) |

## Adapter

`sciback-adapter-dspace` (en `SciBack/platform`):

```python
from sciback_adapter_dspace import DSpaceAdapter, DSpaceSettings

adapter = DSpaceAdapter(DSpaceSettings(
    base_url="https://repositorio.upeu.edu.pe",
    oai_pmh_url="https://repositorio.upeu.edu.pe/oai",
))
for pub in adapter.harvest():
    print(pub.title)
```

## Variables de entorno

```env
DSPACE_BASE_URL=https://repositorio.upeu.edu.pe
DSPACE_OAI_PMH_URL=https://repositorio.upeu.edu.pe/oai
DSPACE_EMAIL=admin@upeu.edu.pe      # opcional, para REST API autenticada
DSPACE_PASSWORD=...                  # opcional
```

## Pendientes

- [ ] Confirmar endpoint OAI-PMH (actualmente 403 desde internet — solo red UPeU)
- [ ] Coordinar con DTI UPeU apertura del OAI-PMH al EC2 de GUIA
- [ ] Verificar sets disponibles (`?verb=ListSets`)
- [ ] Verificar cobertura de abstracts (base del RAG)
