# GUIA Campus

Conectores comerciales para sistemas institucionales. Código privado — repo `SciBack/guia-campus`.

## Conectores incluidos

| Conector | Sistema | Qué expone a GUIA |
|----------|---------|-------------------|
| `koha.py` | Koha | Préstamos, deudas, catálogo |
| `sis.py` | Sistema académico | Matrículas, notas, horarios |
| `erp.py` | Sistema financiero | Estado de cuenta, pagos pendientes |
| `moodle.py` | Moodle LMS | Tareas, cursos, calificaciones |
| `keycloak.py` | Keycloak Admin API | Identidad directa (Fase 0) |
| `midpoint.py` | midPoint REST API | Usuario canónico (Fase 1+) |
| `zammad.py` | Zammad | Hub multi-canal, escalamiento a humano |
| `glpi.py` | GLPI | Tickets de incidencias técnicas |
| `whatsapp.py` | WhatsApp Cloud API | Canal messaging (pywa) |

## Estado

⏳ Por crear en Fase 1 (octubre 2026).

## Relación con guia-node

`guia-node` (open source) define la interfaz `GUIAConnector`. `guia-campus` implementa esa interfaz para cada sistema comercial. Se instala como paquete opcional encima del Node.
