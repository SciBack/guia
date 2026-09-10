"""Cuando la lista no sabe, decide el modelo — y responde él.

La objeción que originó esto, de Alberto el 10-sep-2026: «¿no se supone que la
IA de Claude es la que nos tiene que ayudar? ¿no una plantilla que no va a
tomar todas las opciones?». Tenía razón. La detección de "¿dice sobre qué
buscar?" era una lista de palabras y falló dos días seguidos con la misma
pregunta escrita distinto.

Ahora es una cascada por coste, como el router de intención: las listas
despachan lo evidente gratis, y lo dudoso lo decide el modelo. Lo que se prueba
aquí es que cada escalón hace su trabajo y, sobre todo, que el caso que se coló
llega hasta el modelo en vez de morir en una lista.
"""

from __future__ import annotations

import asyncio

import pytest
from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.domain.chat import ChatRequest
from guia.services.chat import ChatService
from guia.services.lector_de_peticion import LectorDePeticion, hay_peticion

from .test_chat_service import FakeEmbedder


class LLMQueAnota:
    """Modelo falso que anota si lo llamaron y con qué."""

    def __init__(self, respuesta: str = "TEMA", *, tarda: float = 0.0) -> None:
        self.llamadas: list[str] = []
        self._respuesta = respuesta
        self._tarda = tarda

    def complete(self, messages: list, **kwargs: object) -> object:
        import time

        self.llamadas.append(messages[-1].content)
        if self._tarda:
            time.sleep(self._tarda)

        class R:
            content = self._respuesta

        return R()


class LLMQueRevienta:
    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def complete(self, messages: list, **kwargs: object) -> object:
        self.llamadas.append(messages[-1].content)
        raise RuntimeError("el proveedor no responde")


def _servicio(llm_lector: object | None) -> ChatService:
    lector = LectorDePeticion(llm_lector, timeout=0.5) if llm_lector else None  # type: ignore[arg-type]
    return ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="respuesta", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        lector_de_peticion=lector,
    )


class TestQuienDecideEnCadaEscalon:
    async def test_la_lista_decide_que_falta_y_el_modelo_como_se_pregunta(self) -> None:
        """Dos decisiones distintas: la lista ve QUE falta, el modelo escribe CÓMO.

        "necesito hacer mi tarea" no deja una sola palabra de contenido al
        vaciarla, así que no hace falta preguntar a nadie si falta el tema.
        Lo que sí se le pide al modelo es que redacte la repregunta, en vez
        del texto fijo de siempre.
        """
        llm = LLMQueAnota(respuesta="¿De qué asignatura es la tarea y sobre qué tema?")
        falta = await _servicio(llm)._que_le_falta_a_la_consulta("necesito hacer mi tarea")

        assert falta == "¿De qué asignatura es la tarea y sobre qué tema?"
        assert llm.llamadas == ["necesito hacer mi tarea"]

    async def test_si_la_lista_esta_segura_su_criterio_manda(self) -> None:
        """El modelo dice que hay tema; la lista sabe que no queda nada.

        "quiero libros" es el caso: los formatos no son temas. Aquí no se
        busca "libros" en el catálogo — se pregunta, con el texto de reserva.
        """
        falta = await _servicio(LLMQueAnota("TEMA"))._que_le_falta_a_la_consulta("quiero libros")
        assert falta is not None

    async def test_un_tema_a_secas_tampoco(self) -> None:
        """"contaminación del lago Titicaca" no pide nada: nombra algo."""
        llm = LLMQueAnota()
        falta = await _servicio(llm)._que_le_falta_a_la_consulta(
            "contaminación del lago Titicaca"
        )

        assert falta is None
        assert llm.llamadas == []

    async def test_la_zona_gris_llega_al_modelo(self) -> None:
        """El caso de la captura. Pide algo Y nombra cosas: aquí la lista falló.

        Es el test que importa: si alguien vuelve a resolver esto solo con
        palabras, la llamada desaparece y esto se pone rojo.
        """
        llm = LLMQueAnota(respuesta="¿Sobre qué tema es tu investigación?")
        falta = await _servicio(llm)._que_le_falta_a_la_consulta(
            "me puedes ayudar en mi investigacion?"
        )

        assert llm.llamadas == ["me puedes ayudar en mi investigacion?"]
        assert falta == "¿Sobre qué tema es tu investigación?"


