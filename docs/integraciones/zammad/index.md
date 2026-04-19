# Zammad — Integración GUIA

Zammad es el hub multi-canal que unifica Telegram, WhatsApp, Teams, email y chat web en una sola plataforma. GUIA opera como agente automatizado dentro de Zammad.

## Rol en el ecosistema

- **Unificación de canales:** un usuario puede iniciar en WhatsApp y continuar en email en el mismo thread
- **GUIA como agente:** responde automáticamente cuando tiene confianza alta
- **Escalamiento a humano:** cuando `confidence < threshold`, el caso pasa a bibliotecario o DTI
- **Panel institucional:** el equipo UPeU ve conversaciones + tickets + SLA en una pantalla

## Distinción con GLPI

| Sistema | Qué maneja |
|---------|-----------|
| Zammad | Conversaciones (chat, email, Telegram, WhatsApp) |
| GLPI | Tickets de incidencias técnicas (TI) |

GUIA crea tickets en GLPI cuando detecta `intent=OPERACIONAL_INCIDENCIA`, pero la conversación vive en Zammad.

## Integración

```python
# guia-campus/connectors/zammad.py
class ZammadConnector:
    def create_ticket(self, subject: str, body: str, customer_email: str) -> str: ...
    def escalate_to_human(self, ticket_id: str, agent_group: str) -> None: ...
```

## Variables de entorno

```env
ZAMMAD_URL=https://zammad.upeu.edu.pe
ZAMMAD_API_TOKEN=...
GUIA_CONFIDENCE_THRESHOLD=0.75
```

## Estado

⏳ Por implementar en Sprint 0.6 (Fase 0). Primero confirmar si UPeU ya tiene Zammad desplegado.
