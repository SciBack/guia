"""Identidad de los registros cosechados.

La propiedad que se defiende aquí es una sola: **el mismo registro de la misma
fuente debe producir el mismo id en cosechas distintas**. Cuando dejó de
cumplirse, cada cosecha insertó filas nuevas en vez de actualizar las
existentes, y el índice de UPeU acabó con 15.949 registros de OJS para 682
títulos distintos.
"""

from __future__ import annotations

from typing import Any

from guia.services.harvester import _stable_pub_id


class _Fecha:
    def __init__(self, year: int) -> None:
        self.year_int = year


class _Titulo:
    def __init__(self, valor: str) -> None:
        self.primary_value = valor
        self.primary_language = "es"


class _Id:
    def __init__(self, value: str, scheme: str = "") -> None:
        self.value = value
        self.scheme = scheme


class _Pub:
    """Publication mínima — solo lo que mira _stable_pub_id."""

    def __init__(
        self,
        *,
        titulo: str = "Hábitos de estudio y rendimiento académico",
        anio: int = 2021,
        publisher: str | None = "Universidad Peruana Unión",
        external_ids: list[_Id] | None = None,
        extra: dict[str, Any] | None = None,
        uuid: str = "019de4b8-b238-70f1-8949-82fc18459c2b",
    ) -> None:
        self.title = _Titulo(titulo)
        self.publication_date = _Fecha(anio)
        self.publisher = publisher
        self.external_ids = external_ids or []
        self.extra = extra or {}
        self.id = uuid


# ── La regresión que motivó todo esto ────────────────────────────────────────


def test_dos_cosechas_del_mismo_registro_dan_el_mismo_id() -> None:
    """SciBackBaseEntity genera un UUIDv7 nuevo en cada constructor.

    Antes ese UUID acababa dentro del id ('ojs:uuid:019de4b8-…'), así que dos
    cosechas del mismo artículo producían dos ids y, por tanto, dos filas.
    """
    extra = {"oai_identifier": "oai:revistas.upeu.edu.pe:article/1436"}
    primera = _Pub(extra=extra, uuid="019de4b8-b238-70f1-8949-82fc18459c2b")
    segunda = _Pub(extra=extra, uuid="019dfb08-6db3-7001-8982-fe4ea8f85039")

    assert _stable_pub_id(primera, "ojs", 1) == _stable_pub_id(segunda, "ojs", 2)


def test_el_uuid_generado_nunca_entra_en_el_id() -> None:
    """Ni siquiera cuando no hay ningún otro identificador disponible."""
    pub = _Pub(uuid="019de4b8-b238-70f1-8949-82fc18459c2b")

    generado = _stable_pub_id(pub, "ojs", 1)

    assert "019de4b8" not in generado
    assert ":uuid:" not in generado


def test_la_posicion_en_la_cosecha_no_influye() -> None:
    """El antiguo fallback ':idx:' dependía del orden de recorrido."""
    pub = _Pub()

    assert _stable_pub_id(pub, "ojs", 1) == _stable_pub_id(pub, "ojs", 9999)


# ── Orden de preferencia ─────────────────────────────────────────────────────


def test_gana_el_identificador_ya_prefijado_por_la_fuente() -> None:
    pub = _Pub(external_ids=[_Id("koha:12345")])

    assert _stable_pub_id(pub, "koha", 1) == "koha:12345"


def test_el_oai_va_por_delante_del_doi() -> None:
    """Es la corrección de fondo, no una preferencia estética.

    El DOI es estable pero no siempre está: el mismo artículo se cosechaba como
    'ojs:uuid:…' antes de tener DOI y como 'doi:10.17162/…' después, y esa
    divergencia creaba una fila más. El identificador OAI, en cambio, el
    protocolo lo obliga a existir y a no cambiar.
    """
    con_doi = _Pub(
        external_ids=[_Id("10.17162/rmi.v6i1.1436", scheme="DOI")],
        extra={"oai_identifier": "oai:revistas.upeu.edu.pe:article/1436"},
    )
    sin_doi = _Pub(extra={"oai_identifier": "oai:revistas.upeu.edu.pe:article/1436"})

    assert _stable_pub_id(con_doi, "ojs", 1) == _stable_pub_id(sin_doi, "ojs", 2)
    assert _stable_pub_id(con_doi, "ojs", 1).startswith("oai:")


def test_el_doi_se_usa_cuando_no_hay_oai() -> None:
    pub = _Pub(external_ids=[_Id("10.17162/rmi.v6i1.1436", scheme="IdentifierScheme.DOI")])

    assert _stable_pub_id(pub, "ojs", 1) == "doi:10.17162/rmi.v6i1.1436"


def test_el_handle_tambien_sirve() -> None:
    pub = _Pub(external_ids=[_Id("20.500.12840/1234", scheme="handle")])

    assert _stable_pub_id(pub, "dspace", 1) == "handle:20.500.12840/1234"


def test_la_url_es_el_ultimo_identificador_real() -> None:
    pub = _Pub(extra={"url": "https://revistas.upeu.edu.pe/index.php/rc/article/view/1436"})

    generado = _stable_pub_id(pub, "ojs", 1)

    assert generado.startswith("ojs:url:https://revistas.upeu.edu.pe/")


# ── Huella de contenido ──────────────────────────────────────────────────────


def test_sin_identificador_alguno_la_huella_es_estable() -> None:
    uno = _Pub()
    otro = _Pub()

    generado = _stable_pub_id(uno, "ojs", 1)

    assert generado == _stable_pub_id(otro, "ojs", 2)
    assert generado.startswith("ojs:sha1:")


def test_la_huella_ignora_tildes_mayusculas_y_espacios_de_mas() -> None:
    """Las fuentes reescriben el título sin que el registro cambie."""
    original = _Pub(titulo="Hábitos de Estudio y Rendimiento Académico")
    retocado = _Pub(titulo="  habitos  de estudio y rendimiento academico ")

    assert _stable_pub_id(original, "ojs", 1) == _stable_pub_id(retocado, "ojs", 2)


def test_la_huella_distingue_registros_distintos() -> None:
    uno = _Pub(titulo="Hábitos de estudio y rendimiento académico")
    otro = _Pub(titulo="Contaminación del lago Titicaca")

    assert _stable_pub_id(uno, "ojs", 1) != _stable_pub_id(otro, "ojs", 2)


def test_la_huella_distingue_el_ano() -> None:
    """El año entra en la huella; si se leyera mal, dos ediciones colapsarían."""
    edicion_2021 = _Pub(anio=2021)
    edicion_2024 = _Pub(anio=2024)

    assert _stable_pub_id(edicion_2021, "ojs", 1) != _stable_pub_id(edicion_2024, "ojs", 2)


def test_la_huella_separa_las_fuentes() -> None:
    """El mismo título en dos fuentes son dos registros, no uno."""
    pub = _Pub()

    assert _stable_pub_id(pub, "ojs", 1) != _stable_pub_id(pub, "koha", 1)
