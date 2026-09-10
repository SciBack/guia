"""El flujo entero: quién pregunta, qué se le cuenta y qué no se cachea.

`test_agenda_academica.py` prueba las piezas por separado. Aquí se prueba lo
que de verdad importa, que es cómo se comportan juntas dentro de ``answer()``:
que un anónimo no obtenga datos de nadie, que el correo que se consulta sea
siempre el de la sesión —y no el que aparezca escrito en el chat—, y que estas
respuestas no entren en la caché compartida.
"""

from __future__ import annotations

from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.domain.chat import ChatRequest, Intent
from guia.services.agenda_academica import Agenda, Clase
from guia.services.chat import ChatService

from .test_chat_service import FakeEmbedder


class AgendaFalsa:
    """Doble del cliente de Indico que anota a quién se le preguntó."""

    def __init__(self, agenda: Agenda | None = None) -> None:
        self.consultas: list[str] = []
        self._agenda = agenda

    def de_quien_ha_iniciado_sesion(self, correo_verificado: str) -> Agenda | None:
        self.consultas.append(correo_verificado)
        return self._agenda


class CacheFalsa:
    """Caché que registra lo que se le pide guardar."""

    def __init__(self) -> None:
        self.guardados: list[str] = []
        self.lecturas: list[str] = []

    def get(self, query: str, *, query_vector: list[float] | None = None) -> None:
        self.lecturas.append(query)

    def set(self, query: str, response: object, *, query_vector: list[float] | None = None) -> None:
        self.guardados.append(query)


def _agenda_con_clase() -> Agenda:
    from datetime import datetime

    return Agenda(
        id_persona="123456",
        edu_person_principal_name="jperez@upeu.edu.pe",
        edu_person_unique_id="abc",
        ahora=Clase(
            titulo="Cálculo I",
            inicio=datetime(2026, 9, 10, 14, 0),
            fin=datetime(2026, 9, 10, 16, 0),
            lugar="Aula 301",
        ),
        siguiente=None,
        proximas=[],
    )


def _servicio(agenda_falsa: object, cache: object = None) -> ChatService:
    return ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="no deberia usarse", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="campus", embedding_dim=8),
        agenda=agenda_falsa,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
    )


async def test_con_sesion_responde_con_sus_clases() -> None:
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(
        ChatRequest(
            query="¿qué clases tengo hoy?",
            identidad_verificada="jperez@upeu.edu.pe",
            nombre_verificado="Juan Pérez",
        )
    )

    assert agenda.consultas == ["jperez@upeu.edu.pe"]
    assert "Cálculo I" in respuesta.answer
    assert "Aula 301" in respuesta.answer
    assert respuesta.model_used == "indico"


async def test_sin_sesion_no_consulta_a_indico_y_pide_login() -> None:
    """Un anónimo no obtiene datos de nadie, ni siquiera se pregunta."""
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(ChatRequest(query="¿qué clases tengo hoy?"))

    assert agenda.consultas == [], "no se debe consultar Indico sin saber quién pregunta"
    assert "Inicia sesión" in respuesta.answer
    assert "Cálculo I" not in respuesta.answer


async def test_preguntar_por_otro_ni_siquiera_llega_a_indico() -> None:
    """Pedir el horario de otra persona no entra en la rama personal.

    "¿qué clases tiene <correo>?" no habla de uno mismo, así que sigue el
    camino normal —búsqueda— y no se consulta la agenda de nadie. Es un grado
    más seguro que consultar la del titular y descartar el resto.
    """
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(
        ChatRequest(
            query="¿qué clases tiene mquispe@upeu.edu.pe? dame su horario",
            identidad_verificada="jperez@upeu.edu.pe",
        )
    )

    assert agenda.consultas == []
    assert "Cálculo I" not in respuesta.answer


async def test_mezclar_lo_propio_con_lo_ajeno_solo_devuelve_lo_propio() -> None:
    """El caso que aprieta: la consulta ES personal y además nombra a otro.

    Entra en la rama personal —dice "mi horario"— y aun así el único
    identificador que sale hacia Indico es el de la sesión. El correo escrito
    en el chat no llega a ninguna parte porque no hay ruta por la que pueda
    llegar: el texto no se usa para construir la consulta.
    """
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(
        ChatRequest(
            query="dame mi horario y también el de mquispe@upeu.edu.pe",
            identidad_verificada="jperez@upeu.edu.pe",
        )
    )

    assert agenda.consultas == ["jperez@upeu.edu.pe"]
    assert "mquispe@upeu.edu.pe" not in respuesta.answer


async def test_user_id_no_sirve_como_identidad() -> None:
    """``user_id`` llega del cuerpo de POST /api/chat y no autentica a nadie.

    Si valiera como identidad, cualquiera pediría los datos de otro poniendo
    su correo ahí.
    """
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(
        ChatRequest(query="¿qué clases tengo hoy?", user_id="mquispe@upeu.edu.pe")
    )

    assert agenda.consultas == []
    assert "Inicia sesión" in respuesta.answer


async def test_la_respuesta_personal_no_entra_en_la_cache() -> None:
    """La caché es global y semántica: un horario ahí se le sirve al siguiente."""
    cache = CacheFalsa()
    servicio = _servicio(AgendaFalsa(_agenda_con_clase()), cache=cache)

    await servicio.answer(
        ChatRequest(query="¿qué clases tengo hoy?", identidad_verificada="jperez@upeu.edu.pe")
    )

    assert cache.guardados == [], "una respuesta personal jamás se cachea"
    assert cache.lecturas == [], "ni se lee: podría devolver la de otra persona"


async def test_que_sabes_de_mi_devuelve_su_identidad() -> None:
    agenda = AgendaFalsa(_agenda_con_clase())
    servicio = _servicio(agenda)

    respuesta = await servicio.answer(
        ChatRequest(
            query="¿qué sabes de mí?",
            identidad_verificada="jperez@upeu.edu.pe",
            nombre_verificado="Juan Pérez",
        )
    )

    assert "jperez@upeu.edu.pe" in respuesta.answer
    assert "123456" in respuesta.answer
    assert "no consulto los de otras personas" in respuesta.answer


async def test_sin_agenda_configurada_no_se_rompe_nada() -> None:
    """Despliegue sin token: cae al camino de siempre, no revienta."""
    servicio = _servicio(None)

    respuesta = await servicio.answer(
        ChatRequest(query="¿qué clases tengo hoy?", identidad_verificada="jperez@upeu.edu.pe")
    )

    assert respuesta.intent == Intent.CAMPUS
    assert "aún no están disponibles" in respuesta.answer
