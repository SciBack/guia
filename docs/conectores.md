# Conectores

GUIA se conecta a los sistemas universitarios mediante conectores modulares. Cada conector es un modulo Python independiente que implementa la interfaz `GUIAConnector`.

---

## Capa 1 — Research (open source)

### DSpace

| Campo | Detalle |
|-------|---------|
| **Protocolo** | OAI-PMH |
| **Versiones** | DSpace 5.x, 6.x, 7.x |
| **Datos** | Tesis, articulos, reportes, datasets |
| **Fase** | 0 (piloto) |

Conector core. Cosecha metadatos Dublin Core via OAI-PMH y procesa PDFs full-text con GROBID para embeddings vectoriales.

### OJS

| Campo | Detalle |
|-------|---------|
| **Protocolo** | OAI-PMH |
| **Versiones** | OJS 3.x |
| **Datos** | Articulos de revistas, estado de envios |
| **Fase** | 0 (piloto) |

Similar a DSpace. Ademas puede consultar via REST API el estado de un envio del autor ("Mi articulo fue aceptado?").

---

## Capa 2 — Campus (licencia comercial)

### Koha

| Campo | Detalle |
|-------|---------|
| **Protocolo** | SIP2 / REST API |
| **Datos** | Prestamos activos, deudas, disponibilidad de libros, reservas |
| **Fase** | 0 (piloto — UPeU ya tiene Koha) |

Primer conector Campus. Permite preguntas como:
- "Tengo libros pendientes de devolver?"
- "Esta disponible el libro de Sampieri?"
- "Cuantos dias me quedan para devolver?"

### SIS (Sistema de Informacion Estudiantil)

| Campo | Detalle |
|-------|---------|
| **Protocolo** | REST API (varia por SIS) |
| **Datos** | Matricula, notas, horarios, creditos |
| **Fase** | 1 |

Requiere integracion custom por universidad (cada SIS es distinto). Preguntas tipicas:
- "Cual es mi horario?"
- "Ya salieron mis notas?"
- "Cuantos creditos me faltan para egresar?"

### ERP (Finanzas)

| Campo | Detalle |
|-------|---------|
| **Protocolo** | REST API (varia por ERP) |
| **Datos** | Estado de cuenta, pagos pendientes, recibos |
| **Fase** | 1 |

Preguntas tipicas:
- "Cuanto debo?"
- "Cual es la fecha limite de pago?"
- "Ya se registro mi pago?"

### AD/LDAP (Directorio)

| Campo | Detalle |
|-------|---------|
| **Protocolo** | LDAP / Microsoft Graph API |
| **Datos** | Usuario de correo, credenciales, grupos |
| **Fase** | 1 |

Preguntas tipicas:
- "Cual es mi correo institucional?"
- "Como cambio mi contrasena?"

### Moodle

| Campo | Detalle |
|-------|---------|
| **Protocolo** | Moodle REST API |
| **Datos** | Cursos, tareas pendientes, calificaciones |
| **Fase** | 2 |

Preguntas tipicas:
- "Que tareas tengo pendientes?"
- "Cual fue mi nota en el ultimo examen?"

---

## Crear un conector nuevo

```python
from guia.connectors.base import GUIAConnector, Result

class MiSistemaConnector(GUIAConnector):
    """Conector para MiSistema."""

    def search(self, query: str, user_context: dict) -> list[Result]:
        # Implementar busqueda
        ...

    def get_user_info(self, user_id: str) -> dict:
        # Info personalizada del usuario
        ...

    def get_status(self, user_id: str, entity: str) -> dict:
        # Estado de un proceso
        ...
```

Registrar en `config.yml`:

```yaml
connectors:
  - name: mi_sistema
    class: mi_sistema.MiSistemaConnector
    config:
      api_url: https://mi-sistema.universidad.edu
      api_key: ${MI_SISTEMA_API_KEY}
```