class TestLoQueDevuelveElModelo:
    async def test_si_dice_que_hay_tema_se_busca(self) -> None:
        lector = LectorDePeticion(LLMQueAnota("TEMA"), timeout=1.0)  # type: ignore[arg-type]
        assert await lector.que_le_falta("ayudame con mi tesis sobre la quinua") is None

    async def test_su_repregunta_se_usa_tal_cual(self) -> None:
        """No hay plantilla de por medio: lo que escribe el modelo es la respuesta."""
        escrito = "Veo que es para tu tesis. ¿De qué tema trata?"
        lector = LectorDePeticion(LLMQueAnota(escrito), timeout=1.0)  # type: ignore[arg-type]

        assert await lector.que_le_falta("ayudame con mi tesis") == escrito

    async def test_una_respuesta_demasiado_corta_no_se_le_ensena_a_nadie(self) -> None:
        """Salirse del formato no debe convertirse en un mensaje absurdo."""
        lector = LectorDePeticion(LLMQueAnota("ok"), timeout=1.0)  # type: ignore[arg-type]
        assert await lector.que_le_falta("ayudame con mi tesis") is None


class TestCuandoElModeloNoEsta:
    """Degrada hacia buscar, nunca hacia dejar al usuario esperando."""

    async def test_si_revienta_se_busca(self) -> None:
        llm = LLMQueRevienta()
        lector = LectorDePeticion(llm, timeout=1.0)  # type: ignore[arg-type]

        assert await lector.que_le_falta("ayudame con mi tesis") is None
        assert llm.llamadas, "se intentó, y al fallar se sigue"

    async def test_si_tarda_demasiado_se_busca(self) -> None:
        lector = LectorDePeticion(LLMQueAnota("TEMA", tarda=1.0), timeout=0.2)  # type: ignore[arg-type]

        t = asyncio.get_event_loop().time()
        assert await lector.que_le_falta("ayudame con mi tesis") is None
        assert asyncio.get_event_loop().time() - t < 0.9, "no espera al modelo lento"

    async def test_sin_lector_configurado_funciona_como_antes(self) -> None:
        servicio = _servicio(None)
        # Zona gris sin modelo: se busca, como se hacía antes de todo esto.
        # ("ayudame con mi investigacion" no vale de ejemplo: ahí no queda ni
        # una palabra de contenido, así que lo resuelve la lista.)
        assert await servicio._que_le_falta_a_la_consulta(
            "necesito articulos de energias renovables"
        ) is None
        # Y lo que la lista sí sabe se sigue preguntando, con el texto fijo.
        assert await servicio._que_le_falta_a_la_consulta("necesito hacer mi tarea") is not None


class TestQueCuentaComoPeticion:
    @pytest.mark.parametrize(
        "consulta",
        ["me puedes ayudar en mi investigacion?", "necesito articulos de quinua", "quiero libros"],
    )
    def test_pide_algo(self, consulta: str) -> None:
        assert hay_peticion(consulta)

    @pytest.mark.parametrize(
        "consulta",
        [
            "contaminacion del lago Titicaca",
            "Darwin y la evolucion",
            # La cortesía no convierte una pregunta en petición. Con "por" en
            # la lista, esta consulta gastaba una llamada al modelo por el
            # "por qué", y el modelo respondía que faltaba el tema.
            "que es la kiwicha y por que es importante",
        ],
    )
    def test_solo_nombra_algo(self, consulta: str) -> None:
        assert not hay_peticion(consulta)


class TestElFlujoCompleto:
    async def test_la_repregunta_del_modelo_llega_al_usuario(self) -> None:
        escrito = "Entiendo que es para tu investigación. ¿Sobre qué tema trata?"
        servicio = _servicio(LLMQueAnota(escrito))

        respuesta = await servicio.answer(
            ChatRequest(query="me puedes ayudar en mi investigacion?")
        )

        assert respuesta.answer == escrito
        assert respuesta.sources == []
