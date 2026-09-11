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
