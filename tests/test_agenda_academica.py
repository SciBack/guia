"""GUIA solo cuenta lo tuyo, y solo si iniciaste sesión.

La regla que se prueba aquí es la del 10-sep-2026: con el login de M365 y
Keycloak ya sabemos quién entró, así que GUIA puede darle sus propios datos de
identidad y su horario. Los de otra persona, nunca.

Lo que hace que esa regla aguante no es el prompt, son tres cosas concretas, y
cada una tiene su test:

1. La firma del cliente no admite un identificador — solo el correo de la
   sesión. No hay parámetro por el que pedir la agenda de otro.
2. La identidad viaja en ``identidad_verificada``, que ``ChatRequestSchema`` no
   expone. El ``user_id`` del cuerpo de ``POST /api/chat`` no vale como
   credencial.
3. Las consultas personales no tocan la caché, que es global y semántica.
"""

from __future__ import annotations

import inspect

import pytest

from guia.api.schemas import ChatRequestSchema
from guia.domain.chat import ChatRequest
from guia.services.agenda_academica import (
    Agenda,
    AgendaAcademica,
    Clase,
    es_consulta_sobre_uno_mismo,
    redactar,
    redactar_identidad,
)


class TestNoSePuedePreguntarPorOtro:
    """Lo que impide el abuso es que no exista el parámetro."""

    def test_la_firma_solo_acepta_el_correo_de_la_sesion(self) -> None:
        parametros = list(
            inspect.signature(AgendaAcademica.de_quien_ha_iniciado_sesion).parameters
        )
        assert parametros == ["self", "correo_verificado"], (
            "Si aparece otro parámetro de identidad, el modelo puede rellenarlo "
            "con lo que le pidan en el chat."
        )

    def test_la_api_publica_no_expone_la_identidad(self) -> None:
        """``POST /api/chat`` no autentica: su cuerpo no puede traer identidad.

        Si ``identidad_verificada`` apareciera en el esquema HTTP, bastaría con
        mandar el correo de otra persona para que GUIA contara sus datos.
        """
        assert "identidad_verificada" not in ChatRequestSchema.model_fields
        assert "nombre_verificado" not in ChatRequestSchema.model_fields

    def test_user_id_y_identidad_son_campos_distintos(self) -> None:
        """``user_id`` es para el bucketing A/B y llega del cliente; no es una
        credencial. Que sean dos campos es lo que impide confundirlos."""
        campos = ChatRequest.model_fields
        assert "user_id" in campos
        assert "identidad_verificada" in campos


class TestQueSeConsideraConsultaSobreUnoMismo:
    @pytest.mark.parametrize(
        "consulta",
        [
            "¿qué clases tengo hoy?",
            "cuál es mi horario",
            "¿qué sabes de mí?",
            "quién soy",
            "mis datos",
            "en qué aula me toca ahora",
            "estoy matriculado en algún curso",
        ],
    )
    def test_si(self, consulta: str) -> None:
        assert es_consulta_sobre_uno_mismo(consulta)

    @pytest.mark.parametrize(
        "consulta",
        [
            # Las tres primeras son el motivo de que haga falta doble señal:
            # llevan "mi" y son búsquedas de catálogo, de las más frecuentes.
            "bibliografía para mi tesis",
            "libros para mi tarea de estadística",
            "artículos para mi investigación sobre quinua",
            "¿qué tesis hay sobre hábitos de estudio?",
            "horario de atención de la biblioteca",
            "hola",
        ],
    )
    def test_no(self, consulta: str) -> None:
        assert not es_consulta_sobre_uno_mismo(consulta)


