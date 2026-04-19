# Koha — Integración GUIA

Koha es el sistema de gestión de biblioteca de UPeU. GUIA lo consulta para responder preguntas sobre préstamos y deudas.

## Rol en el ecosistema

- "¿Tengo libros vencidos?" → `KohaConnector.get_loans(patron_id)`
- "¿Tengo multas en biblioteca?" → `KohaConnector.get_debts(patron_id)`
- Parte de GUIA Campus (conector comercial, Fase 1)

## Conector existente

`UPeU-Infra/connector-koha` v1.1.0 — conector Java ConnId para midPoint.

El conector de GUIA Campus es distinto: cliente Python directo a la REST API de Koha.

## Integración

```python
# guia-campus/connectors/koha.py
class KohaConnector:
    def get_loans(self, patron_id: str) -> list[Loan]: ...
    def get_debts(self, patron_id: str) -> list[Debt]: ...
```

El `patron_id` lo provee midPoint via `CanonicalUser.shadows["koha"]`.

## Variables de entorno

```env
KOHA_API_URL=http://koha.upeu.edu.pe:8081
KOHA_API_KEY=...
```

## Estado

⏳ Por implementar en Fase 1 (Sprint 1.2).
