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

## 2. Puerto 3306 hacia la base de Koha — EN ESPERA, el host estaba mal

**No pedir todavía.** La petición decía `192.168.12.130:3306`, y ese host
**no es la base del Koha que GUIA cosecha**. Comprobado el 11-sep-2026:

| evidencia | `koha_bul` en 192.168.12.130 | lo que sirve la REST / el OPAC |
|---|---|---|
| registros | 34.944, ids dispersos hasta 63.370 | ~46.681, ids densos desde 1 |
| biblionumber 12987 | «Diagnóstico normativo de los derechos sexuales» | «Introducción a la seguridad y salud en el trabajo» |
| biblionumber 28277 | no existe | «Contabilidad de costos : un enfoque gerencial» |

Son **catálogos distintos**. El secreto `koha-prod.env` tiene
`KOHA_PROD_DB_HOST=192.168.12.130` junto a
`KOHA_PROD_URL=https://biblioteca-staff.upeu.edu.pe`, y esas dos líneas no
apuntan al mismo sistema.

**Dónde está el Koha de producción:** `biblioteca-staff.upeu.edu.pe` y
`biblioteca.upeu.edu.pe` resuelven a **190.239.28.82** desde fuera y a
**192.168.12.199** por la VPN — el balanceador. Ahí están abiertos 22, 80 y
443, pero **no el 3306**, así que su base vive en otra máquina, detrás. Las
credenciales SSH del secreto (las del `.135`) no sirven en el `.199`.

### Antes de pedir nada hay que aclarar

1. **Qué es el Koha del `.130`**, con sus cuatro bases por campus
   (`koha_bul` 34.944, `koha_buj` 9.512, `koha_but` 3.117, `koha_cia` 2.417).
   ¿El sistema anterior a unificar el catálogo? ¿Otra unidad?
2. **Dónde está la base del Koha que sirve `biblioteca-staff`**, que es el que
   GUIA cosecha y el que ve el usuario en el OPAC.

Solo entonces tiene sentido pedir un puerto — y saber hacia dónde.

### Lo que ya sabemos que hará falta de nuestro lado

Si la base de producción resulta tener **varias bases por campus**, el
adaptador necesita dos cosas, no una:

- **Cosechar varias bases**, que hoy no sabe: `KohaSettings.db_name` es una.
- **Identificadores con la biblioteca dentro.** Los `biblionumber` se repiten
  entre campus: medido, **5.204 existen a la vez en Lima y Juliaca**, y son
  libros distintos. Con el id actual (`koha:28277`) se pisarían miles de
  registros y se mezclarían catálogos. Tendría que ser `koha:bul:28277`, lo
  que además cambia el enlace al OPAC de cada campus.

Ese cambio de identificador no es menor: reindexa el catálogo entero y rompe
los ids ya guardados.
