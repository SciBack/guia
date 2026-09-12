# Medir la recuperación antes de tocar un peso

`banco_de_consultas.py` son 14 consultas con **respuesta conocida**, cada una
verificada contra su fuente. Cubren los tres tipos que se comportan distinto:

- **léxico** — el usuario escribe palabras literales del título
- **semántico** — describe el tema con otras palabras
- **agregado** — pregunta por el conjunto, no por un documento

La mezcla importa: BM25 gana en los léxicos y la rama vectorial en los
semánticos, así que un peso medido solo con unos u otros miente.

```bash
docker exec guia-api-1 sh -c "cd /app && python /ruta/medir_pesos.py"
```

## Lo medido el 11-sep-2026

| pesos (bm25/knn) | MRR fusión | MRR final | R@5 final | léxico | semántico | agregado |
|---|---|---|---|---|---|---|
| 0,3 / 0,7 *(anterior)* | 0,506 | 0,583 | 71% | 0,64 | 0,33 | 0,78 |
| 0,4 / 0,6 | 0,510 | 0,583 | 71% | 0,64 | 0,33 | 0,78 |
| **0,5 / 0,5** | 0,546 | **0,786** | **86%** | 0,79 | 0,83 | 0,72 |
| 0,6 / 0,4 | 0,543 | 0,702 | 79% | 0,79 | 0,83 | 0,33 |
| 0,7 / 0,3 | 0,597 | 0,702 | 79% | 0,79 | 0,83 | 0,33 |

**La trampa está en la primera columna.** El MRR de la fusión sube
monótonamente con el peso léxico —0,506 → 0,597— y aun así el resultado final
empeora a partir de 0,5: las preguntas agregadas se desploman de 0,78 a 0,33.
Quien optimice la fusión sin mirar lo que queda tras el reranking elegirá 0,7
y empeorará el producto.

Detalle del cambio 0,3/0,7 → 0,5/0,5, caso por caso: **cuatro documentos que
no aparecían en absoluto pasan al primer puesto** (un proceso del SGC, una
tesis de lixiviados, un evento y el organigrama) y **uno baja del 1 al 6**
(«cómo está organizada la UPeU»), sin salirse de la vista.

## Dos cosas que este banco no mide

- **Es pequeño.** 14 casos dan señal, no precisión estadística. Un cambio de
  dos o tres centésimas en el MRR no significa nada aquí.
- **Mide recuperación, no redacción.** Que el documento salga primero no
  garantiza que la respuesta lo use bien.

## Hallazgo aparte

`koha:28277` se indexa como «Contabilidad de costos» cuando el OPAC dice
«Contabilidad de costos : un enfoque gerencial». **El subtítulo de Koha no se
cosecha**, así que buscarlo por el título completo no lo encuentra. No afecta
a esta comparación —falla igual con todos los pesos— pero es real.

## Segunda medición, 11-sep-2026 — tras arreglar Koha

Repetida después de recosechar el catálogo con el **título compuesto** (con su
subtítulo) y el **año real** en vez de la fecha de catalogación:

| pesos (bm25/knn) | MRR fusión | MRR final | R@5 final | léxico | semántico | agregado |
|---|---|---|---|---|---|---|
| 0,3 / 0,7 | 0,519 | 0,583 | 71% | 0,69 | 0,58 | 0,33 |
| 0,4 / 0,6 | 0,357 | 0,464 | 64% | 0,40 | 0,33 | 0,78 |
| **0,5 / 0,5** *(configurado)* | 0,483 | **0,772** | **93%** | 0,83 | 0,83 | 0,55 |
| 0,6 / 0,4 | 0,473 | 0,738 | 86% | 0,86 | 0,83 | 0,33 |
| 0,7 / 0,3 | 0,529 | 0,738 | 86% | 0,86 | 0,83 | 0,33 |

**El recall sube del 86% al 93%**: 13 de los 14 casos tienen su documento en
los cinco primeros. Lo gana «Contabilidad de costos un enfoque gerencial», que
**no aparecía con ninguna configuración** —su título estaba indexado sin el
subtítulo— y ahora sale en el puesto 2. El único que se queda fuera es «cómo
está organizada la UPeU», en el 7.

El MRR final baja tres milésimas (0,786 → 0,772). **Eso no significa nada
aquí**: con 14 casos, cada uno pesa 0,07, y los tres agregados hacen saltar su
columna entre 0,33 y 0,78 según qué posición cambie. La conclusión firme es la
que se repite en las dos medidas: 0,5/0,5 gana, y las dos columnas de la
izquierda siguen sin predecir la de la derecha.

## Tercera medición, 11-sep-2026 — con el TOC y las materias del MARC

Tras recosechar el catálogo trayendo la tabla de contenidos (MARC 505) y las
materias (650) por la REST. El índice pasó de **1.512 registros con resumen
(3%)** a **46.678 (100%)**, y de **0 materias** a **36.398 (78%)**.

