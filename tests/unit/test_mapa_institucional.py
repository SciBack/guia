"""GUIA tiene que saber de qué responde cada área, no solo qué se ha publicado.

El 11-sep-2026, a "¿qué servicios ofrece la DTI?", GUIA contestaba que estaba
*fuera de su alcance* — y en la misma frase decía poder ayudar con "servicios
institucionales". No era un fallo del modelo: no existía ninguna fuente de
estructura institucional, y ninguna categoría de enrutado para la pregunta.

Estas pruebas fijan las dos mitades del arreglo: que el mapa del SGC se lea
bien, y que una pregunta por un área no acabe ni en Koha ni en el limbo.
"""

from __future__ import annotations

import pytest

from guia.routing import category_to_intent
from guia.routing.cascade import _category_to_tier_privacy
from guia.routing.decision import IntentCategory, PrivacyLevel
from guia.domain.chat import Intent
from guia.services.mapa_institucional import (
    AreaInstitucional,
    ClienteDelSGC,
    ProcesoInstitucional,
)


class _HttpFalso:
    """Responde lo que el SGC responde, con la forma que devuelve Frappe."""

    def __init__(self, por_doctype: dict[str, list[dict]]) -> None:
        self._por_doctype = por_doctype
        self.pedidos: list[tuple[str, dict]] = []

    def get(self, url: str, params=None, headers=None):  # noqa: ANN001, ARG002
        doctype = url.rsplit("/", 1)[-1].replace("%20", " ")
        self.pedidos.append((doctype, params or {}))
        datos = self._por_doctype.get(doctype, [])

        class _R:
            status_code = 200

            @staticmethod
            def json():
                return {"data": datos}

        return _R()

    def close(self) -> None:
        pass


def _cliente(areas: list[dict], procesos: list[dict]) -> ClienteDelSGC:
    c = ClienteDelSGC("https://calidad.upeu.edu.pe", "k", "s")
    c._http = _HttpFalso({"Unidad Organica": areas, "Proceso": procesos})  # type: ignore[assignment]
    return c


_AREAS = [
    {"name": "DTI", "nombre": "Dirección de Tecnologías de Información", "tipo": "Direccion"},
    {
        "name": "DTI-INFRA",
        "nombre": "DTI - Infraestructura Tecnologica",
        "parent_unidad_organica": "DTI",
    },
]
_PROCESOS = [
    {
        "codigo": "S04",
        "proceso": "Gestión tecnológica",
        "nivel": "Soporte",
        "propietario_unidad": "DTI",
        "estado": "Borrador",
    },
    {"codigo": "C02", "proceso": "Matrícula", "nivel": "Clave", "estado": "Aprobado"},
]


