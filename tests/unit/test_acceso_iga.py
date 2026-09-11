"""El IGA decide qué se le enseña a cada quien — y qué no, a nadie.

Hasta el 11-sep-2026 la identidad de MidPoint solo se usaba dentro del camino
personal: fuera de ahí, un Analista Programador de la DTI y un visitante
anónimo recibían la misma respuesta. Estas pruebas fijan el nivel de acceso y,
sobre todo, el límite que ningún nivel levanta.
"""

from __future__ import annotations

from guia.services.acceso_iga import (
    NivelDeAcceso,
    QuienPregunta,
    aporta_contexto,
    derivar_acceso,
)
from guia.services.identidad_institucional import IdentidadInstitucional

#: La ficha real que devuelve MidPoint, comprobada en producción.
_PERSONAL = IdentidadInstitucional(
    codigo="9610165",
    nombre_completo="Juan Alberto Sánchez",
    rol="Analista Programador",
    afiliacion="staff",
    nivel="Pregrado",
    campus="LIMA",
    unidades=("Dirección de Tecnologías de Información",),
)
_ESTUDIANTE = IdentidadInstitucional(
    codigo="201820001",
    nombre_completo="Persona Estudiante",
    rol="Estudiante",
    afiliacion="student",
    nivel="Pregrado",
    campus="LIMA",
    unidades=("Facultad de Ingeniería y Arquitectura",),
)


