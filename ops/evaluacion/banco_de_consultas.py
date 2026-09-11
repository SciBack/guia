"""Banco de consultas con respuesta conocida, para comparar pesos de fusión.

Cada caso es una consulta real y el documento que DEBE salir, verificado
contra la fuente. Se cubren los tres tipos que se comportan distinto:

  lexico    — el usuario escribe palabras literales del título
  semantico — describe el tema con otras palabras
  agregado  — pregunta por el conjunto, no por un documento

Esa mezcla importa: la rama BM25 gana en los léxicos y la vectorial en los
semánticos, así que un peso que solo se mida con unos u otros miente.
"""

BANCO = [
    # ── agregados ─────────────────────────────────────────────────────────
    ("que areas tiene la universidad",        "sgc:mapa",                    "agregado"),
    ("como esta organizada la upeu",          "sgc:mapa",                    "agregado"),
    ("organigrama de la universidad",         "sgc:mapa",                    "agregado"),
    # ── institucionales concretos ─────────────────────────────────────────
    ("que servicios ofrece la DTI",           "sgc:area:DTI",                "lexico"),
    ("de que se encarga la direccion de investigacion e innovacion",
                                              "sgc:area:DIR-INVESTIGACION-E-INNOVACION", "lexico"),
    ("quien es responsable del proceso de matricula", "sgc:proceso:C02",     "semantico"),
    ("gestion tecnologica proceso de soporte","sgc:proceso:S04",             "lexico"),
    # ── catalogo (lexico puro) ────────────────────────────────────────────
    ("Introduccion a la seguridad y salud en el trabajo", "koha:12987",      "lexico"),
    ("Contabilidad de costos un enfoque gerencial",       "koha:28277",      "lexico"),
    # ── produccion cientifica ─────────────────────────────────────────────
    ("Argopecten purpuratus mitochondrial genome",
     "oai:cris.upeu.edu.pe:123456789/1767",                                  "lexico"),
    # ── revistas ──────────────────────────────────────────────────────────
    ("uso del internet y vida devocional en jovenes adventistas",
     "oai:ojs.pkp.sfu.ca:article/1038",                                      "lexico"),
    # ── repositorio (semantico: no se cita el titulo) ──────────────────────
    ("habitos alimentarios y estres en universitarios",
     "oai:repositorio.upeu.edu.pe:20.500.12840/1943",                        "semantico"),
    ("remocion de contaminantes en lixiviados de relleno sanitario",
     "oai:repositorio.upeu.edu.pe:20.500.12840/1942",                        "semantico"),
    # ── eventos ───────────────────────────────────────────────────────────
    ("cultura de prevencion frente a fenomenos naturales",
     "indico:event:01a08b0d-cd05-7ac3-81a1-68c57d35698f",                    "semantico"),
]
