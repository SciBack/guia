# Las fuentes que GUIA cosecha, y a dónde llevan sus enlaces

Estado al **11-sep-2026**, medido sobre el índice de producción.

| Fuente | Etiqueta | Documentos | Vía |
|---|---|---|---|
| Catálogo de la biblioteca | `koha` | 34.971 | REST API de Koha |
| Repositorio institucional (tesis) | `dspace` | 10.443 | OAI-PMH |
| **Producción científica (CRIS)** | **`cris`** | **1.996** | **OAI-PMH** |
| **Mapa institucional (SGC)** | **`sgc`** | **148** | **REST de Frappe** |
| Revistas | `ojs` | 744 | OAI-PMH |
| Eventos | `indico` | 102 | Export API |

ALICIA tiene cosechador, pero no está conectado en UPeU.

## Por qué el CRIS es una fuente aparte y no "más DSpace"

Es el mismo adaptador con otra URL base, y aun así se etiqueta distinto. La
razón no es de catalogación: **la etiqueta decide a qué buscador enlaza un
resultado cuando el usuario quiere ver más**. Mandar a alguien a buscar un
artículo científico en el repositorio de tesis es mandarlo a un sitio donde no
está.

Detalle de implementación que conviene no olvidar: `DSpaceSettings` lee el
prefijo `DSPACE_` del entorno, y ese prefijo ya lo ocupa el repositorio
institucional. Por eso el adaptador del CRIS se construye pasándole los valores
como argumentos y con `_env_file=None`; si se dejara leer el entorno, las dos
instancias apuntarían al mismo sitio.

## Configuración

```
DSPACE_CRIS_BASE_URL=https://cris.upeu.edu.pe
DSPACE_CRIS_OAI_URL=https://cris.upeu.edu.pe/server/oai/request
```

La segunda se puede omitir: se deriva de la primera añadiendo
`/server/oai/request`, que es donde la pone DSpace 7.

```bash
python -m guia harvest --source cris
```

## Lo que el CRIS NO expone por OAI

El repositorio tiene **2.791 items**, pero su OAI publica **1.996**. No es un
fallo: el filtro por defecto deja pasar solo las entidades `Publication`. Fuera
quedan, a propósito, las entidades CERIF:

| Entidad | Items |
|---|---|
| Person (investigadores) | 557 |
| OrgUnit | 221 |
| Funding | 9 |
| Patent | 6 |
| Project | 2 |

Indexarlas serviría para preguntas del tipo "¿quién investiga en X?", pero no
son publicaciones y el mapper actual las deformaría. Si algún día se quiere,
la vía es el contexto `openairecris` del propio OAI, no ensanchar el filtro por
defecto.

## La trampa del enlace: identificadores ajenos en `dc:identifier`

**Este es el motivo por el que un resultado puede llevar a otra cosa.** En
OAI-DC todos los identificadores caen en el mismo campo, sin distinguir los
propios de los ajenos. El primer registro del CRIS trae ocho:

```
1940-1736                                        ← ISSN
1940-1744                                        ← ISSN-e
https://pubmed.ncbi.nlm.nih.gov/24397768         ← PubMed
https://eprints.lib.hokudai.ac.jp/.../Manuscript.pdf
http://hdl.handle.net/2115/60439                 ← handle DE HOKKAIDO
10.3109/19401736.2013.845760                     ← DOI
https://cris.upeu.edu.pe/handle/123456789/1767   ← el bueno, el séptimo
W2106294476                                      ← OpenAlex
```

El enlace se derivaba del primer handle, que es el ajeno: abrir un resultado de
UPeU aterrizaba en el repositorio de la Universidad de Hokkaido. Corregido en
`sciback-adapter-dspace` eligiendo **por host** —solo vale una URL servida por
el mismo sitio que entregó el registro— y, si no hay ninguna, reconstruyéndola
desde el identificador OAI, que el protocolo obliga a tener.

Conviene distinguirlo del fallo de Koha del mismo día, que se le parece desde
fuera —"el listado dice una cosa y el enlace otra"— pero tenía otra causa: allí
el identificador del documento era la *posición* en la cosecha, no el
`biblionumber`.