| pesos (bm25/knn) | MRR fusión | MRR final | R@5 | léxico | semántico | agregado |
|---|---|---|---|---|---|---|
| 0,3 / 0,7 | 0,659 | 0,738 | 93% | 0,81 | 0,58 | 0,78 |
| 0,4 / 0,6 | 0,659 | 0,738 | 93% | 0,81 | 0,58 | 0,78 |
| **0,5 / 0,5** *(configurado)* | 0,639 | 0,757 | 93% | 0,81 | 0,83 | 0,53 |
| 0,6 / 0,4 | 0,635 | **0,798** | 93% | 0,83 | 0,83 | 0,67 |
| 0,7 / 0,3 | 0,641 | **0,798** | 93% | 0,83 | 0,83 | 0,67 |

**Lo que de verdad cambió es la primera columna.** El MRR de la fusión sube de
~0,48-0,52 a ~0,64: los documentos correctos llegan mucho mejor situados a la
fase de reranking, que es lo que se esperaba de darle a cada libro un párrafo
de texto descriptivo en vez de solo un título.

**Y el recall deja de discriminar**: 93% en las cinco configuraciones. El
banco ya no distingue entre pesos por esa métrica — señal de que se quedó
corto, no de que todos los pesos sean iguales.

### Sobre cambiar a 0,6/0,4

Mide mejor (0,798 frente a 0,757) y ya no hunde las preguntas agregadas, que
era lo que lo descartaba en la primera medición. Pero **con 14 casos, un solo
documento que pase del puesto 3 al 1 mueve el MRR 0,048**: la diferencia
observada cabe entera dentro de un caso. No es motivo suficiente para cambiar
un peso en producción.

Lo honesto es anotar la tendencia —en las tres medidas del día, más peso
léxico ha ido saliendo mejor a medida que el índice ganaba texto— y **ampliar
el banco antes de decidir**. Treinta o cuarenta casos darían una señal que
14 no dan.

---

## Cuarta medición, 11-sep-2026 — con el banco ampliado a 40 casos

**Y aquí el banco de 14 resultó estar mintiendo.** Tenía 7 consultas léxicas y
solo 4 semánticas; el de 40 tiene 18 y 19. Con esa mezcla, el resultado se da
la vuelta:

| pesos (bm25/knn) | MRR fusión | MRR final | R@5 | léxico | semántico | agregado |
|---|---|---|---|---|---|---|
| **0,3 / 0,7** *(revertido a esto)* | 0,562 | **0,792** | **88%** | 0,89 | **0,70** | 0,78 |
| 0,4 / 0,6 | 0,561 | 0,792 | 88% | 0,89 | 0,70 | 0,78 |
| 0,5 / 0,5 | 0,559 | 0,749 | 82% | 0,89 | 0,65 | 0,54 |
| 0,6 / 0,4 | 0,536 | 0,613 | 68% | 0,90 | 0,39 | 0,33 |
| 0,7 / 0,3 | 0,539 | 0,613 | 68% | 0,90 | 0,39 | 0,33 |

Las consultas léxicas puntúan **0,89–0,90 con cualquier peso**: entre el
título con subtítulo y el índice de capítulos, ya no discriminan nada. Quien
decide son las semánticas, y ahí la rama vectorial manda — 0,70 con 0,3
frente a 0,39 con 0,6.

Solo **5 de los 40 casos** cambian de resultado entre 0,3/0,7 y 0,5/0,5, pero
el balance es claro: con 0,5 había dos consultas descritas con palabras
propias que **no aparecían en absoluto** y con 0,3 salen las primeras.

| consulta | tipo | 0,3/0,7 | 0,5/0,5 |
|---|---|---|---|
| cómo perciben los vecinos la atención que reciben en su municipio | semántico | **1** | — |
| relación entre el agobio de los estudios y la confianza del alumno | semántico | **1** | — |
| cómo está organizada la UPeU | agregado | **1** | 9 |
| organigrama de la universidad | agregado | 3 | **2** |
| cultura de prevención frente a fenómenos naturales | semántico | — | **1** |

### La lección, que no es el número

`search_peso_lexico` volvió a **0,3**, donde estaba. El cambio a 0,5 duró unas
horas y se hizo *midiendo* — no a ojo—, con una diferencia que parecía
holgada (0,583 → 0,786), no marginal. El error no fue confiar en la medida:
fue **medir con un banco que no representaba las consultas reales**.

Al ampliarlo, dos cosas que conviene recordar antes de la próxima:

- **La composición importa más que el tamaño.** Lo que rompió la medición no
  fue tener 14 casos, fue tener 4 semánticas de 14 cuando la mitad de lo que
  la gente pregunta se describe con palabras propias.
- **Al redactar los casos semánticos, no reusar palabras del título.** Si no,
  se mide recuperación léxica disfrazada, que es justo lo que hace que el peso
  léxico parezca mejor de lo que es.

---

## Lo que el banco NO mide, y por qué el 88% es un suelo

