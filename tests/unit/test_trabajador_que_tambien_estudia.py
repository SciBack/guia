"""Se puede trabajar en la universidad y estudiar en ella a la vez.

Caso real, 11-sep-2026. Un practicante de la DTI que además está matriculado
preguntó "¿qué cursos tengo hoy?" y GUIA le contestó con su ficha laboral
entera —puesto, código de trabajador, área— más dos afirmaciones falsas:

    Condición: personal de la universidad, no estudiante
    No te muestro horario de clases porque no estás matriculado

Las dos salían de deducir la condición de estudiante a partir de
``primaryAffiliation``, que en MidPoint es **una sola**: de que diga "staff"
no se sigue que la persona no estudie. El portal de horarios decía
``tiene_horario: True`` para su código.

Dos fallos distintos, y conviene no confundirlos: uno es afirmar algo falso
sobre alguien; el otro es contestar algo que no preguntó, enseñándole de paso
datos que no pidió.
"""

from __future__ import annotations

from datetime import date

import pytest

from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.domain.chat import ChatRequest
from guia.services.agenda_academica import lo_que_hay_del_personal
from guia.services.chat import ChatService
from guia.services.horario_de_clases import HorarioDelDia, Sesion

from .test_chat_service import FakeEmbedder


class _IdentidadFalsa:
    """La ficha tal como la devuelve MidPoint para el caso real."""

    def __init__(self, afiliacion: str = "staff") -> None:
        self.codigo = "202210253"
        self.nombre_completo = "Nombre Apellido"
        self.rol = "Practicante"
        self.afiliacion = afiliacion
        self.nivel = "Pregrado"
        self.campus = "LIMA"
        self.unidades = ("Dirección de Tecnologías de Información",)

    @property
    def es_estudiante(self) -> bool:
        return self.afiliacion == "student"

    @property
    def es_personal(self) -> bool:
        return self.afiliacion in ("staff", "faculty", "employee")


class _DirectorioFalso:
    def __init__(self, identidad: object) -> None:
        self._identidad = identidad
        self.consultas: list[str] = []

    def de_quien_ha_iniciado_sesion(self, correo: str) -> object:
        self.consultas.append(correo)
        return self._identidad


class _HorarioFalso:
    def __init__(self, horario: HorarioDelDia | None) -> None:
        self._horario = horario
        self.consultas: list[str] = []

    def del_dia(self, codigo: str, dia: date) -> HorarioDelDia | None:
        self.consultas.append(codigo)
        return self._horario


def _matriculado_con_clase() -> HorarioDelDia:
    return HorarioDelDia(
        fecha=date(2026, 9, 11),
        sesiones=[Sesion(curso="Cálculo I", aula="A-103", edificio="Pabellón A",
                         inicio=None, fin=None)],
        tiene_horario=True,
    )


def _matriculado_sin_clase_hoy() -> HorarioDelDia:
    return HorarioDelDia(fecha=date(2026, 9, 11), sesiones=[], tiene_horario=True)


def _sin_matricula() -> HorarioDelDia:
    return HorarioDelDia(fecha=date(2026, 9, 11), sesiones=[], tiene_horario=False)


def _servicio(identidad: object, horario: HorarioDelDia | None) -> ChatService:
    return ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="x", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="campus", embedding_dim=8),
        directorio=_DirectorioFalso(identidad),  # type: ignore[arg-type]
        horario=_HorarioFalso(horario),  # type: ignore[arg-type]
    )


class TestLaFichaNoAfirmaLoQueNoSabe:
    def test_un_trabajador_matriculado_no_figura_como_no_estudiante(self) -> None:
        texto = lo_que_hay_del_personal(
            _IdentidadFalsa(), "x@upeu.edu.pe", tambien_estudia=True
        )

        assert "no estudiante" not in texto
        assert "no estás matriculado" not in texto
        assert "además estás matriculado" in texto

    def test_un_trabajador_sin_matricula_sigue_sabiendolo(self) -> None:
        texto = lo_que_hay_del_personal(
            _IdentidadFalsa(), "x@upeu.edu.pe", tambien_estudia=False
        )

        assert "No me consta ninguna matrícula" in texto

    def test_si_no_se_pudo_comprobar_no_se_afirma_nada(self) -> None:
        """Callar es mejor que arriesgarse a decirle a alguien que no estudia."""
        texto = lo_que_hay_del_personal(
            _IdentidadFalsa(), "x@upeu.edu.pe", tambien_estudia=None
        )

        assert "matricul" not in texto.lower()
        assert "no estudiante" not in texto


@pytest.mark.asyncio
class TestSeContestaLoQuePreguntan:
    async def test_pide_sus_cursos_y_recibe_sus_cursos(self) -> None:
        """El caso de Piero: preguntó por clases y le llegó su ficha laboral."""
        servicio = _servicio(_IdentidadFalsa(), _matriculado_con_clase())

        r = await servicio.answer(
            ChatRequest(
                query="hola quiero saber que cursos tengo hoy",
                identidad_verificada="x@upeu.edu.pe",
            )
        )

        assert "Cálculo I" in r.answer
        assert "Código de trabajador" not in r.answer
        assert "Practicante" not in r.answer

    async def test_matriculado_sin_clase_hoy_no_recibe_su_ficha(self) -> None:
        servicio = _servicio(_IdentidadFalsa(), _matriculado_sin_clase_hoy())

        r = await servicio.answer(
            ChatRequest(query="qué clases tengo hoy", identidad_verificada="x@upeu.edu.pe")
        )

        assert "no tienes clases" in r.answer.lower()
        assert "Código de trabajador" not in r.answer

    async def test_trabajador_sin_matricula_recibe_una_explicacion_no_su_ficha(
        self,
    ) -> None:
        servicio = _servicio(_IdentidadFalsa(), _sin_matricula())

        r = await servicio.answer(
            ChatRequest(query="qué clases tengo hoy", identidad_verificada="x@upeu.edu.pe")
        )

        assert "matrícula" in r.answer.lower()
        assert "Código de trabajador" not in r.answer

    async def test_pregunta_por_si_mismo_y_si_recibe_la_ficha(self) -> None:
        """Lo que la ficha laboral sí debe contestar."""
        servicio = _servicio(_IdentidadFalsa(), _matriculado_con_clase())

        r = await servicio.answer(
            ChatRequest(query="qué sabes de mí", identidad_verificada="x@upeu.edu.pe")
        )

        assert "Practicante" in r.answer
        assert "además estás matriculado" in r.answer
