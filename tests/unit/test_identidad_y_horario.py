"""Quién es quien pregunta, y qué clases tiene hoy.

El 11-sep-2026 Alberto reportó que GUIA seguía sin dar horarios ni cursos, y
sin los datos de identidad de MidPoint. El diagnóstico dio dos causas, ninguna
de ellas un fallo del código que había:

1. **Cobertura.** La identidad se resolvía contra el plugin de Indico, que
   tenía 298 personas de 8.364 usuarios. Para el 96% no había nada que
   responder. MidPoint las tiene todas.
2. **Granularidad.** Lo que Indico llama "evento" es el curso del semestre
   —103 días de media—, así que "¿qué clases tengo hoy?" se contestaba con
   "Ahora mismo: Nutrición Pública II", cierto de agosto a noviembre y por
   tanto inútil. El horario sesión a sesión está en el portal de estudiantes.

Y una restricción que manda en el diseño: ese portal **solo acepta el código
universitario**, no el correo. Por eso la cadena es correo → MidPoint →
código → horario, y el correo sale siempre de la sesión.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from guia.services.horario_de_clases import HorarioDeClases, Sesion, redactar_horario
from guia.services.identidad_institucional import (
    DirectorioInstitucional,
    IdentidadInstitucional,
)

FICHA_MIDPOINT = """{
  "object": {"object": [{"name": "201811220", "fullName": "Billy Santos",
  "emailAddress": "alguien@upeu.edu.pe", "title": "Estudiante",
  "primaryAffiliation": "student", "studyLevel": "Pregrado"}]}
}"""

HORARIO_DE_UN_DIA = {
    "found": True,
    "hasSchedule": True,
    "today": [
        {
            "course": "Investigación V",
            "room": "A-103",
            "building": "Pabellón A",
            "startsAt": "2026-09-09T09:20:00",
            "endsAt": "2026-09-09T11:10:00",
        },
        {
            "course": "Nutrición Pública II",
            "room": "A-103",
            "building": "Pabellón A",
            "startsAt": "2026-09-09T07:30:00",
            "endsAt": "2026-09-09T09:10:00",
        },
    ],
}


def _directorio(respuesta: str, codigo: int = 200) -> DirectorioInstitucional:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"], "va autenticado como cuenta de servicio"
        return httpx.Response(codigo, text=respuesta)

    d = DirectorioInstitucional("https://identity.upeu.edu.pe/midpoint", "svc", "clave")
    d._http = httpx.Client(transport=httpx.MockTransport(responder))
    return d


def _horarios(respuesta: object, codigo: int = 200) -> tuple[HorarioDeClases, list]:
    enviados: list = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json

        enviados.append(json.loads(request.content))
        return httpx.Response(codigo, json=respuesta)

    h = HorarioDeClases("https://indico.upeu.edu.pe")
    h._http = httpx.Client(transport=httpx.MockTransport(responder))
    return h, enviados


class TestMidPointResuelveQuienEs:
    def test_saca_el_codigo_que_abre_el_horario(self) -> None:
        """``name`` es el código universitario, y es la llave de todo lo demás."""
        ficha = _directorio(FICHA_MIDPOINT).de_quien_ha_iniciado_sesion("alguien@upeu.edu.pe")

        assert ficha is not None
        assert ficha.codigo == "201811220"
        assert ficha.nombre_completo == "Billy Santos"
        assert ficha.rol == "Estudiante"
        assert ficha.nivel == "Pregrado"
        assert ficha.es_estudiante

    def test_sin_resultados_no_inventa_ficha(self) -> None:
        assert _directorio('{"object": {}}').de_quien_ha_iniciado_sesion("x@upeu.edu.pe") is None

    def test_credenciales_rechazadas_no_devuelven_datos(self) -> None:
        assert _directorio("", 401).de_quien_ha_iniciado_sesion("x@upeu.edu.pe") is None

    @pytest.mark.parametrize(
        "correo",
        ["", "   ", "no-es-un-correo", "<script>@upeu.edu.pe", "a@b</value></equal>"],
    )
    def test_un_correo_raro_no_llega_a_construir_la_consulta(self, correo: str) -> None:
        """El correo se interpola en un XML; no se construye markup a ciegas.

        La cuenta es de solo lectura, así que el daño posible era escaso, pero
        no es razón para meter texto sin comprobar dentro de una consulta.
        """
        assert _directorio(FICHA_MIDPOINT).de_quien_ha_iniciado_sesion(correo) is None


class TestElHorarioDelDia:
    def test_devuelve_las_sesiones_ordenadas(self) -> None:
        """Llegan desordenadas del origen; se leen por orden de hora."""
        horario, _ = _horarios(HORARIO_DE_UN_DIA)
        dia = horario.del_dia("201811220", date(2026, 9, 9))

        assert dia is not None
        assert [s.curso for s in dia.sesiones] == ["Nutrición Pública II", "Investigación V"]
        assert dia.sesiones[0].cuando() == "07:30-09:10"
        assert dia.sesiones[0].donde() == "A-103 · Pabellón A"

    def test_se_consulta_con_el_codigo_no_con_el_correo(self) -> None:
        """El portal solo acepta el código: con el correo responde found:false."""
        horario, enviados = _horarios(HORARIO_DE_UN_DIA)
        horario.del_dia("201811220", date(2026, 9, 9))

        assert enviados[0]["identifier"] == "201811220"
        assert "@" not in enviados[0]["identifier"]

    def test_sin_codigo_no_se_consulta_nada(self) -> None:
        horario, enviados = _horarios(HORARIO_DE_UN_DIA)

        assert horario.del_dia("", date(2026, 9, 9)) is None
        assert enviados == []

    def test_por_confirmar_no_se_le_ensena_al_usuario(self) -> None:
        """El origen escribe "Por confirmar" en aula y pabellón; eso no es un sitio."""
        s = Sesion(
            curso="Formación Cristiana VIII",
            aula="Por confirmar",
            edificio="Por confirmar",
            inicio=datetime(2026, 9, 10, 17, 50),
            fin=datetime(2026, 9, 10, 19, 35),
        )
        assert s.donde() == ""

    def test_un_dia_sin_clases_se_dice_tal_cual(self) -> None:
        horario, _ = _horarios({"found": True, "hasSchedule": True, "today": []})
        dia = horario.del_dia("201811220", date(2026, 9, 13))

        assert dia is not None
        assert not dia.hay_clases
        assert "no tienes clases" in redactar_horario(dia).lower()

    def test_sin_horario_publicado_se_distingue_de_no_tener_clase(self) -> None:
        """No es lo mismo "hoy libras" que "tu horario no está cargado"."""
        horario, _ = _horarios({"found": True, "hasSchedule": False, "today": []})
        dia = horario.del_dia("201811220", date(2026, 9, 13))

        assert dia is not None
        texto = redactar_horario(dia)
        assert "no está publicado" in texto or "aún no esté publicado" in texto


class TestComoSeLeeElHorario:
    def test_lleva_hora_curso_y_aula(self) -> None:
        horario, _ = _horarios(HORARIO_DE_UN_DIA)
        dia = horario.del_dia("201811220", date(2026, 9, 9))
        assert dia is not None

        texto = redactar_horario(dia, nombre="Billy Santos")

        assert "Billy," in texto, "se saluda por el nombre de pila, no por el completo"
        assert "07:30-09:10" in texto
        assert "Nutrición Pública II" in texto
        assert "A-103" in texto
        assert "miércoles 09/09" in texto


class TestLaIdentidadQueSeMuestra:
    def test_incluye_lo_de_midpoint(self) -> None:
        from guia.services.agenda_academica import redactar_identidad

        texto = redactar_identidad(
            None,
            correo="alguien@upeu.edu.pe",
            nombre="Billy Santos",
            identidad=IdentidadInstitucional(
                codigo="201811220",
                nombre_completo="Billy Santos",
                rol="Estudiante",
                afiliacion="student",
                nivel="Pregrado",
                campus="LIMA",
            ),
        )

        assert "201811220" in texto
        assert "Estudiante" in texto
        assert "Pregrado" in texto
        assert "no consulto los de otras personas" in texto


class TestCuandoQuienPreguntaTrabajaAqui:
    """El caso que reportó Alberto el 11-sep-2026: "yo no soy estudiante".

    GUIA le respondía "no encuentro clases tuyas — revisa tu matrícula", que a
    un Analista Programador de la DTI no le dice nada: no es que no se
    encuentren sus clases, es que no tiene. Y mientras tanto se callaba lo que
    sí sabe de él.
    """

    @staticmethod
    def _personal() -> IdentidadInstitucional:
        return IdentidadInstitucional(
            codigo="9610165",
            nombre_completo="Juan Alberto Sanchez Condor",
            rol="Analista Programador",
            afiliacion="staff",
            nivel="Pregrado",
            campus="LIMA",
        )

    def test_se_distingue_del_estudiante(self) -> None:
        assert self._personal().es_personal
        assert not self._personal().es_estudiante

    def test_le_dice_su_puesto_y_no_le_habla_de_matricula(self) -> None:
        from guia.services.agenda_academica import lo_que_hay_del_personal

        texto = lo_que_hay_del_personal(self._personal(), "jsanchez@upeu.edu.pe")

        assert "Analista Programador" in texto
        assert "9610165" in texto
        assert "LIMA" in texto
        assert "matrícula" not in texto.lower() or "no estás matriculado" in texto.lower()

    def test_no_le_ensena_el_nivel_de_estudios(self) -> None:
        """``studyLevel`` viene poblado en el personal con lo que estudió aquí.

        Enseñarle "Nivel: Pregrado" a un trabajador da a entender que está
        matriculado, que es justo lo contrario de lo que se quiere decir.
        """
        from guia.services.agenda_academica import lo_que_hay_del_personal

        texto = lo_que_hay_del_personal(self._personal(), "jsanchez@upeu.edu.pe")

        assert "Pregrado" not in texto

    def test_dice_en_voz_alta_lo_que_no_sabe(self) -> None:
        """Contrato, vacaciones y área no están en el directorio.

        Comprobado sobre la ficha completa de MidPoint: no hay ningún campo de
        planilla, y la cuenta de servicio solo alcanza 12. Callarlo dejaría al
        usuario sin saber si el dato no existe o si GUIA no supo buscarlo.
        """
        from guia.services.agenda_academica import lo_que_hay_del_personal

        texto = lo_que_hay_del_personal(self._personal(), "jsanchez@upeu.edu.pe").lower()

        assert "contrato" in texto
        assert "vacaciones" in texto
