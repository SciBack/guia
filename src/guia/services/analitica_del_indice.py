"""Qué tiene GUIA indexado, contado del índice y no de memoria.

Por qué existe. El endpoint de transparencia (ADR-047, exigido por el DS
115-2025-PCM) publicaba el inventario **escrito a mano**, y el 11-sep-2026
tres de sus cuatro cifras eran falsas: decía 12.500 artículos de OJS cuando
hay 744, 550 eventos de Indico cuando hay 102, y no mencionaba el CRIS, que
son 1.996 publicaciones. No es un descuido puntual: una lista escrita a mano
envejece en cuanto alguien cosecha algo, y nadie se entera porque no falla.

Un dato de transparencia que hay que recordar actualizar no es transparencia.
Así que se cuenta del índice, cada vez.

Y sirve para dos cosas más, ambas pedidas: que GUIA pueda **responder qué
tiene** cuando se lo preguntan —"¿qué información manejas?"— y que se pueda
ver de un vistazo si una cosecha dejó una fuente a medias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from guia.logging import get_logger

logger = get_logger(__name__)

#: Cómo se llama cada fuente de cara a una persona. Una fuente que no esté
#: aquí se muestra con su etiqueta técnica: es preferible a ocultarla.
_COMO_SE_LLAMA = {
    "koha": ("Catálogo de la biblioteca", "libros, tesis impresas y material del CRAI"),
    "dspace": ("Repositorio institucional", "tesis y trabajos de investigación"),
    "cris": ("Producción científica (CRIS)", "artículos y publicaciones de los investigadores"),
    "ojs": ("Revistas científicas UPeU", "artículos publicados en las revistas de la universidad"),
    "indico": ("Eventos", "congresos, jornadas y actividades académicas"),
    "sgc": ("Mapa institucional", "áreas de la universidad y los procesos de los que responde cada una"),
    "alicia": ("ALICIA — CONCYTEC", "producción científica nacional"),
}


@dataclass(frozen=True)
class FuenteIndexada:
    """Lo que hay de una fuente."""

    clave: str
    documentos: int
    nombre: str
    descripcion: str = ""
    anio_min: int | None = None
    anio_max: int | None = None

    @property
    def cobertura(self) -> str | None:
        if self.anio_min and self.anio_max:
            if self.anio_min == self.anio_max:
                return str(self.anio_min)
            return f"{self.anio_min}–{self.anio_max}"
        return None


@dataclass(frozen=True)
class AnaliticaDelIndice:
    """La foto del índice en un momento dado."""

    calculada_en: datetime
    fuentes: tuple[FuenteIndexada, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return sum(f.documentos for f in self.fuentes)

    def para_transparencia(self) -> list[dict[str, object]]:
        """El bloque ``data_sources`` del endpoint público."""
        return [
            {
                "name": f.nombre,
                "key": f.clave,
                "type": f.descripcion,
                "records": f.documentos,
                "coverage": f.cobertura,
            }
            for f in self.fuentes
        ]

    def como_texto(self) -> str:
        """Lo que GUIA puede decir cuando le preguntan qué sabe.

        En prosa y con los números redondeados a la baja: quien pregunta
        quiere hacerse una idea del tamaño, no auditar el índice. Decir
        "34.971" invita a creer que la cifra es exacta al documento, y cambia
        con cada cosecha.
        """
        if not self.fuentes:
            return "Ahora mismo no tengo nada indexado."

        def redondea(n: int) -> str:
            if n >= 1000:
                return f"más de {n // 1000} mil"
            if n >= 100:
                return f"más de {n // 100 * 100}"
            return str(n)

        piezas = []
        for f in self.fuentes:
            cob = f" ({f.cobertura})" if f.cobertura else ""
            piezas.append(f"{f.nombre}: {redondea(f.documentos)} registros{cob}")
        return (
            f"Tengo indexados {redondea(self.total)} registros de "
            f"{len(self.fuentes)} fuentes de la universidad — " + "; ".join(piezas) + "."
        )


def _dsn_para_psycopg(dsn: str) -> str:
    """Quita el dialecto de SQLAlchemy de la cadena de conexión.

    ``pgvector_database_url`` está escrita para SQLAlchemy
    (``postgresql+psycopg://…``) y psycopg no entiende ese ``+psycopg``: lo
    rechaza con «missing "=" after …», un error que no se parece en nada a su
    causa y que además **escupe el DSN entero, contraseña incluida**, al log.
    """
    for prefijo in ("postgresql+psycopg://", "postgresql+psycopg2://",
                    "postgresql+asyncpg://"):
        if dsn.startswith(prefijo):
            return "postgresql://" + dsn[len(prefijo):]
    return dsn


class CalculadoraDeAnalitica:
    """Cuenta lo que hay en el índice, agrupado por fuente.

    Se consulta el almacén vectorial y no OpenSearch a propósito: pgvector es
    donde la cosecha escribe, así que es la capa que primero refleja la
    realidad. Si las dos discrepan, es que falta un reindex — y eso también
    conviene poder verlo.

    Args:
        dsn: Cadena de conexión de PostgreSQL/pgvector.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = _dsn_para_psycopg(dsn)

    def calcular(self) -> AnaliticaDelIndice:
        import psycopg

        consulta = """
            SELECT metadata->>'source'            AS fuente,
                   count(*)                       AS documentos,
                   min((metadata->>'year')::int)  AS anio_min,
                   max((metadata->>'year')::int)  AS anio_max
              FROM sciback_vectors
             WHERE metadata->>'source' IS NOT NULL
               AND coalesce(metadata->>'is_chunk', 'false') <> 'true'
               AND (metadata->>'year' IS NULL OR metadata->>'year' ~ '^[0-9]{4}$')
             GROUP BY 1
             ORDER BY 2 DESC
        """
        filas: list[tuple] = []
        try:
            with psycopg.connect(self._dsn, connect_timeout=10) as con, con.cursor() as cur:
                cur.execute(consulta)
                filas = cur.fetchall()
        except Exception as exc:
            # Sin str(exc): psycopg mete el DSN completo —con la contraseña—
            # en el texto del error, y esto acaba en el log de producción.
            logger.warning("analitica_no_disponible", tipo=type(exc).__name__)
            return AnaliticaDelIndice(calculada_en=datetime.now(UTC))

        fuentes = []
        for clave, documentos, anio_min, anio_max in filas:
            nombre, descripcion = _COMO_SE_LLAMA.get(clave, (clave, ""))
            # Un año de 1000 es el relleno que pone el adaptador cuando el
            # registro no trae fecha; publicarlo como cobertura sería mentir.
            fuentes.append(
                FuenteIndexada(
                    clave=clave,
                    documentos=int(documentos),
                    nombre=nombre,
                    descripcion=descripcion,
                    anio_min=anio_min if anio_min and anio_min > 1500 else None,
                    anio_max=anio_max if anio_max and anio_max > 1500 else None,
                )
            )

        analitica = AnaliticaDelIndice(
            calculada_en=datetime.now(UTC), fuentes=tuple(fuentes)
        )
        logger.info(
            "analitica_calculada",
            fuentes=len(fuentes),
            total=analitica.total,
        )
        return analitica
