"""El horario del día: qué clase toca, a qué hora y en qué aula.

Por qué existe, y por qué no bastaba lo que había. GUIA consultaba
``/academic-identity/lookup`` de Indico, que devuelve los **cursos del
semestre**: eventos que duran 103 días de media —medido el 11-sep-2026 sobre
los 47 que hay—. Con eso, a la pregunta "¿qué clases tengo hoy?" GUIA
contestaba "Ahora mismo: Nutrición Pública II", que es verdad de agosto a
noviembre y por tanto no dice nada útil un jueves a las nueve de la noche.

El horario de verdad —sesión a sesión, con aula y hora— lo sirve el portal de
estudiantes en ``/student-api/v1/schedule/lookup``. Comprobado: para un
estudiante devuelve "Nutrición Pública II · A-103 · Pabellón A ·
07:30-10:10", día por día.

**Ese servicio solo acepta el código universitario**, no el correo: con el
correo responde ``found: false``. Por eso este cliente recibe el código ya
resuelto por MidPoint (ver ``identidad_institucional``) y no un identificador
cualquiera — el código sale de la sesión autenticada, nunca del texto del
chat.

Nota de seguridad, anotada porque conviene no perderla de vista: esa ruta **no
pide autenticación** y acepta también el DNI. Se reportó el 10-sep-2026. GUIA
la consume igual porque es la fuente que hay y porque solo pregunta por el
titular de la sesión, pero el agujero es del servicio, no de este cliente, y
sigue abierto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from guia.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Sesion:
    """Una clase concreta: la de hoy a las 7:30, no el curso del semestre."""

    curso: str
    aula: str | None
    edificio: str | None
    inicio: datetime | None
    fin: datetime | None
    docente: str | None = None

    def cuando(self) -> str:
        if self.inicio is None:
            return ""
        if self.fin is None:
            return self.inicio.strftime("%H:%M")
        return f"{self.inicio.strftime('%H:%M')}-{self.fin.strftime('%H:%M')}"

    def donde(self) -> str:
        """Aula y pabellón, saltándose los "Por confirmar" del origen."""
        partes = [
            p
            for p in (self.aula, self.edificio)
            if p and p.strip().lower() not in ("", "por confirmar")
        ]
        return " · ".join(partes)


@dataclass(frozen=True)
class HorarioDelDia:
    fecha: date
    sesiones: list[Sesion] = field(default_factory=list)
    tiene_horario: bool = True

    @property
    def hay_clases(self) -> bool:
        return bool(self.sesiones)


def _hora(valor: object) -> datetime | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        logger.warning("horario_fecha_ilegible", valor=valor[:32])
        return None


def _sesion(crudo: object) -> Sesion | None:
    if not isinstance(crudo, dict):
        return None
    curso = crudo.get("course")
    if not isinstance(curso, str) or not curso.strip():
        return None

    def _texto(clave: str) -> str | None:
        v = crudo.get(clave)
        return v.strip() if isinstance(v, str) and v.strip() else None

    return Sesion(
        curso=curso.strip(),
        aula=_texto("room"),
        edificio=_texto("building"),
        inicio=_hora(crudo.get("startsAt") or crudo.get("starts_at")),
        fin=_hora(crudo.get("endsAt") or crudo.get("ends_at")),
        docente=_texto("teacher"),
    )


class HorarioDeClases:
    """Cliente del portal de horarios. Solo pregunta por quien ha entrado.

    Args:
        base_url: Raíz del portal (``https://indico.upeu.edu.pe``).
        timeout: Techo por consulta.
    """

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._url = base_url.rstrip("/") + "/student-api/v1/schedule/lookup"
        self._http = httpx.Client(timeout=timeout)

    @property
    def configurado(self) -> bool:
        return self._url.startswith("http")

    def del_dia(  # noqa: PLR0911 — un return por cada motivo de no tener dato; fundirlos los haría indistinguibles en el registro
        self, codigo_universitario: str, dia: date
    ) -> HorarioDelDia | None:
        """Las clases de esa persona ese día.

        Args:
            codigo_universitario: El código que devolvió MidPoint para la
                sesión autenticada. No se acepta un identificador libre a
                propósito: es el único punto por el que se podría consultar el
                horario de otra persona.
            dia: Qué día se consulta.
        """
        codigo = (codigo_universitario or "").strip()
        if not codigo or not self.configurado:
            return None

        try:
            r = self._http.post(
                self._url,
                json={"identifier": codigo, "date": dia.isoformat()},
                headers={"Content-Type": "application/json"},
            )
        except Exception as exc:
            logger.warning("horario_no_responde", error=str(exc))
            return None

        if r.status_code == 404:
            return None
        if r.status_code != 200:
            logger.warning("horario_respuesta_inesperada", codigo=r.status_code)
            return None

        try:
            datos = r.json()
        except ValueError:
            logger.warning("horario_respuesta_no_es_json")
            return None

        if not isinstance(datos, dict) or not datos.get("found"):
            return None

        sesiones = [s for s in (_sesion(x) for x in datos.get("today") or []) if s]
        sesiones.sort(key=lambda s: s.inicio or datetime.max)
        return HorarioDelDia(
            fecha=dia,
            sesiones=sesiones,
            tiene_horario=bool(datos.get("hasSchedule", True)),
        )

    def cerrar(self) -> None:
        self._http.close()


_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def redactar_horario(horario: HorarioDelDia, *, nombre: str | None = None) -> str:
    """El horario en texto, listo para el chat.

    Se redacta aquí en vez de pedírselo al modelo: son datos del propio
    usuario y no hay nada que interpretar, así que pasarlos por una síntesis
    solo añadiría latencia y una ocasión de inventarse un aula.
    """
    saludo = f"{nombre.split()[0]}, " if nombre else ""
    dia = _DIAS[horario.fecha.weekday()]
    fecha = f"{dia} {horario.fecha.strftime('%d/%m')}"

    if not horario.hay_clases:
        if not horario.tiene_horario:
            return (
                f"{saludo}no tienes un horario cargado todavía. Si ya te matriculaste, "
                "puede que aún no esté publicado — revísalo en "
                "https://indico.upeu.edu.pe/student/"
            )
        return f"{saludo}no tienes clases el {fecha}."

    lineas = [f"{saludo}esto es lo que tienes el {fecha}:" if saludo else f"El {fecha} tienes:"]
    for s in horario.sesiones:
        donde = f" — {s.donde()}" if s.donde() else ""
        docente = f" (con {s.docente})" if s.docente else ""
        lineas.append(f"- **{s.cuando()}** · {s.curso}{donde}{docente}")
    return "\n".join(lineas)
