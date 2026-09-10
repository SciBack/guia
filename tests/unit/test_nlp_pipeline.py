"""Tests del pipeline NLP de preprocesamiento de queries (ADR-044)."""
from __future__ import annotations

import pytest


class TestGreetings:
    def test_strip_hola_inicio(self) -> None:
        from guia.nlp.greetings import strip_greetings
        result = strip_greetings("hola, ¿tienes libros sobre excel?")
        assert "hola" not in result.lower()
        assert "excel" in result.lower()

    def test_strip_buenos_dias(self) -> None:
        from guia.nlp.greetings import strip_greetings
        result = strip_greetings("buenos días, busco tesis de IA")
        assert "buenos" not in result.lower()
        assert "tesis" in result.lower()

    def test_preserva_query_sin_saludo(self) -> None:
        from guia.nlp.greetings import strip_greetings
        query = "libros de cálculo diferencial"
        assert strip_greetings(query) == query

    def test_strip_gracias_final(self) -> None:
        from guia.nlp.greetings import strip_greetings
        result = strip_greetings("busco tesis de machine learning gracias")
        assert "gracias" not in result.lower()
        assert "machine learning" in result.lower()

    def test_query_solo_saludo(self) -> None:
        from guia.nlp.greetings import strip_greetings
        result = strip_greetings("hola")
        assert result.strip() == ""


class TestAcronyms:
    def test_expand_ia(self) -> None:
        from guia.nlp.acronyms import expand_acronyms
        result = expand_acronyms("tesis sobre IA en educación")
        assert "inteligencia artificial" in result.lower()

    def test_expand_tic(self) -> None:
        from guia.nlp.acronyms import expand_acronyms
        result = expand_acronyms("proyectos de TIC")
        assert "tecnolog" in result.lower()

    def test_preserva_texto_sin_siglas(self) -> None:
        from guia.nlp.acronyms import expand_acronyms
        text = "libros de matemáticas"
        result = expand_acronyms(text)
        assert "matemáticas" in result

    def test_preserva_siglas_desconocidas(self) -> None:
        from guia.nlp.acronyms import expand_acronyms
        result = expand_acronyms("proyectos XYZQ")
        assert "XYZQ" in result


class TestDater:
    def test_año_pasado(self) -> None:
        from guia.nlp.dater import extract_date_filters
        from datetime import date
        result = extract_date_filters("tesis del año pasado")
        assert result is not None
        assert "gte" in result
        expected_year = date.today().year - 1
        assert str(expected_year) in result["gte"]

    def test_rango_explicito(self) -> None:
        from guia.nlp.dater import extract_date_filters
        result = extract_date_filters("artículos de 2020-2023")
        assert result is not None
        assert "gte" in result and "lte" in result
        assert "2020" in result["gte"]
        assert "2023" in result["lte"]

    def test_sin_fecha(self) -> None:
        from guia.nlp.dater import extract_date_filters
        result = extract_date_filters("libros de cálculo diferencial")
        assert result is None

    def test_este_anio(self) -> None:
        from guia.nlp.dater import extract_date_filters
        from datetime import date
        result = extract_date_filters("publicaciones de este año")
        assert result is not None
        assert str(date.today().year) in result["gte"]


class TestLanguage:
    def test_espanol_pass(self) -> None:
        from guia.nlp.language import detect_language
        lang, _ = detect_language("¿Qué libros de matemáticas tienen?")
        assert lang == "es"

    def test_texto_vacio_es_espanol(self) -> None:
        from guia.nlp.language import detect_language
        lang, conf = detect_language("")
        assert lang == "es"

    def test_distingue_de_verdad_y_no_solo_degrada_a_espanol(self) -> None:
        """El test que faltaba, y por el que el fallo pasó desapercibido.

        Los dos de arriba pasan igual con el detector roto: cuando no puede
        cargar, este módulo devuelve ("es", 1.0), que es exactamente lo que
        comprueban. Y roto estuvo — desde que se movió al sidecar hasta el
        10-sep-2026 — porque NumPy 2 rompió fasttext.

        Un idioma que NO sea español no lo puede fingir el fallback.
        """
        from guia.nlp.language import detect_language

        lang, score = detect_language("I need books about child nutrition for my thesis")
        assert lang == "en", "si sale 'es' aquí, el detector está degradado"
        assert score > 0.5

    def test_el_parche_de_numpy_no_se_escapa_del_modulo_de_fasttext(self) -> None:
        """El parche es quirúrgico a propósito.

        Los embeddings y el reranker también usan NumPy en este mismo proceso.
        Aflojar np.array para todos habría cambiado su comportamiento en
        silencio, que es peor que el problema que se venía a resolver.
        """
        import numpy as np

        from guia.nlp.language import detect_language

        detect_language("hola, necesito libros de nutrición")  # fuerza la carga

        with pytest.raises(ValueError):
            np.array([1, 2, 3], copy=False)


class TestKeywords:
    def test_extrae_keywords(self) -> None:
        from guia.nlp.keywords import expand_keywords
        result = expand_keywords("tesis sobre inteligencia artificial en educación peruana")
        assert isinstance(result, list)

    def test_texto_corto_retorna_vacio(self) -> None:
        from guia.nlp.keywords import expand_keywords
        result = expand_keywords("IA")
        assert result == []
