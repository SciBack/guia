# CLAUDE.md — SciBack/guia (instrucciones operativas)

## ⚠️ Popup "Léeme" — cómo modificarlo

El popup "Léeme" que ven los usuarios en GUIA **NO usa `chainlit.md`**.

### Arquitectura real
`auto-login.js` intercepta el clic del botón "Léeme" con `capture:true` antes de que React lo procese,
y abre un modal custom que carga: **`public/readme-content.html`**

### Regla obligatoria
Cada vez que se integre una nueva fuente de datos o feature en GUIA, actualizar `public/readme-content.html`:
- Nueva fuente operativa → moverla a la sección "✅ Lo que puedo hacer ahora" con número de registros
- Fuente no disponible → moverla a "🔜 Próximamente"
- Cambio en número de registros indexados → actualizar el número

### Archivos implicados
| Propósito | Archivo |
|---|---|
| **Contenido del popup Léeme** | `public/readme-content.html` ← ESTE es el que importa |
| Lógica del modal | `public/auto-login.js` → función `buildReadmeModal()` |
| Metadata API /project/settings | `chainlit.md` (NO afecta el popup visual) |

### Flujo de deploy sin rebuild
Los mounts en `docker-compose.yml` permiten que un `git pull` en el servidor sea suficiente:
```
./public:/app/public:ro
./.chainlit:/app/.chainlit:ro
./chainlit.md:/app/chainlit.md:ro
./src:/app/src:ro
```

### Estado de fuentes indexadas (2026-04-29)
- ✅ Koha UPeU — 34,985 libros
- ✅ OJS revistas.upeu.edu.pe — 744 artículos
- 🔜 DSpace repositorio.upeu.edu.pe — bloqueado (403, IP no whitelisted)
- 🔜 ALICIA — pendiente Fase 1

---

> Ver `~/.claude/projects/-Users-alberto-proyectos-sciback-guia/memory/chainlit_features.md`
> para el inventario completo de features Chainlit activados y pendientes.
