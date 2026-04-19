# OJS — Integración GUIA

Open Journal Systems — fuente de artículos de revistas académicas institucionales.

## Rol en el ecosistema

- Harvesting OAI-PMH → `sciback-adapter-ojs` → pgvector → RAG
- Complementa DSpace: tesis en DSpace, artículos de revistas en OJS

## Instancias relevantes

| Instancia | URL | Estado |
|-----------|-----|--------|
| Portal revistas UPeU | `https://revistas.upeu.edu.pe` | Por confirmar |

## Adapter

`sciback-adapter-ojs` (en `SciBack/platform`):

```python
from sciback_adapter_ojs import OjsAdapter, OjsSettings

adapter = OjsAdapter(OjsSettings(
    base_url="https://revistas.upeu.edu.pe",
    oai_pmh_url="https://revistas.upeu.edu.pe/index.php/index/oai",
))
for pub in adapter.harvest():
    print(pub.title)
```

## Variables de entorno

```env
OJS_BASE_URL=https://revistas.upeu.edu.pe
OJS_OAI_PMH_URL=https://revistas.upeu.edu.pe/index.php/index/oai
OJS_API_TOKEN=...    # opcional, para REST API v3
```

## Pendientes

- [ ] Confirmar URLs OAI-PMH de todas las revistas OJS UPeU
- [ ] Listar journals disponibles (`?verb=ListSets`)
