"""Quién es, según MidPoint — la fuente canónica de identidad de la UPeU.

Por qué hacía falta. GUIA resolvía la identidad contra el plugin
``academic_identity`` de Indico, y ahí solo había **298 personas de 8.364**
usuarios (medido el 11-sep-2026). Para el 96% de la gente, GUIA respondía "no
encuentro nada tuyo" — que es lo que se veía desde fuera como "no funciona".

MidPoint tiene la ficha de todas. Y no hizo falta abrir nada: existe desde el
01-jul-2026 una cuenta de servicio creada para exactamente esto,
``svc-ai-identity``, de **solo lectura** y con una allow-list de 12 campos que
deja fuera DNI, fecha de nacimiento, foto y credenciales. Es decir, el propio
MidPoint garantiza la minimización de datos; GUIA no podría pedir de más
aunque el código lo intentara.

Lo que se obtiene, y para qué sirve cada cosa:

- ``name`` — el **código universitario**. Es la llave que pide el servicio de
  horarios, que no acepta correos (comprobado: con el correo devuelve
  ``found: false``, con el código devuelve las clases del día).
- ``fullName`` — para dirigirse a la persona por su nombre.
- ``title`` / ``primaryAffiliation`` — "Estudiante" / ``student``.
- ``studyLevel`` — "Pregrado".

Se habla por la URL **pública** (``identity.upeu.edu.pe``) y no por la
interna: desde el contenedor de GUIA la interna no responde y la pública sí
—comprobado—, porque el 8080 de MidPoint no está abierto hacia este servidor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from guia.logging import get_logger

logger = get_logger(__name__)

#: Filtro de búsqueda por correo. MidPoint habla XML aquí aunque responda JSON.
_CONSULTA = """\
<query xmlns="http://prism.evolveum.com/xml/ns/public/query-3">
  <filter><equal><path>emailAddress</path><value>{correo}</value></equal></filter>