## El índice OAI del CRIS se puebla a mano

DSpace 7 sirve el OAI desde su propio core de Solr, que **no se actualiza
solo**. Si un artículo nuevo no aparece en la cosecha, casi siempre es eso:

```bash
sudo -u dspace /opt/dspace/bin/dspace oai import
```

Sin `-c` es incremental; con `-c` limpia y reconstruye (2.793 items en 30 s,
medido el 11-sep-2026). Merece un cron en el servidor del CRIS: mientras no lo
tenga, GUIA cosechará lo que hubiera en el último import.

## Los títulos del CRIS llegan doblemente escapados

`&amp;lt;i&amp;gt;Argopecten purpuratus&amp;lt;/i&amp;gt;` — el dato entró ya
escapado y OAI lo volvió a escapar al serializar. Mostrado tal cual, el usuario
lee las entidades en medio de la frase. El adaptador lo desescapa hasta punto
fijo y quita las etiquetas de énfasis. Es una limpieza defensiva: el dato sucio
sigue estando en el CRIS.

## Cosechar no es publicar: el reindex es obligatorio

`harvest` escribe **solo en pgvector**. El buscador lee de **OpenSearch**, y
OpenSearch se llena con un paso aparte:

```bash
python -m guia reindex --target opensearch --source cris
```

Es fácil no darse cuenta, porque la cosecha termina diciendo «Cosecha
completada» con 0 errores y todo parece hecho. El 11-sep-2026 una recosecha
entera de Koha —46.778 registros, 0 errores— dejó el índice de búsqueda
exactamente igual que antes: los usuarios habrían seguido viendo los mismos
enlaces rotos.

**Regla: después de cada `harvest`, un `reindex --source <fuente>`.** Y si la
cosecha reemplaza documentos en vez de añadirlos, hay que borrar los viejos en
las dos capas, porque el reindex añade pero no retira lo que sobra.

### Cómo se separan los documentos viejos de los nuevos

`sciback_vectors` tiene `updated_at`, y un upsert lo actualiza. Eso basta: lo
que la cosecha tocó lleva la fecha de hoy, y lo que no tocó es lo que quedó
huérfano.

```sql
DELETE FROM sciback_vectors
WHERE metadata->>'source' = 'koha' AND updated_at < '2026-09-11';
```

Es más fiable que marcar los documentos antes de cosechar, que fue el primer
intento: la marca se puso en OpenSearch y allí no sirve para limpiar pgvector.

Y es seguro por construcción: si un documento viejo tenía ya el identificador
correcto, la cosecha lo actualizó —fecha de hoy— y no entra en el borrado.
Comprobado antes de ejecutarlo: de los 12.369 que iban a caer, ninguno de la
muestra existía en el OPAC. Eran posiciones de cosecha, no `biblionumber`.

## El mapa institucional, y lo que todavía no recupera bien

Desde el 11-sep-2026 GUIA indexa el mapa de procesos del SGC: **51 áreas y 96
procesos**, más un documento con el mapa entero. Con eso responde bien "¿qué
servicios ofrece la DTI?" y "¿quién responde del proceso de matrícula?" —
antes las clasificaba como *fuera de alcance*.

**Lo que la fuente no da todavía**, y conviene no prometerlo: 70 de los 96
procesos no tienen área propietaria asignada, ninguno tiene responsable, y los
96 están en `Borrador` porque las fichas SIPOC no se han entregado. Sirve para
"de qué responde un área", no para "dónde tramito mi constancia". Cada
documento viaja con su estado y el prompt obliga a decirlo.

### La pregunta agregada: por qué fallaba, y no era el reranker

`¿qué áreas tiene la universidad?` no recuperaba el mapa. La sospecha inicial
—que lo hundía el reranking— **era falsa**, y medirlo lo dejó claro:

| | posición de `sgc:mapa` |
|---|---|
| BM25 puro | **1** |
| tras la fusión híbrida | **51 de 98** |

