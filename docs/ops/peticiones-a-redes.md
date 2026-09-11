# Lo que GUIA necesita de Redes

**Queda una sola petición viva: el registro DNS.** La segunda se redactó y se
retiró el mismo día, al descubrir que lo que pedía ya estaba disponible por
otra vía; se deja escrita porque el razonamiento que llevó a ella es útil de
recordar.

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

## 2. Puerto 3306 hacia Koha — RETIRADA, no hacía falta

**No pedir.** Se llegó a redactar y era innecesaria.

El razonamiento que la motivó tenía un agujero: se comprobó que el JSON de
`/api/v1/biblios` no trae la tabla de contenidos (MARC 505) ni las materias
(650), y de ahí se saltó a "hace falta la base de datos". No se probó **el
mismo endpoint pidiendo MARC**, que sí los trae:

```
GET /api/v1/biblios?_page=0&_per_page=100
Accept: application/marc-in-json          → 200 en 0,33 s
```

Es el listado paginado, no registro a registro: **dos peticiones por página**
en vez de una, 936 en total sobre el catálogo. Ya está implementado y
cosechado.

Medido contra el Koha real, sobre 300 registros: **98% con tabla de
contenidos y 82% con materias**, donde antes se indexaba el 0% de ambas.

### Lo que queda por saber, aunque ya no bloquea nada

`KOHA_PROD_DB_HOST` apuntaba a `192.168.12.130` / `koha_bul`, que es **otro
Koha** — allí el biblionumber 12987 es un libro distinto y el 28277 no existe.
Tiene cuatro bases por campus (Lima 34.944, Juliaca 9.512, Tarapoto 3.117,
CIA 2.417). El de producción es `192.168.12.136` / `koha_upeu`, con 46.678
registros, que es lo que GUIA indexa. El secreto ya está corregido.

Queda la duda de **qué es el Koha del `.130`**: si guarda material que no está
en el catálogo unificado, sería una fuente adicional a cosechar. Si es el
sistema anterior, no hay nada que hacer.
