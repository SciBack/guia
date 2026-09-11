# Qué ve cada quien, según el IGA

Desde el **11-sep-2026** el nivel de acceso de GUIA lo gobierna MidPoint, a
través de la sesión de Keycloak. Antes era implícito —hay correo de sesión o
no lo hay— y solo se consultaba dentro del camino personal: fuera de ahí, un
Analista Programador de la DTI y un visitante anónimo recibían exactamente la
misma respuesta.

## Los tres niveles

| Nivel | Quién | Qué abre |
|---|---|---|
| `publico` | Sin sesión | Catálogo, repositorio, producción científica, revistas, eventos y el mapa de áreas y procesos. Ningún dato personal |
| `comunidad` | Estudiante con sesión | Lo anterior + sus propias clases, horario y ficha |
| `personal` | Trabajador con sesión | Lo anterior + su ficha laboral y el contexto de su área |

Se publican en `/api/transparency` bajo `access_levels`. Un nivel de acceso
que solo existe dentro del código no es gobernanza: nadie de fuera puede
comprobarlo.

## El límite que ningún nivel levanta

**En ningún nivel se revelan datos de terceros.** No es una promesa del
prompt: `de_quien_ha_iniciado_sesion` no acepta un identificador ajeno, así
que no hay nada que pedirle, y `derivar_acceso` solo mira el correo de la
sesión — pasarle una ficha sin correo verificado da nivel público, no acceso.

Subir de nivel da acceso a **lo tuyo**, nunca a lo de otro.

Y el canal: `identidad_verificada` **solo la puebla Chainlit** desde la sesión
autenticada. La API HTTP no la acepta en el cuerpo, precisamente para que
nadie pueda suplantar a otro mandándola. Al probar por `POST /api/chat` se
responde siempre como anónimo — no es un fallo, es la protección funcionando.

## Contexto y caché: por qué la decisión es una lista

Cuando la consulta pregunta por el propio sitio en la institución —"mi área",
"a quién le pido"—, el prompt recibe quién pregunta: su cargo, su unidad, su
campus. Con eso, "de qué responde mi área" se contesta de verdad.

**Una respuesta así no puede entrar en la caché.** La caché es semántica y
global: no distingue por usuario, así que una respuesta que dice "tu área, la
DTI" servida a la siguiente persona que preguntara algo parecido sería una
fuga. Los cuatro puntos de escritura están cerrados para estas respuestas.

Por eso `aporta_contexto` decide con una lista de patrones y no con el
modelo: de esa decisión depende que la respuesta de una persona no se sirva a
otra, y una lista se lee, se prueba y no cambia de opinión entre dos
peticiones idénticas.

## Dónde se enlazan el IGA y el mapa institucional

MidPoint devuelve la unidad como **la misma cadena** con la que el SGC nombra
al propietario de un proceso:

```
MidPoint  unidades = ("Dirección de Tecnologías de Información",)
SGC       S04 Gestión tecnológica → propietario DTI → "Dirección de Tecnologías de Información"
```

Ese es todo el pegamento. Comprobado end-to-end: con sesión, "de qué responde
mi área" contesta con los procesos de la familia DTI (S04 y sus siete
subprocesos, repartidos entre DTI, DTI-INFRA, DTI-DEV, DTI-MESA y DTI-RSL);
sin sesión, pide iniciar sesión y no filtra nada.

## Coste

La ficha se cachea por correo con TTL de 15 minutos. Antes se pedía una vez de
cada muchas consultas; ahora el nivel se deriva en todos los mensajes, y sin
caché eso serían cientos de milisegundos de MidPoint por mensaje. Lo que
cambia de una persona —cargo, unidad, campus— cambia en semanas.

Dentro de una misma petición la ficha se pide **una sola vez**: viaja dentro
de `QuienPregunta` y el camino personal la reutiliza.

## Pendiente

El contexto le dice al modelo *cuál* es el área del usuario, pero los procesos
concretos los tiene que recuperar la búsqueda. Sería más preciso inyectar
directamente los procesos de esa área, leídos del mapa, en vez de confiar en
que el ranking los traiga.
