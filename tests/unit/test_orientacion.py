"""Un listado sin una línea encima es un buscador, no un asistente.

Hasta el 10-sep-2026, cuando la respuesta era un listado GUIA no llamaba al
modelo: mandaba "Encontré 5 resultados relacionados con tu consulta" y debajo
los enlaces. Había dos razones medidas para ello —el canal descartaba la prosa,
y esa prosa repetía los títulos— y las dos se caen si el modelo escribe
orientación en vez de repetición.

Lo que se prueba aquí es eso: que se le pide otra cosa, que no se pierde el
listado, y que si el modelo no está el listado sigue saliendo igual.
"""

from __future__ import annotations

from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.domain.chat import ChatRequest, Source
from guia.services.chat import ChatService
from guia.services.orientacion import mensajes_de_orientacion, orientar

from .test_chat_service import FakeEmbedder

FUENTES = [
    Source(
        id="1",
        title="Hábitos de estudio y rendimiento académico",
        source_type="thesis",
        year=2021,
    ),
    Source(id="2", title="Guía para elaborar una tesis", source_type="book", year=2018),
]


class LLMQueAnota:
    def __init__(self, respuesta: str) -> None:
        self.llamadas: list[list] = []
        self._respuesta = respuesta

    def complete(self, messages: list, **kwargs: object) -> object:
        self.llamadas.append(messages)

        class R:
            content = self._respuesta

        return R()


class LLMQueRevienta:
    def complete(self, messages: list, **kwargs: object) -> object:
        raise RuntimeError("el proveedor no responde")


class TestQueSeLePide:
    def test_se_le_dan_los_resultados_que_el_usuario_va_a_ver(self) -> None:
        mensajes = mensajes_de_orientacion("tesis sobre hábitos de estudio", FUENTES)

        assert "tesis sobre hábitos de estudio" in mensajes[-1].content
        assert "Hábitos de estudio y rendimiento académico" in mensajes[-1].content
        assert "2021" in mensajes[-1].content

    def test_se_le_prohibe_referirse_por_numero(self) -> None:
        """Visto en producción: "el resultado más directo es el número 5".

        El listado va agrupado por fuente, así que su numeración no coincide
        con la del prompt: ese "5" señalaba a otra cosa.
        """
        sistema = mensajes_de_orientacion("x", FUENTES)[0].content.lower()
        assert "por su número" in sistema

    def test_se_le_pide_espanol_de_peru(self) -> None:
        """También de producción: "Tenés desde manuales prácticos...". """
        sistema = mensajes_de_orientacion("x", FUENTES)[0].content.lower()
        assert "perú" in sistema
        assert "tenés" in sistema, "hay que nombrar el voseo para que lo evite"

    def test_se_le_pide_que_no_repita_los_titulos(self) -> None:
        """La razón por la que antes se descartaba la prosa: duplicaba el listado."""
        sistema = mensajes_de_orientacion("x", FUENTES)[0].content.lower()

        assert "no repitas los títulos" in sistema
        assert "debajo" in sistema, "tiene que saber que el listado ya va aparte"


class TestCuandoElModeloNoEsta:
    async def test_si_revienta_queda_el_encabezado_de_siempre(self) -> None:
        texto = await orientar(
            LLMQueRevienta(), "quinua", FUENTES, de_reserva="Encontré 2 resultados."
        )
        assert texto == "Encontré 2 resultados."

    async def test_una_respuesta_vacia_no_deja_el_listado_sin_encabezado(self) -> None:
        texto = await orientar(
            LLMQueAnota("  "), "quinua", FUENTES, de_reserva="Encontré 2 resultados."
        )
        assert texto == "Encontré 2 resultados."


class TestElFlujoCompleto:
    @staticmethod
    def _servicio(respuesta: str) -> ChatService:
        store = InMemoryVectorStoreAdapter(dim=8)
        for i, titulo in enumerate(
            [
                "Habitos de estudio y rendimiento academico",
                "Procrastinacion academica en universitarios",
                "Estrategias de aprendizaje autonomo",
                "Motivacion academica en universitarios peruanos",
                "Guia para elaborar una tesis",
            ],
            1,
        ):
            store.upsert(
                f"koha:{i}",
                [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                metadata={"title": titulo, "source": "koha", "year": 2020 + i},
            )
        return ChatService(
            synthesis_llm=LLMQueAnota(respuesta),  # type: ignore[arg-type]
            store=store,
            embedder=FakeEmbedder(),
            classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        )

    async def test_la_orientacion_llega_como_respuesta(self) -> None:
        """Con resultados de catálogo, la respuesta ya no es el encabezado seco.

        Se comprueba sobre el flujo real: si alguien vuelve a saltarse el
        modelo en la rama de listados, esto se pone rojo.
        """
        escrito = "Cuatro van directas al tema; la última es de método, por si te hace falta."
        servicio = self._servicio(escrito)

        respuesta = await servicio.answer(
            ChatRequest(query="libros sobre habitos de estudio en universitarios")
        )

        assert respuesta.answer_type == "list", "el caso que se quiere probar es el listado"
        assert respuesta.answer == escrito
        assert respuesta.model_used == "listado_con_orientacion"
        assert respuesta.sources, "el listado de fuentes sigue viajando aparte"

    async def test_si_el_modelo_falla_el_listado_sale_igual(self) -> None:
        """Perder la orientación no puede costar los resultados."""
        servicio = ChatService(
            synthesis_llm=LLMQueRevienta(),  # type: ignore[arg-type]
            store=self._servicio("x")._store,  # type: ignore[attr-defined]
            embedder=FakeEmbedder(),
            classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        )

        respuesta = await servicio.answer(
            ChatRequest(query="libros sobre habitos de estudio en universitarios")
        )

        assert respuesta.sources
        assert "resultado" in respuesta.answer.lower()
