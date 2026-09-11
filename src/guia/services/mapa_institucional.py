"""Qué áreas tiene la universidad y de qué procesos responde cada una.

Por qué existe. GUIA nació como buscador de documentos y se presentaba como
"el asistente de la biblioteca". A la pregunta "¿qué servicios ofrece la DTI?"
contestaba, literalmente, que estaba *fuera de su alcance* — y en la misma
frase decía poder ayudar con "servicios institucionales". Prometía lo que no
tenía: no existía ninguna fuente de estructura institucional.

La fuente es el **SGC** (``calidad.upeu.edu.pe``), que es donde vive el mapa de
procesos aprobado por la Dirección de Planificación y Gestión de la Calidad.
De ahí salen dos cosas, y solo dos:

- ``Unidad Organica`` — las áreas, en árbol (la DTI y debajo DTI-INFRA,
  DTI-DEV, DTI-MESA, DTI-RSL).
- ``Proceso`` — el mapa v8.0, también en árbol: macroproceso → proceso →
  subproceso, cada uno con su nivel (Estratégico / Clave / Soporte) y, cuando
  está asignado, el área propietaria.

**Lo que esta fuente NO es, y conviene tenerlo claro antes de prometerlo.**
Medido el 11-sep-2026 contra el SGC en producción: 96 procesos, de los que 26
tienen área propietaria y **ninguno tiene responsable**; las fichas de
caracterización (SIPOC) no se han entregado todavía, y los 96 están en estado
``Borrador``. Es decir: sirve para responder "de qué responde la DTI", no para
responder "dónde tramito mi constancia". Ese segundo nivel llegará cuando la
DPGC entregue las fichas; hasta entonces GUIA no debe inventarlo.

Por eso cada documento viaja con su ``estado`` y esta capa marca lo que aún es
borrador. Un asistente que presenta un borrador como norma aprobada hace más
daño que uno que dice "todavía no está aprobado".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from guia.logging import get_logger

logger = get_logger(__name__)

#: Niveles del mapa de procesos, con lo que significan para quien pregunta.
_QUE_ES_EL_NIVEL = {
    "Estratégico": "define el rumbo de la universidad",
    "Clave": "es parte de la cadena de valor académica",
    "Soporte": "sostiene a los demás procesos",
}


@dataclass(frozen=True)
class AreaInstitucional:
    """Una unidad orgánica: una dirección, una oficina, una unidad."""

    codigo: str
    nombre: str
    tipo: str | None = None
    sede: str | None = None
    padre: str | None = None
    procesos: tuple[ProcesoInstitucional, ...] = ()

    def como_texto(self) -> str:
        """Lo que se indexa y lo que lee el modelo.

        Incluye el código además del nombre porque dentro de la universidad la
        gente dice "la DTI", no "la Dirección de Tecnologías de la
        Información", y quien pregunta escribe la sigla.
        """
        partes = [f"{self.nombre} ({self.codigo})"]
        if self.tipo:
            partes.append(f"Tipo: {self.tipo}.")
        if self.sede:
            partes.append(f"Sede: {self.sede}.")
        if self.padre:
            partes.append(f"Depende de {self.padre}.")
        if self.procesos:
            nombres = ", ".join(p.nombre for p in self.procesos)
            partes.append(f"Responde de estos procesos institucionales: {nombres}.")
        return " ".join(partes)


@dataclass(frozen=True)
class ProcesoInstitucional:
    """Un proceso del mapa: "Gestión tecnológica", "Matrícula"."""

    codigo: str
    nombre: str
    nivel: str | None = None
    nivel_bpm: str | None = None
    area: str | None = None
    padre: str | None = None
    estado: str | None = None
    aprobado: bool = False

    def como_texto(self) -> str:
        partes = [f"{self.nombre} ({self.codigo})"]
        if self.nivel:
            glosa = _QUE_ES_EL_NIVEL.get(self.nivel)
            partes.append(
                f"Proceso de nivel {self.nivel}"
                + (f", que {glosa}." if glosa else ".")
            )
        if self.area:
            partes.append(f"El área responsable es {self.area}.")
        if self.padre:
            partes.append(f"Forma parte de {self.padre}.")
        if not self.aprobado:
            partes.append(
                "Este proceso todavía está en borrador dentro del sistema de "
                "gestión de la calidad: la denominación es la oficial, pero su "
                "ficha detallada aún no está aprobada."
            )
        return " ".join(partes)


@dataclass(frozen=True)
class MapaInstitucional:
    """La foto completa: áreas y procesos, ya cruzados entre sí."""

    areas: tuple[AreaInstitucional, ...] = ()
    procesos: tuple[ProcesoInstitucional, ...] = ()
    avisos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def esta_vacio(self) -> bool:
        return not self.areas and not self.procesos

    def resumen(self) -> str:
        """Un solo texto con el mapa entero, para las preguntas agregadas.

        "¿Qué áreas tiene la universidad?" no se responde buscando documento a
        documento: cada área es un documento suyo y ninguno contiene la lista.
        Comprobado el 11-sep-2026 — con las 51 áreas indexadas, esa pregunta
        devolvía documentos sobre universidades en general.

        Así que el mapa se indexa también entero, como un documento más. Es la
        respuesta a la pregunta que la gente hace primero.
        """
        direcciones = [a for a in self.areas if not a.padre]
        lineas = [
            "Áreas y estructura de la Universidad Peruana Unión. "
            f"La universidad tiene {len(self.areas)} unidades orgánicas "
            f"—direcciones, oficinas y unidades— y {len(self.procesos)} "
            "procesos en su mapa de procesos institucional.",
            "",
            "Unidades principales:",
        ]
        lineas += [
            f"- {a.nombre} ({a.codigo})" + (f", {a.tipo}" if a.tipo else "")
            for a in direcciones
        ]

        por_nivel: dict[str, list[str]] = {}
        for pr in self.procesos:
            if pr.nivel:
                por_nivel.setdefault(pr.nivel, []).append(pr.nombre)
        if por_nivel:
            lineas += ["", "Procesos por nivel:"]
            for nivel, nombres in por_nivel.items():
                lineas.append(f"- {nivel}: {', '.join(nombres[:12])}")
        return "\n".join(lineas)


def _texto(valor: object) -> str | None:
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


class ClienteDelSGC:
    """Lee el mapa de procesos del SGC. Solo lectura.

    Args:
        base_url: Raíz del SGC (``https://calidad.upeu.edu.pe``).
        api_key: Par ``key`` de la credencial de API de Frappe.
        api_secret: Par ``secret``.
        timeout: Techo por consulta. Generoso: esto corre en la cosecha
            nocturna, no en el camino de una respuesta de chat.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._auth = f"token {api_key}:{api_secret}"
        self._http = httpx.Client(timeout=timeout)

    @property
    def configurado(self) -> bool:
        return bool(self._base.startswith("http") and "token :" not in self._auth)

    def _listar(self, doctype: str, campos: list[str]) -> list[dict]:
        """Trae un doctype entero.

        Frappe pagina de 20 en 20 por defecto y devuelve 200 con la lista
        corta, sin avisar de que falta el resto; ``limit_page_length=0`` es lo
        que pide todo. El mapa son ~150 documentos, así que cabe de una vez.
        """
        import json

        try:
            r = self._http.get(
                f"{self._base}/api/resource/{doctype.replace(' ', '%20')}",
                params={"fields": json.dumps(campos), "limit_page_length": 0},
                headers={"Authorization": self._auth, "Accept": "application/json"},
            )
        except Exception as exc:
            logger.warning("sgc_no_responde", doctype=doctype, error=str(exc))
            return []

        if r.status_code != 200:
            logger.warning(
                "sgc_respuesta_inesperada", doctype=doctype, codigo=r.status_code
            )
            return []
        try:
            datos = r.json().get("data")
        except ValueError:
            logger.warning("sgc_respuesta_no_es_json", doctype=doctype)
            return []
        return datos if isinstance(datos, list) else []

    def mapa(self) -> MapaInstitucional:
        """Áreas y procesos, ya cruzados.

        Se cruzan aquí y no en quien consulta porque la pregunta que la gente
        hace es "¿de qué responde tal área?", y eso exige recorrer los procesos
        buscando su propietario. Hacerlo una vez por cosecha es gratis;
        hacerlo por consulta, no.
        """
        if not self.configurado:
            logger.warning("sgc_sin_configurar")
            return MapaInstitucional()

        crudo_areas = self._listar(
            "Unidad Organica",
            ["name", "nombre", "tipo", "sede", "parent_unidad_organica"],
        )
        crudo_procesos = self._listar(
            "Proceso",
            [
                "codigo",
                "proceso",
                "nivel",
                "nivel_bpm",
                "propietario_unidad",
                "parent_proceso",
                "estado",
            ],
        )

        nombre_de = {
            _texto(a.get("name")): _texto(a.get("nombre")) or _texto(a.get("name"))
            for a in crudo_areas
            if _texto(a.get("name"))
        }
        nombre_proceso_de = {
            _texto(p.get("codigo")): _texto(p.get("proceso"))
            for p in crudo_procesos
            if _texto(p.get("codigo"))
        }

        procesos: list[ProcesoInstitucional] = []
        for p in crudo_procesos:
            codigo = _texto(p.get("codigo"))
            nombre = _texto(p.get("proceso"))
            if not codigo or not nombre:
                continue
            unidad = _texto(p.get("propietario_unidad"))
            padre = _texto(p.get("parent_proceso"))
            estado = _texto(p.get("estado"))
            procesos.append(
                ProcesoInstitucional(
                    codigo=codigo,
                    nombre=nombre,
                    nivel=_texto(p.get("nivel")),
                    nivel_bpm=_texto(p.get("nivel_bpm")),
                    area=nombre_de.get(unidad, unidad),
                    padre=nombre_proceso_de.get(padre, padre),
                    estado=estado,
                    aprobado=(estado or "").lower() in ("aprobado", "vigente"),
                )
            )

        # Un proceso cuenta para su área propietaria y también para las áreas
        # que cuelgan de ella: si la DTI es dueña de "Gestión tecnológica",
        # preguntar por DTI-INFRA tiene que llegar al mismo sitio.
        por_area: dict[str, list[ProcesoInstitucional]] = {}
        for pr in procesos:
            if pr.area:
                por_area.setdefault(pr.area, []).append(pr)

        areas: list[AreaInstitucional] = []
        for a in crudo_areas:
            codigo = _texto(a.get("name"))
            if not codigo:
                continue
            nombre = _texto(a.get("nombre")) or codigo
            padre_codigo = _texto(a.get("parent_unidad_organica"))
            areas.append(
                AreaInstitucional(
                    codigo=codigo,
                    nombre=nombre,
                    tipo=_texto(a.get("tipo")),
                    sede=_texto(a.get("sede")),
                    padre=nombre_de.get(padre_codigo, padre_codigo),
                    procesos=tuple(por_area.get(nombre, ())),
                )
            )

        avisos: list[str] = []
        sin_area = sum(1 for p in procesos if not p.area)
        if sin_area:
            avisos.append(
                f"{sin_area} de {len(procesos)} procesos no tienen área "
                "propietaria asignada en el SGC."
            )
        borradores = sum(1 for p in procesos if not p.aprobado)
        if borradores:
            avisos.append(
                f"{borradores} de {len(procesos)} procesos siguen en borrador."
            )

        logger.info(
            "sgc_mapa_leido",
            areas=len(areas),
            procesos=len(procesos),
            procesos_con_area=len(procesos) - sin_area,
        )
        return MapaInstitucional(
            areas=tuple(areas), procesos=tuple(procesos), avisos=tuple(avisos)
        )

    def cerrar(self) -> None:
        self._http.close()
