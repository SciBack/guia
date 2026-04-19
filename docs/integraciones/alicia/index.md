# ALICIA / CONCYTEC — Integración GUIA

ALICIA es el repositorio nacional de acceso abierto del Perú, gestionado por CONCYTEC.

## Rol en el ecosistema

- Validación de los 11 campos obligatorios ALICIA 2.1.0 sobre items cosechados de DSpace/OJS
- Harvesting del repositorio nacional para enriquecer el índice local
- Cumplimiento normativo: Ley 30035 exige que repositorios institucionales sean interoperables con ALICIA

## 11 campos obligatorios ALICIA 2.1.0

```
dc.contributor.author    dc.title             dc.publisher
dc.date.issued           dc.type (URI COAR)   dc.language.iso
dc.rights (URI COAR)     dc.description.abstract
dc.subject               dc.subject.ocde      dc.identifier.uri
```

## Campos adicionales RENATI (solo tesis)

```
renati.author.dni        dc.contributor.advisor   renati.advisor.orcid
renati.type              thesis.degree.name       renati.level
thesis.degree.discipline thesis.degree.grantor    renati.juror
```

## Adapter

`sciback-adapter-alicia` (en `SciBack/platform`):

```python
from sciback_adapter_alicia import AliciaHarvester, AliciaSettings

harvester = AliciaHarvester(AliciaSettings())  # URL CONCYTEC por defecto
for pub in harvester.harvest():
    print(pub.title)
```

## Variables de entorno

```env
ALICIA_OAI_URL=https://alicia.concytec.gob.pe/vufind/OAI/Server  # default
ALICIA_METADATA_PREFIX=oai_dc
```
