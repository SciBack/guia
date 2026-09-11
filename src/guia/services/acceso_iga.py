"""Qué puede ver quien pregunta, según lo que dice el IGA.

Hasta ahora la identidad de MidPoint solo se usaba dentro del camino
personal: GUIA sabía quién preguntaba cuando alguien decía "¿qué clases tengo
hoy?" y lo olvidaba para todo lo demás. Fuera de ese camino, un Analista
Programador de la DTI y un visitante anónimo recibían exactamente la misma
respuesta — aunque la primera pregunta que hace alguien de dentro suele ser
"¿de qué responde **mi** área?".

Este módulo hace dos cosas, y conviene no confundirlas:

1. **Declara el nivel de acceso.** Antes era implícito y binario —hay correo
   de sesión o no lo hay— y estaba repartido por el código. Aquí se nombra:
   ``PUBLICO``, ``COMUNIDAD``, ``PERSONAL``. Lo que cada nivel abre está
   escrito abajo y se puede auditar.

2. **Contextualiza la respuesta.** Con la unidad que da MidPoint, "mi área"
   deja de ser una frase vacía: la DTI de la ficha es la misma DTI que el
   mapa del SGC dice que responde de "Gestión tecnológica".

**La regla que ningún nivel levanta:** GUIA solo revela datos personales del
titular de la sesión. No es una promesa del prompt, es cómo está construido
—``de_quien_ha_iniciado_sesion`` no acepta un identificador ajeno, así que no
hay nada que pedirle—, y aquí no se añade ninguna puerta nueva. Subir de
nivel da acceso a **lo tuyo**, nunca a lo de otro.

Y una consecuencia que es fácil pasar por alto: **una respuesta que lleva
contexto de quien pregunta no puede entrar en la caché global**, que es
semántica y no distingue por usuario. Por eso ``aporta_contexto`` se decide
con una lista y no con el modelo: de ella depende que la respuesta de una
persona no acabe sirviéndose a otra.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

if True:  # noqa: SIM108 — TYPE_CHECKING no vale: el dataclass lo usa en runtime
    from guia.services.identidad_institucional import IdentidadInstitucional


class NivelDeAcceso(StrEnum):
    """Lo que el IGA permite ver, de menos a más.

    No es una jerarquía de privilegio sobre datos ajenos: los tres niveles
    tienen exactamente el mismo acceso a los datos de terceros, que es
    ninguno. Lo que cambia es cuánto de *lo propio* se puede enseñar.
    """

    PUBLICO = "publico"
    """Sin sesión. El catálogo, el repositorio, la producción científica, las
    revistas, los eventos y el mapa institucional — todo lo que ya es
    público. Nada de nadie."""

    COMUNIDAD = "comunidad"
    """Estudiante con sesión iniciada. Lo público, más sus propias clases,
    su horario y su ficha académica."""

    PERSONAL = "personal"
    """Trabajador con sesión iniciada: docente, administrativo. Lo público,
    más su propia ficha laboral y el contexto de su área — de qué responde
    la unidad en la que trabaja."""


#: Lo que cada nivel abre, en una frase. Se publica en el endpoint de
#: transparencia: un nivel de acceso que no se puede leer desde fuera no es
#: gobernanza, es una variable.
QUE_ABRE_CADA_NIVEL: dict[NivelDeAcceso, str] = {
    NivelDeAcceso.PUBLICO: (
        "Catálogo, repositorio, producción científica, revistas, eventos y el "
        "mapa de áreas y procesos de la universidad. Ningún dato personal."
    ),
    NivelDeAcceso.COMUNIDAD: (
        "Lo anterior, más los datos académicos del propio titular de la "
        "sesión: sus clases, su horario y su ficha de estudiante."
    ),
    NivelDeAcceso.PERSONAL: (
        "Lo anterior, más la ficha laboral del propio titular y el contexto "
        "de su unidad: de qué procesos responde el área en la que trabaja."
    ),
}

#: Invariante del sistema, en todos los niveles.
LIMITE_INFRANQUEABLE = (
    "En ningún nivel se revelan datos personales de terceros. El "
    "identificador con el que se consulta la identidad sale siempre de la "
    "sesión verificada, nunca del texto de la consulta."
)

#: Frases con las que alguien pregunta por SU sitio en la institución. La
#: lista decide si la respuesta lleva contexto personal — y por tanto si
#: puede cachearse—, así que es deliberadamente corta y explícita: un falso
#: positivo aquí solo cuesta una respuesta sin cachear, pero el mecanismo
#: tiene que ser inspeccionable.
_LO_MIO_INSTITUCIONAL = re.compile(
    r"\b(mi|mis)\s+("
    r"area|areas|unidad|unidades|oficina|direccion|departamento|"
    r"facultad|escuela|carrera|jefatura|equipo"
    r")\b"
    r"|\b(a\s+quien|con\s+quien)\s+(le\s+)?(pido|solicito|reclamo|acudo|hablo)\b"
    r"|\bquien\s+(ve|lleva|atiende)\s+lo\s+(de|del)\b"
    r"|\bde\s+que\s+(responde|se\s+encarga)\s+mi\b"
)


def _sin_tildes(texto: str) -> str:
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class QuienPregunta:
    """Quién está al otro lado, según el IGA, y qué se le puede enseñar."""

    nivel: NivelDeAcceso
    correo: str | None = None
    nombre: str | None = None
    rol: str | None = None
    """Lo que dice MidPoint en ``title``: "Analista Programador", "Docente"."""

    unidades: tuple[str, ...] = ()
    """Las áreas a las que pertenece. Es la llave que enlaza con el mapa del
    SGC: la misma cadena que ahí figura como propietaria de un proceso."""

    campus: str | None = None
    codigo: str | None = None

    ficha: IdentidadInstitucional | None = field(default=None, repr=False)
    """La ficha cruda del IGA, tal como vino.

    Se guarda para que el camino personal no tenga que volver a pedirla en la
    misma petición: consultar MidPoint dos veces por mensaje es trabajo
    duplicado aunque la caché lo abarate. Va con ``repr=False`` para que no
    acabe en un log por descuido.
    """

    @property
    def hay_sesion(self) -> bool:
        return self.nivel is not NivelDeAcceso.PUBLICO

    @property
    def puede_ver_lo_suyo(self) -> bool:
        """Si se le pueden enseñar sus propios datos.

        Equivale a tener sesión. Existe como propiedad con nombre porque el
        código que la consulta habla de permisos, no de correos.
        """
        return self.hay_sesion

    @property
    def area_principal(self) -> str | None:
        """La unidad con la que resolver "mi área".

        Se toma la primera: MidPoint las devuelve por ``parentOrgRef``, y
        quien tiene varias suele ser trabajador y egresado a la vez, donde la
        laboral es la que viene primero. Cuando hay más de una, el texto del
        contexto las nombra todas para que el modelo no tenga que adivinar.
        """
        return self.unidades[0] if self.unidades else None

    def para_el_prompt(self) -> str | None:
        """Lo que se le cuenta al modelo sobre quien pregunta.

        Devuelve ``None`` cuando no hay nada que aportar — sin sesión, o con
        sesión pero sin ficha en MidPoint—, para no meter una línea vacía en
        el prompt ni marcar la respuesta como personalizada sin motivo.
        """
        if not self.hay_sesion:
            return None

        piezas: list[str] = []
        if self.nombre:
            piezas.append(f"Se llama {self.nombre}")
        if self.rol:
            piezas.append(f"su cargo es {self.rol}")
        if self.unidades:
            piezas.append("trabaja en " + " y ".join(self.unidades))
        if self.campus:
            piezas.append(f"está en el campus de {self.campus.title()}")
        if not piezas:
            return None

        return (
            "QUIÉN PREGUNTA: " + "; ".join(piezas) + ". "
            "Úsalo para resolver lo que diga \"mi área\", \"mi unidad\" o "
            "\"a quién le pido\", y para ajustar el tono. No repitas su "
            "nombre ni su cargo si no viene a cuento, y no le atribuyas "
            "funciones que no estén en los resultados."
        )


def derivar_acceso(
    identidad: IdentidadInstitucional | None,
    *,
    correo_verificado: str | None,
    nombre_verificado: str | None = None,
) -> QuienPregunta:
    """Traduce la ficha del IGA a un nivel de acceso.

    Args:
        identidad: Lo que devolvió MidPoint, o ``None`` si no tiene ficha o
            el directorio no está disponible.
        correo_verificado: El correo de la sesión de Keycloak. **Es lo único
            que decide si hay sesión**: sin él, nivel público, por mucha
            identidad que se pase.
        nombre_verificado: El nombre que trae la sesión, como respaldo
            cuando MidPoint no tiene ficha de la persona.
    """
    correo = (correo_verificado or "").strip() or None
    if correo is None:
        return QuienPregunta(nivel=NivelDeAcceso.PUBLICO)

    if identidad is None:
        # Hay sesión pero MidPoint no sabe quién es. Cuenta como comunidad:
        # se le pueden enseñar sus propios datos si alguna otra fuente los
        # tiene, y desde luego no se le puede enseñar nada de otro.
        return QuienPregunta(
            nivel=NivelDeAcceso.COMUNIDAD, correo=correo, nombre=nombre_verificado
        )

    nivel = (
        NivelDeAcceso.PERSONAL if identidad.es_personal else NivelDeAcceso.COMUNIDAD
    )
    return QuienPregunta(
        nivel=nivel,
        correo=correo,
        nombre=identidad.nombre_completo or nombre_verificado,
        rol=identidad.rol,
        unidades=identidad.unidades,
        campus=identidad.campus,
        codigo=identidad.codigo,
        ficha=identidad,
    )


def aporta_contexto(query: str, quien: QuienPregunta) -> bool:
    """Si esta consulta se responde mejor sabiendo quién la hace.

    Y, por lo mismo, si la respuesta **no puede cachearse**: la caché es
    semántica y global, así que una respuesta que menciona "tu área, la DTI"
    servida a la siguiente persona que pregunte algo parecido sería una fuga.

    Se decide con una lista y no con el modelo a propósito. En los caminos
    que tocan datos de una persona, lo determinista manda: una lista se lee,
    se prueba y no cambia de opinión entre dos peticiones idénticas.
    """
    if not quien.hay_sesion or not quien.unidades:
        return False
    return bool(_LO_MIO_INSTITUCIONAL.search(_sin_tildes(query)))
