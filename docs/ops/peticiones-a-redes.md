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

## 2. Puerto 3306/TCP hacia la base de datos de Koha

**Qué pedir:** permitir `192.168.15.167 → 192.168.12.130 : 3306/TCP`.

**Lo importante: la ruta entre las dos subredes ya existe.** No hay que abrir
un camino nuevo, solo un puerto en uno que ya funciona. Medido desde el .167:

| destino | estado |
|---|---|
| `192.168.12.130:80` | **abierto** |
| `192.168.12.130:3306` | cerrado / timeout |
| `192.168.12.130:443` | cerrado / timeout |
| `192.168.12.135:22` | cerrado / timeout |

Las credenciales ya existen y funcionan (usuario `ticrai`, probado desde la
VPN): no hay que crear nada en el gestor de base de datos.

### Qué se gana, medido sobre 1.500 registros

GUIA cosecha hoy el catálogo por la **REST API**, que no expone parte de los
metadatos. La vía de base de datos da:

| campo | REST (hoy) | base de datos |
|---|---|---|
| tabla de contenidos (MARC 505) | **0%** | **99%** |
| materias (MARC 650) | **0%** | **72%** |
| resumen | 3% | 99% |
| año de publicación | 98% *(ya arreglado)* | 97% |
| editorial | 95% | 99% |

Lo que de verdad justifica la petición es el **TOC y las materias**: son texto
descriptivo del contenido, que es lo que alimenta la búsqueda semántica. Año y
subtítulo ya se resolvieron por REST el 11-sep, así que la urgencia bajó.

### Y algo que hay que hacer de nuestro lado antes

**Hay cuatro bibliotecas, no una**, y el adaptador solo sabe leer una base:

| base | registros |
|---|---|
| `koha_bul` (Lima) | 34.944 |
| `koha_buj` (Juliaca) | 9.512 |
| `koha_but` (Tarapoto) | 3.117 |
| `koha_cia` | 2.417 |
| **total** | **49.990** |

La REST las sirve todas (46.778 cosechados). Cambiar a la vía de base de datos
tal como está **perdería tres campus**. Así que el puerto no basta: hace falta
además que `sciback-adapter-koha` coseche varias bases. Pedir el puerto sin
ese trabajo no sirve de nada.
