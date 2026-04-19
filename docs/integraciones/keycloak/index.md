# Keycloak — Integración GUIA

Keycloak provee autenticación SSO via OIDC para todos los canales de GUIA.

## Rol en el ecosistema

- Emite tokens JWT que GUIA valida en cada request
- Federa con AD/LDAP, Azure EntraID, Google Workspace de cada universidad
- 1 realm por universidad (multi-tenant)
- Co-desplegado con el Node (no SaaS central)

## Estado en UPeU

- Keycloak 26.6.0 UP
- Realm UPeU con federación Azure EntraID (tenant sciback.com)
- Usuarios sci-* probados end-to-end

## Integración en guia-node

```python
# FastAPI middleware valida JWT de Keycloak
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException
from jose import jwt
```

## Variables de entorno

```env
KEYCLOAK_URL=https://keycloak.guia.upeu.edu.pe
KEYCLOAK_REALM=upeu
KEYCLOAK_CLIENT_ID=guia-node
KEYCLOAK_CLIENT_SECRET=...
```

## Chainlit + Keycloak OIDC

Chainlit soporta auth OIDC nativamente. En Sprint 0.6 se configura el realm UPeU para que usuarios institucionales puedan chatear autenticados.