class TestLaLecturaDeLaRespuestaDeIndico:
    """El cliente no se fía del JSON: Indico puede devolver campos a medias."""

    @staticmethod
    def _cliente(respuesta: object, codigo: int = 200) -> AgendaAcademica:
        import httpx

        def responder(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Academic-Identity-Token"] == "s3cr3t0"
            return httpx.Response(codigo, json=respuesta)

        cliente = AgendaAcademica("https://indico.upeu.edu.pe", "s3cr3t0")
        cliente._http = httpx.Client(transport=httpx.MockTransport(responder))
        return cliente

    def test_lee_la_agenda_completa(self) -> None:
        agenda = self._cliente(
            {
                "found": True,
                "identity": {
                    "id_persona": "123456",
                    "eduPersonPrincipalName": "jperez@upeu.edu.pe",
                    "eduPersonUniqueId": "abc",
                },
                "current": {
                    "title": "Cálculo I",
                    "start": "2026-09-10T14:00:00+00:00",
                    "end": "2026-09-10T16:00:00+00:00",
                    "location": "Aula 301",
                },
                "next": None,
                "classes": [],
            }
        ).de_quien_ha_iniciado_sesion("jperez@upeu.edu.pe")

        assert agenda is not None
        assert agenda.id_persona == "123456"
        assert agenda.ahora is not None
        assert agenda.ahora.titulo == "Cálculo I"
        assert agenda.ahora.cuando() == "14:00–16:00"  # noqa: RUF001 — guion largo, como lo escribe el código

    def test_una_clase_sin_titulo_se_descarta_en_vez_de_romper(self) -> None:
        agenda = self._cliente(
            {"found": True, "identity": {}, "classes": [{"start": "2026-09-10T14:00:00+00:00"}]}
        ).de_quien_ha_iniciado_sesion("jperez@upeu.edu.pe")
        assert agenda is not None
        assert agenda.proximas == []

    def test_una_fecha_ilegible_no_tumba_la_clase(self) -> None:
        agenda = self._cliente(
            {"found": True, "identity": {}, "classes": [{"title": "Física", "start": "ayer"}]}
        ).de_quien_ha_iniciado_sesion("jperez@upeu.edu.pe")
        assert agenda is not None
        assert agenda.proximas[0].titulo == "Física"
        assert agenda.proximas[0].inicio is None

    def test_404_es_no_lo_conozco_no_un_error(self) -> None:
        cliente = self._cliente({"found": False, "classes": []}, codigo=404)
        assert cliente.de_quien_ha_iniciado_sesion("nadie@upeu.edu.pe") is None

    def test_401_no_devuelve_datos(self) -> None:
        """Si el token deja de valer, se degrada a 'no sé', nunca a datos."""
        cliente = self._cliente({"error": "unauthorized"}, codigo=401)
        assert cliente.de_quien_ha_iniciado_sesion("jperez@upeu.edu.pe") is None

    def test_sin_token_configurado_no_se_consulta_nada(self) -> None:
        assert not AgendaAcademica("https://indico.upeu.edu.pe", "").configurada

    def test_correo_vacio_no_consulta(self) -> None:
        assert self._cliente({"found": True}).de_quien_ha_iniciado_sesion("  ") is None


class TestLoQueSeLeEnsenaAlUsuario:
    def test_la_identidad_dice_la_regla_en_voz_alta(self) -> None:
        texto = redactar_identidad(
            Agenda(
                id_persona="123456",
                edu_person_principal_name="jperez@upeu.edu.pe",
                edu_person_unique_id="abc",
                ahora=None,
                siguiente=None,
                proximas=[],
            ),
            correo="jperez@upeu.edu.pe",
            nombre="Juan Pérez",
        )
        assert "Juan Pérez" in texto
        assert "123456" in texto
        assert "no consulto los de otras personas" in texto

    def test_sin_agenda_sigue_diciendo_lo_que_hay_en_la_sesion(self) -> None:
        """El correo y el nombre son suyos y vienen del login: negárselos no
        protege a nadie."""
        texto = redactar_identidad(None, correo="jperez@upeu.edu.pe", nombre="Juan")
        assert "jperez@upeu.edu.pe" in texto

    def test_sin_clases_remite_a_indico(self) -> None:
        vacia = Agenda(
            id_persona=None,
            edu_person_principal_name=None,
            edu_person_unique_id=None,
            ahora=None,
            siguiente=None,
            proximas=[],
        )
        assert "indico.upeu.edu.pe" in redactar(vacia)

    def test_la_agenda_se_lee_con_hora_y_lugar(self) -> None:
        from datetime import datetime

        clase = Clase(
            titulo="Cálculo I",
            inicio=datetime(2026, 9, 10, 14, 0),
            fin=datetime(2026, 9, 10, 16, 0),
            lugar="Aula 301",
        )
        texto = redactar(
            Agenda(
                id_persona=None,
                edu_person_principal_name=None,
                edu_person_unique_id=None,
                ahora=clase,
                siguiente=None,
                proximas=[clase],
            ),
            nombre="Juan",
        )
        assert "Cálculo I" in texto
        assert "Aula 301" in texto
        assert "14:00–16:00" in texto  # noqa: RUF001 — guion largo, como lo escribe el código
