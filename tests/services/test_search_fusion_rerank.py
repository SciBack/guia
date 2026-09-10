

class TestQueTextoVeElCrossEncoder:
    """Cuánto se le manda por documento, y por qué tan poco.

    Medido el 10-sep-2026 sobre 12 consultas reales con 30 candidatos cada
    una, puntuando la relevancia del top-5 con un juez: mandar el resumen
    entero costaba 2,66 s y sacaba 2,35/3; recortarlo a 300 caracteres cuesta
    0,48 s y saca 2,50/3. Más rápido *y* mejor — probablemente porque los
    resúmenes largos de las tesis diluyen la señal del título dentro de la
    ventana del modelo.
    """

    def test_el_titulo_va_entero_aunque_sea_largo(self) -> None:
        """Recortar título y resumen juntos castigaba a los títulos largos.

        El título es lo más informativo que tiene el cross-encoder para
        decidir; el recorte cae solo sobre el resumen.
        """
        from guia.search.rerank import _hit_to_text

        titulo = "Hábitos de estudio y rendimiento académico en estudiantes " * 3
        texto = _hit_to_text({"title": titulo.strip(), "abstract": "x " * 500})

        assert texto.startswith(titulo.strip())

    def test_el_resumen_se_recorta(self) -> None:
        from guia.search.rerank import _RESUMEN_MAX_CHARS, _hit_to_text

        texto = _hit_to_text({"title": "T", "abstract": "palabra " * 300})

        assert len(texto) < 400
        assert len(texto) > _RESUMEN_MAX_CHARS - 50

    def test_no_parte_la_ultima_palabra(self) -> None:
        """Un token cortado a la mitad es ruido para el modelo."""
        from guia.search.rerank import _hit_to_text

        texto = _hit_to_text({"title": "T", "abstract": "antidisestablishmentarianism " * 40})

        assert not texto.endswith("antidis")
        assert texto.split()[-1] == "antidisestablishmentarianism"

    def test_un_resumen_corto_no_se_toca(self) -> None:
        from guia.search.rerank import _hit_to_text

        assert _hit_to_text({"title": "Título", "abstract": "Resumen breve."}) == (
            "Título. Resumen breve."
        )

    def test_sin_resumen_va_solo_el_titulo(self) -> None:
        from guia.search.rerank import _hit_to_text

        assert _hit_to_text({"title": "Solo título", "abstract": ""}) == "Solo título"
        assert _hit_to_text({"title": "Solo título"}) == "Solo título"
