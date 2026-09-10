"""Un evento sin descripción solo se encuentra por su título.

Medido en el índice el 10-sep-2026: los 549 eventos de Indico entraban con el
título por todo contenido. El Event canónico no tenía dónde guardar la
descripción, y el texto del embedding se armaba con título + sede + tipo.

Los títulos de congresos y jornadas rara vez dicen de qué tratan ("XXVIII
Jornada de Investigación"), así que ese vector no representaba el contenido.
"""

from __future__ import annotations

from types import SimpleNamespace

from guia.services.harvester import _event_to_embedding_text, _event_to_metadata


def _evento(titulo: str, descripcion: str | None = None, sede: str | None = None):
    return SimpleNamespace(
        title=SimpleNamespace(primary_value=titulo),
        description=SimpleNamespace(primary_value=descripcion) if descripcion else None,
        venue=sede,
        kind=None,
    )


class TestElEmbeddingIncluyeLaDescripcion:
    def test_la_descripcion_entra_en_el_texto_del_vector(self) -> None:
        """Es lo que se recalcula al recosechar: el vector deja de ser el del título."""
        texto = _event_to_embedding_text(
            _evento(
                "XXVIII Jornada de Investigación",
                "Ponencias sobre resiliencia frente a fenómenos naturales en el altiplano",
            )
        )

        assert "resiliencia frente a fenómenos naturales" in texto
        assert "XXVIII Jornada" in texto

    def test_va_justo_despues_del_titulo(self) -> None:
        """El orden importa: el modelo trunca a 512 tokens."""
        texto = _event_to_embedding_text(
            _evento("Título", "La descripción", sede="Auditorio")
        )

        assert texto.index("La descripción") < texto.index("Auditorio")

    def test_un_evento_sin_descripcion_sigue_funcionando(self) -> None:
        """La mayoría de fuentes no la traen; no puede romperse por eso."""
        texto = _event_to_embedding_text(_evento("Solo título", sede="Teams"))

        assert "Solo título" in texto
        assert "Teams" in texto


class TestLosMetadatosLaGuardanComoAbstract:
    def test_se_guarda_bajo_la_clave_que_lee_el_resto(self) -> None:
        """OpenSearch, el render de fuentes y el reranker leen 'abstract'."""
        meta = _event_to_metadata(_evento("T", "El resumen del evento"))

        assert meta["abstract"] == "El resumen del evento"

    def test_sin_descripcion_no_inventa_la_clave(self) -> None:
        meta = _event_to_metadata(_evento("T"))

        assert "abstract" not in meta
