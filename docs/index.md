# GUIA

<div class="hero" markdown>

## Gateway Universitario de Informacion y Asistencia

*Plataforma open-source AI-native que unifica toda la informacion universitaria en un solo chat*

</div>

---

## El problema

Cada universidad tiene 10+ sistemas desconectados. Los estudiantes no saben donde buscar.

```mermaid
graph TD
    A["Estudiante con una pregunta"] --> B["Donde busco?"]
    B --> C["DSpace\nTesis y articulos"]
    B --> D["OJS\nRevistas"]
    B --> E["Koha\nBiblioteca"]
    B --> F["SIS\nMatricula y notas"]
    B --> G["Moodle\nTareas"]
    B --> H["ERP\nPagos"]
    B --> I["Correo\nUsuario y clave"]

    style A fill:#1e3a5f,color:#fff
    style B fill:#c0392b,color:#fff
```

**Resultado:** frustacion, llamadas al helpdesk, informacion perdida, plataformas subutilizadas.

---

## La solucion: GUIA

Un solo chat que conecta todos los sistemas. El estudiante pregunta en lenguaje natural y GUIA responde.

```mermaid
graph TD
    A["Estudiante pregunta\nen chat"] --> GUIA["GUIA Node\nAI + RAG + Conectores"]
    GUIA --> C["DSpace"]
    GUIA --> D["OJS"]
    GUIA --> E["Koha"]
    GUIA --> F["SIS"]
    GUIA --> G["Moodle"]
    GUIA --> H["ERP"]
    GUIA --> I["LDAP"]

    style A fill:#1e3a5f,color:#fff
    style GUIA fill:#27ae60,color:#fff,stroke:#f39c12,stroke-width:3px
```

---

## Ejemplos de uso

<div class="grid cards" markdown>

-   :fontawesome-solid-search: **Investigacion**

    "Que tesis hay sobre inteligencia artificial en educacion?"
    "En que estado esta la publicacion de mi articulo en la revista?"

-   :fontawesome-solid-book: **Biblioteca**

    "Tengo algun libro pendiente de devolver?"
    "Hay disponible el libro de Sampieri?"

-   :fontawesome-solid-graduation-cap: **Academico**

    "Cual es mi horario de clases?"
    "Ya salieron mis notas del parcial?"

-   :fontawesome-solid-credit-card: **Financiero**

    "Cuanto debo de matricula?"
    "Cual es la fecha limite de pago?"

-   :fontawesome-solid-envelope: **Institucional**

    "Cual es mi correo institucional?"
    "Como cambio mi contrasena?"

-   :fontawesome-solid-calendar: **Eventos**

    "Que congresos hay este mes?"
    "Donde me inscribo al simposio de investigacion?"

</div>

---

## Dos productos, un ecosistema

| Producto | Para quien | Que hace |
|----------|-----------|----------|
| **GUIA Node** | Cualquier universidad | Asistente AI que conecta todos los sistemas locales |
| **GUIA Hub** | Consorcios, redes, denominaciones | Federa nodos para busqueda unificada de investigacion |

```mermaid
graph BT
    N1["GUIA Node\nUniversidad A"] --> HUB["GUIA Hub\nConsorcio / Red"]
    N2["GUIA Node\nUniversidad B"] --> HUB
    N3["GUIA Node\nUniversidad C"] --> HUB
    HUB --> LA["Redes nacionales\nALICIA, BDTD, SNRD"]
    HUB --> GLOBAL["Indexadores globales\nOpenAIRE, OpenAlex, BASE"]

    style HUB fill:#1e3a5f,color:#fff,stroke:#f39c12,stroke-width:3px
    style N1 fill:#27ae60,color:#fff
    style N2 fill:#27ae60,color:#fff
    style N3 fill:#27ae60,color:#fff
```

!!! info "Separacion de datos"
    Los datos de campus (notas, pagos, prestamos) son **privados** y nunca salen del Node.
    Solo los datos de investigacion (tesis, articulos) federan hacia el Hub.

---

## Open source

GUIA es open-core:

- **Core (Research):** Apache 2.0 — gratuito para siempre
- **Conectores Campus:** Licencia comercial SciBack
- **Soporte gestionado:** Suscripcion mensual

[:fontawesome-solid-arrow-right: Arquitectura](arquitectura.md){ .md-button .md-button--primary }
[:fontawesome-solid-arrow-right: Modelo Comercial](modelo-comercial.md){ .md-button }