</query>"""


@dataclass(frozen=True)
class IdentidadInstitucional:
    """Lo que MidPoint sabe de una persona, dentro de lo permitido."""

    codigo: str | None
    """El código universitario. Es lo que abre el horario de clases."""

    nombre_completo: str | None
    rol: str | None
    """"Estudiante", "Docente"… tal como lo escribe MidPoint."""

    afiliacion: str | None
    """``student`` / ``faculty`` / ``staff`` — el valor eduPerson."""

    nivel: str | None
    """"Pregrado", "Posgrado"… Ojo: en el personal suele venir poblado con
    los estudios que hizo en la propia universidad, así que **no significa
    que esté matriculado**. Solo se enseña a quien es estudiante."""

    campus: str | None
    """"LIMA", "JULIACA", "TARAPOTO" — de ``campusWorker``."""

    unidades: tuple[str, ...] = ()
    """Las organizaciones a las que pertenece: el área de trabajo, la facultad.

    **No sale de ``organizationalUnit``.** Ese campo lleva el vínculo
    académico —la facultad del estudiante, poblada por dos mappings desde los
    recursos de alumnos— y el área laboral viaja por otro sitio:
    ``parentOrgRef``, que apunta a la ``OrgType`` del área. Comprobado el
    11-sep-2026: un Analista Programador de la DTI tiene
    ``organizationalUnit`` vacío y un ``parentOrgRef`` a la org "DTI".

    Por eso aquí se resuelven las referencias en vez de leer el campo. Puede
    haber más de una en quien es a la vez trabajador y egresado."""

    @property
    def es_estudiante(self) -> bool:
        return (self.afiliacion or "").lower() == "student"

    @property
    def es_personal(self) -> bool:
        """Personal administrativo o docente.

        Importa porque el horario de clases no aplica: a un trabajador no se
        le pregunta por su matrícula, y GUIA se lo estaba diciendo.
        """
        return (self.afiliacion or "").lower() in ("staff", "faculty", "employee")


def _campo(texto: str, nombre: str) -> str | None:
    """Saca un campo del JSON de MidPoint sin depender de su anidamiento.

    La respuesta viene envuelta en varias capas de ``@ns``/``@type`` que
    cambian entre versiones; buscar el campo por nombre es más estable que
    recorrer la estructura, y aquí solo se leen cadenas simples.
    """
    m = re.search(rf'"{nombre}"\s*:\s*"([^"]*)"', texto)
    return m.group(1) if m and m.group(1).strip() else None


def _oids_de_orgs(texto: str) -> list[str]:
    """Los OID de las organizaciones a las que pertenece la persona.

    Se leen de ``parentOrgRef``, que es donde MidPoint materializa la
    pertenencia y respeta la vigencia de la asignación.
    """
    return re.findall(
        r'"parentOrgRef"[^}]*?"oid"\s*:\s*"([0-9a-f-]{36})"', texto, re.S
    )


class DirectorioInstitucional:
    """Consulta MidPoint por correo. Solo lectura, solo la persona que entró.

    Args:
        base_url: Raíz de MidPoint (``https://identity.upeu.edu.pe/midpoint``).
        usuario: La cuenta de servicio ``svc-ai-identity``.
        clave: Su contraseña.
        timeout: Techo por consulta. Corto: esto va en el camino de una
            respuesta de chat.
    """

    def __init__(
        self,
        base_url: str,
        usuario: str,
        clave: str,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/ws/rest/users/search"
        self._auth = (usuario, clave)
        self._http = httpx.Client(timeout=timeout)

    @property
    def configurado(self) -> bool:
        return bool(self._auth[0] and self._auth[1] and self._url.startswith("http"))

    def _nombre_de_la_org(self, oid: str) -> str | None:
        """Resuelve una referencia a organización a su nombre legible.

        La cuenta de servicio solo alcanza ``name``, ``displayName`` e
        ``identifier`` de las orgs — ni managers, ni inducements, ni
        políticas. Lo justo para poder nombrarla.
        """
        try:
            r = self._http.get(
                self._url.replace("/users/search", f"/orgs/{oid}"),
                auth=self._auth,
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            logger.warning("midpoint_org_no_responde", error=str(exc))
            return None
        if r.status_code != 200:
            return None
        # displayName es el nombre para personas ("Dirección de Tecnologías
        # de Información"); name es el técnico ("DTI"). Se prefiere el largo.
        return _campo(r.text, "displayName") or _campo(r.text, "name")

    def de_quien_ha_iniciado_sesion(  # noqa: PLR0911 — ídem: cada salida es un caso distinto en el log
        self, correo_verificado: str
    ) -> IdentidadInstitucional | None:
        """La ficha del titular de ese correo, o ``None``.

        Args:
            correo_verificado: El correo que devolvió Keycloak tras el login de
                M365. **Nunca** un dato sacado del texto del chat — misma regla
                que en el resto de caminos que tocan datos personales: el
                identificador no puede venir de lo que alguien escriba.
        """
        if not self.configurado:
            logger.warning("midpoint_sin_configurar")
            return None

        correo = (correo_verificado or "").strip()
        # El correo se interpola en un XML: un valor con "<" rompería la
        # consulta, y aunque la cuenta es de solo lectura, no se construye
        # markup con datos sin comprobar.
        if not correo or not re.fullmatch(r"[\w.+-]+@[\w.-]+", correo):
            return None

        try:
            r = self._http.post(
                self._url,
                auth=self._auth,
                headers={"Content-Type": "application/xml", "Accept": "application/json"},
                content=_CONSULTA.format(correo=correo).encode(),
            )
        except Exception as exc:
            logger.warning("midpoint_no_responde", error=str(exc))
            return None

        if r.status_code == 401:
            logger.error("midpoint_credenciales_rechazadas")
            return None
        if r.status_code != 200:
            logger.warning("midpoint_respuesta_inesperada", codigo=r.status_code)
            return None

        texto = r.text
        if '"emailAddress"' not in texto:
            # Búsqueda sin resultados: MidPoint devuelve 200 con la lista vacía.
            return None

        unidades = tuple(
            n
            for n in (
                self._nombre_de_la_org(oid)
                for oid in dict.fromkeys(_oids_de_orgs(texto))
            )
            if n
        )

        return IdentidadInstitucional(
            codigo=_campo(texto, "name"),
            nombre_completo=_campo(texto, "fullName"),
            rol=_campo(texto, "title"),
            afiliacion=_campo(texto, "primaryAffiliation"),
            nivel=_campo(texto, "studyLevel"),
            campus=_campo(texto, "campusWorker"),
            unidades=unidades,
        )

    def cerrar(self) -> None:
        self._http.close()