class TestNivelDeAcceso:
    def test_sin_sesion_es_publico(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado=None)

        assert quien.nivel is NivelDeAcceso.PUBLICO
        assert quien.puede_ver_lo_suyo is False

    def test_una_ficha_sin_correo_de_sesion_no_da_acceso(self) -> None:
        """Lo que decide es el correo de Keycloak, no la ficha. Pasarle una
        identidad sin sesión no puede abrir nada: sería la vía para consultar
        a un tercero."""
        quien = derivar_acceso(_PERSONAL, correo_verificado="   ")

        assert quien.nivel is NivelDeAcceso.PUBLICO
        assert quien.correo is None
        assert quien.unidades == ()

    def test_un_trabajador_llega_a_nivel_personal(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert quien.nivel is NivelDeAcceso.PERSONAL
        assert quien.rol == "Analista Programador"
        assert quien.area_principal == "Dirección de Tecnologías de Información"

    def test_un_estudiante_llega_a_comunidad(self) -> None:
        quien = derivar_acceso(_ESTUDIANTE, correo_verificado="alguien@upeu.edu.pe")

        assert quien.nivel is NivelDeAcceso.COMUNIDAD
        assert quien.puede_ver_lo_suyo is True

    def test_con_sesion_pero_sin_ficha_sigue_habiendo_sesion(self) -> None:
        """MidPoint no conoce a todo el mundo. Quedarse en público dejaría a
        esa persona sin sus propios datos; subirla de nivel no le da los de
        nadie más."""
        quien = derivar_acceso(
            None, correo_verificado="nuevo@upeu.edu.pe", nombre_verificado="Nuevo"
        )

        assert quien.nivel is NivelDeAcceso.COMUNIDAD
        assert quien.nombre == "Nuevo"
        assert quien.unidades == ()


class TestElLimiteQueNingunNivelLevanta:
    def test_ningun_nivel_expone_un_identificador_ajeno(self) -> None:
        """QuienPregunta se construye SIEMPRE desde el correo de la sesión.
        No hay campo ni parámetro por el que entre el de otra persona."""
        import inspect

        firma = inspect.signature(derivar_acceso)

        assert set(firma.parameters) == {
            "identidad",
            "correo_verificado",
            "nombre_verificado",
        }

    def test_el_nivel_publico_no_arrastra_datos(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado=None)

        assert quien.nombre is None
        assert quien.rol is None
        assert quien.codigo is None
        assert quien.campus is None


class TestContextoYCache:
    """Si la respuesta lleva contexto de quien pregunta, no puede cachearse.

    La caché es semántica y global: no distingue por usuario. Una respuesta
    que dice "tu área, la DTI" servida a la siguiente persona que preguntara
    algo parecido sería una fuga.
    """

    def test_mi_area_pide_contexto(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert aporta_contexto("de qué responde mi área", quien) is True
        assert aporta_contexto("cuáles son mis unidades", quien) is True

    def test_funciona_sin_tildes(self) -> None:
        """La gente escribe sin tildes, y de esta decisión depende la caché."""
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert aporta_contexto("de que responde mi area", quien) is True

    def test_a_quien_le_pido_pide_contexto(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert aporta_contexto("a quien le pido acceso a un sistema", quien) is True

    def test_una_busqueda_normal_no_pide_contexto(self) -> None:
        """Si no, ninguna respuesta de nadie con sesión se cachearía."""
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert aporta_contexto("tesis sobre estrés académico", quien) is False
        assert aporta_contexto("qué áreas tiene la universidad", quien) is False

    def test_sin_sesion_nunca_hay_contexto(self) -> None:
        anonimo = derivar_acceso(None, correo_verificado=None)

        assert aporta_contexto("de qué responde mi área", anonimo) is False

    def test_sin_unidades_no_hay_nada_que_aportar(self) -> None:
        """Con sesión pero sin ficha, "mi área" no se puede resolver: mejor
        no marcar la respuesta como personalizada y dejarla cachear."""
        sin_ficha = derivar_acceso(None, correo_verificado="nuevo@upeu.edu.pe")

        assert aporta_contexto("de qué responde mi área", sin_ficha) is False


class TestLoQueSeLeCuentaAlModelo:
    def test_el_contexto_nombra_area_cargo_y_campus(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        texto = quien.para_el_prompt() or ""

        assert "Analista Programador" in texto
        assert "Dirección de Tecnologías de Información" in texto
        assert "Lima" in texto  # campus en MidPoint viene en mayúsculas

    def test_sin_sesion_no_se_le_cuenta_nada(self) -> None:
        anonimo = derivar_acceso(None, correo_verificado=None)

        assert anonimo.para_el_prompt() is None

    def test_con_sesion_y_sin_datos_tampoco(self) -> None:
        """Una línea "QUIÉN PREGUNTA:" vacía solo gasta tokens."""
        pelado = QuienPregunta(nivel=NivelDeAcceso.COMUNIDAD, correo="x@upeu.edu.pe")

        assert pelado.para_el_prompt() is None

    def test_el_contexto_prohibe_atribuir_funciones_inventadas(self) -> None:
        """Mismo riesgo que con el mapa de procesos: el modelo rellena huecos."""
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        texto = quien.para_el_prompt() or ""

        assert "no le atribuyas" in texto


class TestUnaSolaConsultaAlIga:
    """La ficha se pide una vez por petición, no una por camino.

    Al derivar el nivel de acceso en cada mensaje, el directorio pasó a
    consultarse también fuera del camino personal. Sin reutilizar el
    resultado, una pregunta como "¿qué clases tengo hoy?" golpeaba MidPoint
    dos veces.
    """

    def test_la_ficha_viaja_dentro_de_quien_pregunta(self) -> None:
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert quien.ficha is _PERSONAL

    def test_sin_ficha_no_se_inventa(self) -> None:
        quien = derivar_acceso(None, correo_verificado="nuevo@upeu.edu.pe")

        assert quien.ficha is None

    def test_la_ficha_no_sale_en_el_repr(self) -> None:
        """Un repr con la ficha dentro acaba en un log el día menos pensado."""
        quien = derivar_acceso(_PERSONAL, correo_verificado="jsanchez@upeu.edu.pe")

        assert "9610165" not in repr(quien).replace("codigo='9610165'", "")
        assert "ficha=" not in repr(quien)
