# midPoint — Integración GUIA

midPoint es el hub de identidad que correlaciona usuarios de múltiples sistemas institucionales y entrega un **usuario canónico** a GUIA.

## Rol en el ecosistema

- Sincroniza: LAMB Academic (SIS/ERP) + Koha + Azure EntraID + AD/LDAP
- Entrega a GUIA un `CanonicalUser` con todos los IDs de shadows (`patron_id`, `student_id`, `account_id`)
- Sin midPoint, GUIA tendría que consultar cada sistema por separado con IDs distintos

## Estado en UPeU (abril 2026)

| Componente | Estado |
|-----------|--------|
| midPoint 4.9.5 | ✅ UP en `192.168.15.230:8080` |
| LAMB Academic (PostgreSQL SIS/ERP) | ✅ Conectado via JDBC |
| Koha | ✅ Conectado via `connector-koha` v1.1.0 |
| Azure EntraID (tenant sciback.com) | ✅ Conectado |
| Keycloak 26.6.0 | ✅ Federado con EntraID |
| Usuarios ficticios sci-* | ✅ 10 usuarios probados end-to-end (3 shadows) |
| GLPI | ⏳ Pendiente (Fase Connect) |

## Conector GUIA

```python
# guia-campus/connectors/identity/midpoint.py
class MidPointConnector:
    def get_canonical_user(self, keycloak_sub: str) -> CanonicalUser:
        """Resuelve el usuario Keycloak a sus shadows en todos los sistemas."""
```

## Fase de integración

- **Fase 0:** Keycloak directo (sin midPoint) — solo UPeU que ya lo tiene operativo
- **Fase 1+:** MidPointConnector activo — GUIA consulta `CanonicalUser` y obtiene `patron_id`, `student_id`, etc.

## Recursos

- Repo: `UPeU-Infra/` (configuración midPoint UPeU)
- Puerto REST API: `192.168.15.230:8080/midpoint`