class TestLecturaDelMapa:
    def test_el_area_sabe_de_que_procesos_responde(self) -> None:
        """Es la pregunta que la gente hace: "¿de qué se encarga la DTI?"."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        dti = next(a for a in mapa.areas if a.codigo == "DTI")
        assert [p.codigo for p in dti.procesos] == ["S04"]
        assert "Gestión tecnológica" in dti.como_texto()

    def test_el_proceso_nombra_al_area_por_su_nombre_largo(self) -> None:
        """El SGC guarda el código (DTI); quien lee necesita el nombre."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        s04 = next(p for p in mapa.procesos if p.codigo == "S04")
        assert s04.area == "Dirección de Tecnologías de Información"

    def test_la_jerarquia_de_areas_se_resuelve(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        infra = next(a for a in mapa.areas if a.codigo == "DTI-INFRA")
        assert infra.padre == "Dirección de Tecnologías de Información"

    def test_el_texto_del_area_lleva_la_sigla(self) -> None:
        """Dentro de la universidad nadie dice "Dirección de Tecnologías de
        Información": dice "la DTI", y eso es lo que escribe al preguntar."""
        area = AreaInstitucional(codigo="DTI", nombre="Dirección de Tecnologías")

        assert "(DTI)" in area.como_texto()


class TestBorradoresYAvisos:
    def test_un_borrador_se_marca_como_tal(self) -> None:
        """Presentar un borrador como norma aprobada hace más daño que decir
        que aún no lo está: los 96 procesos siguen en borrador."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        s04 = next(p for p in mapa.procesos if p.codigo == "S04")
        assert s04.aprobado is False
        assert "borrador" in s04.como_texto().lower()

    def test_un_proceso_aprobado_no_lleva_la_advertencia(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        c02 = next(p for p in mapa.procesos if p.codigo == "C02")
        assert c02.aprobado is True
        assert "borrador" not in c02.como_texto().lower()

    def test_avisa_de_lo_que_falta_en_la_fuente(self) -> None:
        """70 de 96 procesos no tienen área: conviene que se note en el log,
        no descubrirlo cuando alguien pregunte."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        assert any("no tienen área propietaria" in a for a in mapa.avisos)

    def test_sin_credenciales_devuelve_un_mapa_vacio_y_no_revienta(self) -> None:
        """Un despliegue sin SGC —el caso de cualquier otra universidad— no
        puede romperse por esto."""
        vacio = ClienteDelSGC("https://calidad.upeu.edu.pe", "", "")

        mapa = vacio.mapa()

        assert mapa.esta_vacio

    def test_pide_el_doctype_entero(self) -> None:
        """Frappe pagina de 20 en 20 y devuelve 200 con la lista corta: sin
        limit_page_length=0 se cosecharían 20 de 96 sin que nada fallara."""
        c = _cliente(_AREAS, _PROCESOS)

        c.mapa()

        assert all(p[1].get("limit_page_length") == 0 for p in c._http.pedidos)  # type: ignore[attr-defined]


class TestEnrutadoInstitucional:
    def test_lo_institucional_va_al_indice_y_no_al_catalogo(self) -> None:
        """CAMPUS busca en Koha. Preguntar de qué se encarga un área no es
        buscar un libro: tiene que ir por GENERAL, que pasa por el índice —
        donde está el mapa del SGC."""
        assert category_to_intent(IntentCategory.INSTITUCIONAL) is Intent.GENERAL
        assert category_to_intent(IntentCategory.CAMPUS_GENERICO) is Intent.CAMPUS

    def test_el_mapa_institucional_puede_ir_a_la_nube(self) -> None:
        """Es información pública de la organización, no datos de nadie."""
        _tier, privacidad = _category_to_tier_privacy(IntentCategory.INSTITUCIONAL)

        assert privacidad is PrivacyLevel.CLOUD_OK

    def test_todas_las_categorias_tienen_destino(self) -> None:
        """Los mapeos son lookup directo: una categoría sin entrada es un
        KeyError en producción, no un default."""
        for categoria in IntentCategory:
            assert category_to_intent(categoria) is not None
            assert _category_to_tier_privacy(categoria) is not None


class TestProcesoSuelto:
    def test_un_proceso_sin_area_no_inventa_una(self) -> None:
        proceso = ProcesoInstitucional(codigo="C07", nombre="Perfil de egreso")

        texto = proceso.como_texto()

        assert "área responsable" not in texto
        assert "C07" in texto


class TestInventarioDeFuentes:
    """Las cifras que ve el modelo salen del índice, no de una constante.

    Las que había escritas a mano decían 12.500 artículos de OJS cuando hay
    744 y 550 eventos cuando hay 102. El modelo las repetía a quien preguntara
    qué fuentes tenía.
    """

    def test_sin_analitica_no_se_inventan_cifras(self) -> None:
        from guia.services.chat import inventario_de_fuentes

        texto = inventario_de_fuentes(None)

        assert "12,500" not in texto
        assert "34,900" not in texto
        assert "Koha" in texto  # sigue diciendo QUÉ hay, solo que sin números

    def test_con_analitica_salen_las_cifras_reales(self) -> None:
        from guia.services.analitica_del_indice import (
            AnaliticaDelIndice,
            FuenteIndexada,
        )
        from guia.services.chat import inventario_de_fuentes
        from datetime import UTC, datetime

        analitica = AnaliticaDelIndice(
            calculada_en=datetime.now(UTC),
            fuentes=(
                FuenteIndexada(clave="ojs", documentos=744, nombre="Revistas"),
                FuenteIndexada(clave="sgc", documentos=147, nombre="Mapa institucional"),
            ),
        )

        texto = inventario_de_fuentes(analitica)

        assert "744" in texto
        assert "147" in texto

    def test_el_ano_de_relleno_no_se_publica_como_cobertura(self) -> None:
        """El adaptador pone 1000 cuando el registro no trae fecha; decir que
        la cobertura empieza en el año 1000 es mentir con precisión."""
        from guia.services.analitica_del_indice import FuenteIndexada

        f = FuenteIndexada(clave="koha", documentos=10, nombre="Catálogo", anio_min=None)

        assert f.cobertura is None


class TestDsnDeLaAnalitica:
    """El DSN del proyecto está escrito para SQLAlchemy; psycopg no lo acepta.

    El error que devuelve —«missing "=" after …»— no se parece a su causa, y
    además escupe el DSN entero con la contraseña dentro al log de producción.
    """

    def test_quita_el_dialecto_de_sqlalchemy(self) -> None:
        from guia.services.analitica_del_indice import _dsn_para_psycopg

        limpio = _dsn_para_psycopg("postgresql+psycopg://u:p@host:5432/db")

        assert limpio == "postgresql://u:p@host:5432/db"

    def test_un_dsn_ya_limpio_no_se_toca(self) -> None:
        from guia.services.analitica_del_indice import _dsn_para_psycopg

        assert (
            _dsn_para_psycopg("postgresql://u:p@host/db")
            == "postgresql://u:p@host/db"
        )


class TestResumenDelMapa:
    """La pregunta que la gente hace primero es agregada, no puntual."""

    def test_el_resumen_cuenta_areas_y_procesos(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        resumen = mapa.resumen()

        assert "2 unidades orgánicas" in resumen
        assert "2 procesos" in resumen

    def test_el_resumen_lista_las_unidades_de_primer_nivel(self) -> None:
        """DTI-INFRA cuelga de DTI: en el listado de cabecera sobra."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        resumen = mapa.resumen()

        assert "Dirección de Tecnologías de Información (DTI)" in resumen
        assert "DTI-INFRA" not in resumen

    def test_el_resumen_agrupa_los_procesos_por_nivel(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        resumen = mapa.resumen()

        assert "Soporte: Gestión tecnológica" in resumen
        assert "Clave: Matrícula" in resumen


class TestElTextoQueSeEmbebe:
    """El vector se hace con la pregunta que el documento contesta.

    El resumen del mapa son 2.701 caracteres de nombres de direcciones y E5
    admite unos 1.500. Usándolo también como texto de embedding, la frase que
    responde a "¿qué áreas tiene la universidad?" quedaba ahogada: BM25 lo
    ponía **primero** y, tras fusionarlo con la rama vectorial —que pesa 0,7
    frente a 0,3—, caía al puesto 51 de 98. No lo hundía el reranker: entraba
    hundido.
    """

    def test_el_texto_de_busqueda_no_es_el_contenido(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        assert mapa.texto_para_buscar() != mapa.resumen()

    def test_el_texto_de_busqueda_cabe_en_el_embedder(self) -> None:
        from guia.services.harvester import _MAX_EMBEDDING_CHARS

        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        assert len(mapa.texto_para_buscar()) <= _MAX_EMBEDDING_CHARS

    def test_lleva_las_palabras_con_las_que_se_pregunta(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        texto = mapa.texto_para_buscar().lower()

        assert "qué áreas tiene la universidad" in texto
        assert "organigrama" in texto

    def test_el_contenido_completo_sigue_en_el_resumen(self) -> None:
        """La metadata es lossless: el modelo tiene que poder leerlo entero."""
        mapa = _cliente(_AREAS, _PROCESOS).mapa()

        assert "Dirección de Tecnologías de Información (DTI)" in mapa.resumen()

    def test_un_area_tambien_separa_los_dos_textos(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()
        dti = next(a for a in mapa.areas if a.codigo == "DTI")

        assert dti.texto_para_buscar() != dti.como_texto()
        assert "de qué se encarga" in dti.texto_para_buscar()

    def test_un_proceso_nombra_a_su_area_en_el_texto_de_busqueda(self) -> None:
        mapa = _cliente(_AREAS, _PROCESOS).mapa()
        s04 = next(p for p in mapa.procesos if p.codigo == "S04")

        assert "Dirección de Tecnologías de Información" in s04.texto_para_buscar()


class TestPesosDeLaFusion:
    """El reparto entre la rama léxica y la vectorial se configura y se mide.

    Estaba cableado en 0,3/0,7 como default de tres firmas distintas, así que
    no había forma de cambiarlo sin tocar código. El 11-sep-2026 se midió
    sobre un banco de 14 consultas con respuesta conocida y se movió a
    0,5/0,5: MRR final de 0,583 a 0,786, recall@5 del 71% al 86%.
    """

    def test_el_reparto_suma_uno(self) -> None:
        from guia.search.backend import SearchAdapter

        sa = SearchAdapter(object(), peso_lexico=0.3)

        assert sa._weights == (0.3, pytest.approx(0.7))

    def test_el_peso_configurado_se_respeta(self) -> None:
        from guia.search.backend import SearchAdapter

        sa = SearchAdapter(object(), peso_lexico=0.7)

        assert sa._weights == (0.7, pytest.approx(0.3))

    def test_el_default_es_el_medido(self) -> None:
        """Si alguien lo cambia sin medir, que al menos rompa un test.

        0,3 tras medir sobre 40 consultas. Estuvo en 0,5 unas horas, con un
        banco de 14 que solo tenía 4 semánticas: al ampliarlo, el resultado se
        dio la vuelta.
        """
        from guia.config import GUIASettings

        assert GUIASettings.model_fields["search_peso_lexico"].default == 0.3
