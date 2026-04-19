# GUIA Hub

Federador multi-universidad. Agrega nodos GUIA de múltiples instituciones y expone datos públicos de investigación a redes nacionales e internacionales.

## Rol

- Resuelve queries que un nodo local no puede responder solo
- Expone endpoint OAI-PMH compatible con OpenAIRE v4, ALICIA, La Referencia
- Solo datos públicos (investigación) — nunca datos campus privados

## Jerarquía de federación (caso IASD)

```
Node UPeU → Node UAP → Node ... → Hub División → Hub Mundial → OpenAIRE / La Referencia
```

## Modelo de despliegue

SaaS gestionado por SciBack. Un Hub central sirve a N universidades.

## Estado

⏳ Por construir en Fase 2 (H1 2027). Requiere 10+ nodos activos como base.

## Stack técnico

- FastAPI (OAI-PMH server, ~500 líneas)
- Federation broker (resolución cross-nodo)
- schema.org / JSON-LD para indexación Google Scholar
- OpenAIRE v4 como formato de exposición
