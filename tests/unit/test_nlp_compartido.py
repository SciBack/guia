"""Los modelos NLP viven una sola vez, en el sidecar.

Medido en el contenedor de produccion el 09-sep-2026: Detoxify 712 MB, spaCy
es_core_news_lg 317 MB, SymSpell 31 MB — 1.061 MB por canal, duplicados en api
y chainlit sobre una VM de 9,7 GB con 500 MB libres. Es la situacion que ADR-051
resolvio para los embeddings, una capa mas arriba.

Lo que estas pruebas protegen no es el ahorro, que es evidente, sino las dos
formas de perderlo sin enterarse: que alguien cargue el modelo local "por si
acaso" cuando el sidecar no responde, y que un fallo del sidecar degrade en
silencio. Detoxify llevaba meses caido en produccion sin que nadie lo supiera.
"""

from __future__ import annotations

import pytest

from guia.nlp.cliente import AnalizadorNLP
from guia.routing.gates import LanguageGate, ToxicityGate


def _hubo_aviso(
    fragmento: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> bool:
    """¿Se registró el aviso, por la ruta que sea?

    El logging va por structlog, y segun como lo haya configurado otro test de
    la sesion escribe a stdout o propaga al logging estandar. Lo que se afirma
    aqui es que el aviso EXISTE, no por donde sale.
    """
    return fragmento in capsys.readouterr().out or fragmento in caplog.text


class _HTTPFalso:
    """Sustituye al cliente httpx del analizador."""

    def __init__(self, respuesta: object) -> None:
        self.respuesta = respuesta
        self.llamadas: list[dict] = []

    def post(self, url: str, json: dict) -> object:
        self.llamadas.append(json)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def close(self) -> None:
        pass


class _Respuesta:
    def __init__(self, datos: dict) -> None:
        self._datos = datos

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._datos


def _analizador(respuesta: object) -> tuple[AnalizadorNLP, _HTTPFalso]:
    a = AnalizadorNLP("http://embeddings:11434")
    http = _HTTPFalso(respuesta)
    a._http = http  # type: ignore[assignment]
    return a, http


class TestElGateUsaElSidecar:
    def test_la_toxicidad_se_pregunta_al_sidecar(self) -> None:
        analizador, http = _analizador(_Respuesta({"score": 0.97, "disponible": True}))
        gate = ToxicityGate(enabled=True, threshold=0.85, analizador=analizador)

        r = gate.evaluate("una consulta cualquiera")

        assert not r.passed
        assert http.llamadas == [{"op": "toxicity", "text": "una consulta cualquiera"}]

    def test_sin_analizador_sigue_usando_el_modelo_local(self) -> None:
        """La CLI y los tests corren sin sidecar; no pueden quedarse sin gate."""
        gate = ToxicityGate(enabled=True, threshold=0.85)

        assert gate._analizador is None

    def test_el_idioma_tambien(self) -> None:
        analizador, http = _analizador(
            _Respuesta({"lang": "qu", "confidence": 0.95, "disponible": True})
        )
        gate = LanguageGate(enabled=True, analizador=analizador)

        r = gate.evaluate("imaynalla kashanki")

        assert r.reason == "quechua_detected"
        assert http.llamadas[0]["op"] == "language"


class TestCuandoElSidecarFalla:
    def test_no_carga_el_modelo_local_de_reserva(self) -> None:
        """Cargarlo devolveria la memoria duplicada por la puerta de atras."""
        analizador, _ = _analizador(RuntimeError("connection refused"))

        assert analizador.toxicidad("hola") == 0.0
        assert analizador.entidades("hola") == {}
        assert analizador.corregir("nutricon") == "nutricon"
        assert analizador.idioma("hola") == ("es", 1.0)

    def test_deja_rastro_en_el_log(
        self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Un guardarrail que falla callado es peor que no tenerlo: se sigue
        contando con el. Es exactamente lo que paso con Detoxify.

        """
        analizador, _ = _analizador(RuntimeError("connection refused"))

        with caplog.at_level("WARNING"):
            analizador.toxicidad("hola")

        assert _hubo_aviso("nlp_sidecar_no_responde", capsys, caplog)

    def test_un_modelo_caido_en_el_sidecar_se_distingue_de_la_red(
        self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """El remedio es distinto: alli es la red, aqui es el modelo."""
        analizador, _ = _analizador(_Respuesta({"score": 0.0, "disponible": False}))

        with caplog.at_level("WARNING"):
            analizador.toxicidad("hola")

        assert _hubo_aviso("no_disponible_en_sidecar", capsys, caplog)


class TestElGateSigueBloqueando:
    @pytest.mark.parametrize(
        ("score", "bloquea"),
        [(0.97, True), (0.86, True), (0.85, True), (0.84, False), (0.36, False)],
    )
    def test_el_umbral_se_respeta_igual_que_en_local(
        self, score: float, bloquea: bool
    ) -> None:
        analizador, _ = _analizador(_Respuesta({"score": score, "disponible": True}))
        gate = ToxicityGate(enabled=True, threshold=0.85, analizador=analizador)

        assert gate.evaluate("x").passed is not bloquea
