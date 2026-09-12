"""Banco de consultas con respuesta conocida, para medir la recuperación.

Cada caso es una consulta y el documento que DEBE salir, verificado contra su
fuente. Se cubren los tres tipos que se comportan distinto:

  lexico    — el usuario escribe palabras literales del título, como quien
              copia de una bibliografía
  semantico — describe el tema con OTRAS palabras; deliberadamente no se
              reusan las del título, porque si no se mide recuperación léxica
              disfrazada de semántica
  agregado  — pregunta por el conjunto, no por un documento

Esa mezcla importa: la rama BM25 gana en los léxicos y la vectorial en los
semánticos, así que un peso medido solo con unos u otros miente.

Ampliado a 40 casos el 11-sep-2026. Con 14 el recall se quedó en 93% para las
cinco configuraciones de peso probadas — dejó de discriminar, que no es lo
mismo que decir que los pesos den igual. Los documentos se eligieron por
muestreo aleatorio de cada fuente, no buscando los que fueran a acertar.

Reparto: koha 10 · dspace 7 · cris 6 · ojs 6 · indico 3 · sgc 8.
"""

BANCO = [
    # ══ SGC — el mapa institucional ═══════════════════════════════════════
    ("que areas tiene la universidad",        "sgc:mapa",                    "agregado"),
    ("como esta organizada la upeu",          "sgc:mapa",                    "agregado"),
    ("organigrama de la universidad",         "sgc:mapa",                    "agregado"),
    ("que servicios ofrece la DTI",           "sgc:area:DTI",                "lexico"),
    ("de que se encarga la direccion de investigacion e innovacion",
                                              "sgc:area:DIR-INVESTIGACION-E-INNOVACION", "lexico"),
    ("quien es responsable del proceso de matricula", "sgc:proceso:C02",     "semantico"),
    ("gestion tecnologica proceso de soporte","sgc:proceso:S04",             "lexico"),
    ("que se hace cuando un alumno termina la carrera y quiere su titulo",
                                              "sgc:proceso:C08",             "semantico"),

    # ══ Koha — el catálogo ════════════════════════════════════════════════
    ("Introduccion a la seguridad y salud en el trabajo", "koha:12987",      "lexico"),
    ("Contabilidad de costos un enfoque gerencial",       "koha:28277",      "lexico"),
    ("Documentacion mercantil teoria y practica",         "koha:21901",      "lexico"),
    ("Fundamentos de administracion financiera",          "koha:38754",      "lexico"),
    ("Teoria unificada de estructuras y cimientos",       "koha:42096",      "lexico"),
    # semánticos: el tema, sin las palabras del título
    ("como trabajar el movimiento corporal con chicos de secundaria",
                                                          "koha:15171",      "semantico"),
    ("libro sobre letras de cambio pagares y documentos bancarios",
                                                          "koha:21901",      "semantico"),
    ("analisis elastico de vigas y columnas de acero y hormigon",
                                                          "koha:42096",      "semantico"),
    ("valoracion de empresas y decisiones de inversion para gerentes",
                                                          "koha:38754",      "semantico"),
    ("planificacion de ciudades capitales y su dimension espiritual",
                                                          "koha:14231",      "semantico"),

    # ══ DSpace — tesis y trabajos ═════════════════════════════════════════
    ("Estilos de crianza familiar y rendimiento academico",
     "oai:repositorio.upeu.edu.pe:20.500.12840/309",                         "lexico"),
    ("Relacion entre riesgo de fraude cultura organizacional y compromiso",
     "oai:repositorio.upeu.edu.pe:20.500.12840/4409",                        "lexico"),
    ("habitos alimentarios y estres en universitarios",
     "oai:repositorio.upeu.edu.pe:20.500.12840/1943",                        "semantico"),
    ("remocion de contaminantes en lixiviados de relleno sanitario",
     "oai:repositorio.upeu.edu.pe:20.500.12840/1942",                        "semantico"),
    ("cuando la sunat detecta bienes que no cuadran con lo declarado",
     "oai:repositorio.upeu.edu.pe:20.500.12840/5801",                        "semantico"),
    ("como perciben los vecinos la atencion que reciben en su municipio",
     "oai:repositorio.upeu.edu.pe:20.500.12840/10251",                       "semantico"),
    ("experiencias de mayordomia en el distrito misionero de cajamarca",
     "oai:repositorio.upeu.edu.pe:20.500.12840/6582",                        "lexico"),

    # ══ CRIS — producción científica ══════════════════════════════════════
    ("Argopecten purpuratus mitochondrial genome",
     "oai:cris.upeu.edu.pe:123456789/1767",                                  "lexico"),
    ("Efficacy of CPAP in neonates with meconium aspiration syndrome",
     "oai:cris.upeu.edu.pe:123456789/1191",                                  "lexico"),
    ("tambos of the peruvian rural territory systematic catalog",
     "oai:cris.upeu.edu.pe:123456789/649",                                   "lexico"),
    ("presion positiva continua en recien nacidos que aspiraron meconio",
     "oai:cris.upeu.edu.pe:123456789/1191",                                  "semantico"),
    ("que espera un turista del servicio de mototaxi en tarapoto",
     "oai:cris.upeu.edu.pe:123456789/256",                                   "semantico"),
    ("infecciones de transmision sexual en trabajadores sexuales LGBT",
     "oai:cris.upeu.edu.pe:123456789/576",                                   "semantico"),

    # ══ OJS — revistas ════════════════════════════════════════════════════
    ("uso del internet y vida devocional en jovenes adventistas",
     "oai:ojs.pkp.sfu.ca:article/1038",                                      "lexico"),
    ("Estimacion de la huella ecologica en instituciones educativas",
     "oai:ojs.pkp.sfu.ca:article/714",                                       "lexico"),
    ("identidad de los maskilim en el libro de Daniel",
     "oai:ojs.pkp.sfu.ca:article/2115",                                      "lexico"),
    ("relacion entre el agobio de los estudios y la confianza del alumno en si mismo",
     "oai:ojs.pkp.sfu.ca:article/1694",                                      "semantico"),
    ("que dice la Biblia sobre consultar a los difuntos, Saul y el profeta",
     "oai:ojs.pkp.sfu.ca:article/2123",                                      "semantico"),
    ("modelo de calidad EFQM aplicado a la responsabilidad social de una universidad",
     "oai:ojs.pkp.sfu.ca:article/760",                                       "semantico"),

    # ══ Indico — eventos ══════════════════════════════════════════════════
    ("cultura de prevencion frente a fenomenos naturales",
     "indico:event:359",                    "semantico"),
    ("OneVoice27 mision para todos",
     "indico:event:360",                    "lexico"),
    ("lanzamiento con el pastor Daniel Moltalvan en septiembre",
     "indico:event:360",                    "semantico"),
]