Al investigar los 5 casos que quedaban fuera del top-5 —todos semánticos— se
probaron dos hipótesis y **las dos resultaron falsas**. Merece la pena dejar
escrito el recorrido, porque el final cambia cómo hay que leer la métrica.

**Hipótesis 1: el índice de capítulos desplaza a las materias del embedding.**
Falsa por dos motivos, medidos: reordenar el texto (materias antes del TOC) no
mejora la similitud —0,8134 → 0,8132— y, sobre todo, **las materias nunca se
truncaban**: los textos caben de sobra en los 1.500 caracteres.

**Hipótesis 2: el documento entra en la ventana de candidatos pero el
reranking lo hunde.** Falsa: ampliando la ventana de 50 a 150 y a 300
candidatos, ninguno de los cinco aparece.

**Lo que pasa de verdad.** Para «cómo trabajar el movimiento corporal con
chicos de secundaria», el documento marcado como correcto puntúa 0,81 y los
que salen puntúan 0,92:

```
0,9232  Cómo integrar a niños con necesidades especiales al salón
0,9171  Actividades Psicomotrices Básicas y Trabajos con Elementos
0,9156  Fantasía en movimiento : cuaderno de trabajo
```

Y esos libros **son buenas respuestas a esa pregunta**. El banco los cuenta
como fallo porque exige *un documento concreto*, cuando la pregunta real que
hace un usuario admite varios. La métrica está midiendo «¿sale el que yo
elegí?» en lugar de «¿sale algo útil?».

### Consecuencias prácticas

- **El 88% es un suelo, no el techo.** Parte de los fallos son aciertos que la
  métrica no reconoce.
- **Los casos léxicos siguen siendo fiables**: ahí solo hay un documento
  correcto y el título lo identifica sin ambigüedad.
- Para medir bien lo semántico haría falta que cada caso acepte **un conjunto**
  de documentos válidos, no uno solo. Eso es rehacer el banco con criterio de
  relevancia, no de identidad — más trabajo, y con un punto de juicio que
  conviene que revise una persona.

### Y una advertencia de método

Antes de cambiar nada por una hipótesis, **medirla**. Las dos de arriba
parecían razonables y habrían costado tres horas de recosecha cada una para
descubrir que no servían. Comprobarlas costó dos consultas de similitud y una
tabla de posiciones.

---

## Revisión de los 19 casos semánticos, 12-sep-2026

Se examinó qué devuelve GUIA en cada uno de los 5 que quedaban fuera del
top-5, para separar el fallo de recuperación del defecto de la métrica.
**De los cinco, uno era un bug del índice y tres son aciertos.**

| caso | veredicto | por qué |
|---|---|---|
| movimiento corporal en secundaria | **acierto parcial** | salen *Desarrollo de habilidades sociales en el curso de educación física* y *Ejercicios de educación física*: sirven |
| letras de cambio y pagarés | **fallo real** | sale contabilidad general; ningún libro de títulos valores |
| valoración de empresas | **acierto** | los cuatro son de finanzas — *la decisión de inversión*, *Finanzas para directivos*, *Principios de finanzas corporativas*— y algunos mejores que el marcado |
| SUNAT y bienes no declarados | **acierto** | el tercero es *Análisis de criterios de detección del incremento patrimonial no justificado*: el mismo tema que el marcado |
| cultura de prevención | **bug, ya corregido** | el evento estaba **duplicado**; ver abajo |

### El bug que apareció revisando

El evento «Cultura de prevención y resiliencia» era **el primero en BM25 con
26,9 frente a 11,1 del siguiente** y no salía en el top-5. La causa no era el
ranking: el evento estaba indexado **dos veces**, con dos ids distintos
apuntando a la misma URL, y las dos copias se repartían la señal.

Origen: los eventos usaban `event.id`, un UUIDv7 que el dominio genera **en el
constructor**, así que cada cosecha creaba un documento nuevo. Es el mismo
fallo que `_stable_pub_id` arregló para las publicaciones y que había quedado
vivo aquí. **50 de los 102 documentos de Indico eran duplicados.**

Corregido: el id sale del número de evento de la URL (`/event/359/` →
`indico:event:359`). Duplicados por URL tras la limpieza: **0**.

### Dónde queda la medición

| | R@5 | semánticas |
|---|---|---|
| antes de la revisión | 88% | 0,70 |
| con los ids de Indico estables | **90%** | **0,72** |
| contando los tres aciertos que la métrica no reconoce | **~97%** | — |

Por fuente: CRIS 6/6 · OJS 6/6 · SGC 8/8 · Indico 3/3 · DSpace 6/7 · **Koha
7/10**.

**Queda un fallo genuino**: «letras de cambio, pagarés y documentos
bancarios» no encuentra *Documentación Mercantil*. Es vocabulario
especializado —títulos valores— donde ni el título ni el índice de capítulos
del libro usan esas palabras, y las materias del registro son genéricas
(«Documentos comerciales»). No tiene arreglo por configuración.