Entraba hundido. La causa estaba en la cosecha: el resumen del mapa son
**2.701 caracteres** y se usaba *también* como texto de embedding, cuando E5
admite unos 1.500. La frase que responde a la pregunta quedaba ahogada entre
cincuenta nombres de direcciones, y con la rama vectorial pesando 0,7 frente
a 0,3 del léxico, ganar en BM25 no bastaba.

Es la separación que el harvester ya tenía y que `harvest_sgc` se saltó
(ADR-037: capa A *lossy* para el vector, capa B *lossless* para leer). Ahora
cada objeto tiene `texto_para_buscar()` —corto y en los términos en que la
gente pregunta— aparte de `como_texto()` / `resumen()`, que siguen completos
en la metadata.

**El reranker, medido después, juega a favor en los tres casos:**

| consulta | tras la fusión | tras el reranker |
|---|---|---|
| «qué áreas tiene la universidad» | 1 | **1** |
| «cómo está organizada la UPeU» | 6 | **1** |
| «organigrama de la universidad» | 12 | **3** |

Un apunte para no confundirse al mirar una respuesta: el listado que ve el
usuario **agrupa por fuente**, no por score. Que un libro de Koha aparezca
arriba del listado no significa que haya ganado el ranking.

### DNS: `calidad.upeu.edu.pe` no resuelve dentro

El `.167` resuelve contra los DNS internos `192.168.13.96/.97`, autoritativos
para `upeu.edu.pe`, y **no tienen el registro `calidad`** — el DNS público sí
(3.18.90.66), y el servidor alcanza esa IP sin problema. Mientras Redes no lo
publique, el `docker-compose.upeu.yml` lleva un `extra_hosts`. Es una Elastic
IP, así que no baila; quitarlo cuando el registro exista.

## La actualización diaria

`ops/cron/actualizacion-diaria.sh`, a las 03:40 (`/etc/cron.d/guia-diario`):
cosecha el SGC, **lo publica en OpenSearch** y recuenta el índice. Los tres
pasos, en ese orden. Las fuentes grandes no se tocan ahí: son horas y cambian
despacio.

El recuento va por `POST /api/transparency/recalcular`, cerrado a `127.0.0.1`
— y el `curl` corre **dentro del contenedor**, porque desde el host la
petición llega con la IP de la gateway de Docker y responde 404.

> Al escribir el `/etc/cron.d`: una asignación vacía (`VAR=`) hace que cron
> **descarte el archivo entero**, en silencio y sin dejar nada en syslog. Eso
> tuvo al CRIS dos meses y medio sin ejecutar ni el mantenimiento ni los
> backups. Si una variable va vacía, entrecomíllala: `VAR=""`.

## Koha: el título se indexa con su subtítulo

En MARC 245 el título (`$a`) y el subtítulo (`$b`) son campos distintos, y
Koha los devuelve separados con su puntuación ISBD:

```
title:    "Contabilidad de costos :"
subtitle: "un enfoque gerencial /"
```

Se indexaba solo el primero. Consecuencia: buscar el libro **por el nombre
con el que aparece en el OPAC** no lo encontraba. Medido el 11-sep-2026 sobre
una muestra de 1.200 registros, **el 30% tiene subtítulo** — unos 14.000 de
los 46.778 del catálogo.

Guardarlo aparte no bastaba, y conviene entender por qué antes de proponerlo
otra vez: ya viajaba en `extra["subtitle"]`, se perdía antes de llegar al
índice de búsqueda, y aunque hubiera llegado, la consulta BM25 solo mira
`title^2` y `abstract`. Componerlo lo pone donde de verdad se busca, entra en
el embedding y deja el título igual que en el OPAC.

La vía de base de datos tenía además su propio fallo: anteponía el subtítulo
al resumen «para mejorar la búsqueda semántica», lo que solo funcionaba si el
registro traía TOC o abstract — sin ellos el subtítulo se perdía igual.

> Los identificadores son estables (`koha:<biblionumber>`), así que la
> recosecha **actualiza** los registros existentes. No hay que borrar nada
> después, a diferencia de la recosecha del 11-sep que arregló los ids.
