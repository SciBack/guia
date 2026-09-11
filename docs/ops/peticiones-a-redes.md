# Lo que GUIA necesita de Redes

Dos cosas, las dos comprobadas en vivo el **11-sep-2026** desde el servidor de
GUIA (`192.168.15.167`). Ninguna es urgente: GUIA funciona hoy sin ellas, con
parches que conviene retirar.

---

## 1. Registro DNS interno de `calidad.upeu.edu.pe`

**Qué pedir:** añadir `calidad.upeu.edu.pe → 3.18.90.66` a los DNS internos
`192.168.13.96` y `192.168.13.97`.

**Por qué.** Esos DNS son autoritativos para `upeu.edu.pe` y **no tienen ese
registro**, aunque el DNS público sí. Tienen los de al lado:

| nombre | resuelve desde el .167 |
|---|---|
| `cris.upeu.edu.pe` | 3.137.35.74 |
| `repositorio.upeu.edu.pe` | 3.15.82.50 |
| **`calidad.upeu.edu.pe`** | **NO RESUELVE** |

No es un problema de red: el servidor alcanza esa IP sin dificultad (HTTP 200
con `--resolve`).

**Parche actual:** `extra_hosts` en `docker-compose.upeu.yml`. Funciona porque
es una Elastic IP y no baila, pero es un dato duplicado que envejece solo.
**Retirarlo cuando el registro exista.**

---

## 2. Puerto 3306/TCP hacia la base de Koha

**Qué pedir:** permitir `192.168.15.167` → `192.168.12.136` : `3306/TCP`.

Es **una sola máquina**: `koha-plus-prod.upeu`, con Koha y su MariaDB 10.11.14
en el mismo host (Ubuntu 24.04, base `koha_upeu`, 2,9 GB). Hoy el 3306 está
cerrado desde el servidor de GUIA; el 22 también.

> El primer borrador de esta petición decía `192.168.12.130`, que es **otro
> Koha** — allí el biblionumber 12987 es un libro distinto y el 28277 no
> existe. Dato confirmado: `koha_upeu` tiene **46.678 registros**, que es
> exactamente lo que GUIA tiene indexado. El secreto `koha-prod.env` llevaba
> el host equivocado y ya está corregido.

### Qué se gana, medido sobre el catálogo COMPLETO (46.678 registros)

GUIA cosecha hoy por la REST API, que no expone estos campos:

| campo | REST (hoy) | base de datos |
|---|---|---|
| tabla de contenidos (MARC 505) | **0%** | **43.419 · 93%** |
| materias (MARC 650) | **0%** | **38.020 · 81%** |
| subtítulo | ya resuelto por REST | 18.620 · 40% |
| resumen | 3% | 1.511 · 3% *(igual)* |

Lo que de verdad justifica la petición es el **TOC**: es la tabla de
contenidos del libro, capítulo a capítulo. Para *Redacción en relaciones
públicas*, hoy se indexa solo el título; por base de datos vendría con «Las
relaciones públicas. Conceptos y funciones — La redacción — … — La
comunicación interna — Las relaciones públicas financieras — …». Son 43.419
libros que pasarían de tener una línea de texto buscable a tener un párrafo.

### El adaptador ya está listo — no hace falta trabajo previo

Comprobado el 11-sep-2026 contra la base real:

- La consulta de cosecha del adaptador (`_HARVEST_SQL`) **funciona tal cual**:
  devuelve `toc`, `subjects`, `dewey`, `coauthors`, `place`, `publisher` y
  `copyrightdate`.
- **Los identificadores no cambian.** Las dos vías producen `koha:28277`, el
  mismo título compuesto y el mismo año. Cambiar de vía **actualiza** los
  documentos existentes; no duplica el catálogo ni obliga a reindexar de cero.
- Es **una sola base**, así que no hacen falta ni cosecha multi-base ni
  cambiar el formato del id.

Con el puerto abierto, lo único pendiente es poner `KOHA_DB_HOST`,
`KOHA_DB_NAME`, `KOHA_DB_USER` y `KOHA_DB_PASSWORD` en el `.env` de GUIA
(credenciales ya guardadas en `~/.secrets/koha-prod.env`) y lanzar una
cosecha.
