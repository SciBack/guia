"""Cliente HTTP de GROBID + parser TEI XML mínimo (P3.2)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# TEI namespace usado por GROBID
_TEI_NS = "{http://www.tei-c.org/ns/1.0}"


class GrobidError(Exception):
    """Error genérico del cliente GROBID."""


@dataclass(frozen=True)
class GrobidExtraction:
    """Resultado de procesar un PDF con GROBID."""

    title: str
    abstract: str
    body_text: str
    """Texto plano del cuerpo del paper, secciones concatenadas con \\n\\n."""

    references_count: int = 0
    tei_xml: str = ""
    """TEI XML crudo — útil para parsing posterior si se necesitan más campos."""


def parse_tei_to_text(tei_xml: str) -> GrobidExtraction:
    """Parsea TEI XML de GROBID y extrae title + abstract + body.

    Usa xml.etree de stdlib (no requiere lxml). Maneja namespaces TEI.
    Si el XML está malformado, lanza GrobidError.
    """
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as exc:
        raise GrobidError(f"TEI XML inválido: {exc}") from exc

    # Title: //teiHeader/fileDesc/titleStmt/title
    title_elem = root.find(
        f".//{_TEI_NS}teiHeader//{_TEI_NS}titleStmt/{_TEI_NS}title"
    )
    title = (title_elem.text or "").strip() if title_elem is not None else ""

    # Abstract: //profileDesc/abstract
    abstract_parts: list[str] = []
    abstract_elem = root.find(
        f".//{_TEI_NS}profileDesc/{_TEI_NS}abstract"
    )
    if abstract_elem is not None:
        abstract_parts.extend(_iter_text(abstract_elem))
    abstract = " ".join(abstract_parts).strip()

    # Body: //text/body
    body_parts: list[str] = []
    body_elem = root.find(f".//{_TEI_NS}text/{_TEI_NS}body")
    if body_elem is not None:
        for div in body_elem.findall(f".//{_TEI_NS}div"):
            section_text = " ".join(_iter_text(div)).strip()
            if section_text:
                body_parts.append(section_text)
    body_text = "\n\n".join(body_parts)

    # References (solo conteo)
    refs_elems = root.findall(
        f".//{_TEI_NS}listBibl/{_TEI_NS}biblStruct"
    )

    return GrobidExtraction(
        title=title,
        abstract=abstract,
        body_text=body_text,
        references_count=len(refs_elems),
        tei_xml=tei_xml,
    )


def _iter_text(elem: ET.Element) -> list[str]:
    """Itera sobre el texto de un elemento XML preservando whitespace."""
    out: list[str] = []
    if elem.text:
        out.append(elem.text.strip())
    for child in elem:
        out.extend(_iter_text(child))
        if child.tail:
            out.append(child.tail.strip())
    return [s for s in out if s]


class GrobidClient:
    """Cliente sync de GROBID (HTTP + TEI parser).

    Args:
        base_url: URL de GROBID, default http://localhost:8070
        timeout: Timeout en segundos para requests pesados (default 60).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8070",
        *,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def is_alive(self) -> bool:
        """Health check rápido (GET /api/isalive)."""
        import httpx

        try:
            response = httpx.get(
                f"{self._base_url}/api/isalive", timeout=5.0
            )
            return response.status_code == 200
        except Exception:
            return False

    def process_pdf_bytes(
        self,
        pdf_bytes: bytes,
        *,
        consolidate_header: int = 0,
        consolidate_citations: int = 0,
    ) -> GrobidExtraction:
        """Procesa un PDF (en memoria) → GrobidExtraction.

        Args:
            pdf_bytes: Contenido del PDF.
            consolidate_header: 0=no, 1=biblio-glutton, 2=crossref. Default 0 (rápido).
            consolidate_citations: idem para citas. Default 0.

        Raises:
            GrobidError: si el servicio no responde o devuelve error.
        """
        import httpx

        url = f"{self._base_url}/api/processFulltextDocument"
        files = {"input": ("input.pdf", pdf_bytes, "application/pdf")}
        data = {
            "consolidateHeader": str(consolidate_header),
            "consolidateCitations": str(consolidate_citations),
        }

        try:
            response = httpx.post(
                url, files=files, data=data, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise GrobidError(f"GROBID HTTP error: {exc}") from exc

        if response.status_code != 200:
            raise GrobidError(
                f"GROBID respondió {response.status_code}: {response.text[:200]}"
            )

        return parse_tei_to_text(response.text)

    def process_pdf_path(
        self,
        path: str | Path,
        **kwargs: object,
    ) -> GrobidExtraction:
        """Procesa un PDF desde el filesystem."""
        p = Path(path)
        if not p.is_file():
            raise GrobidError(f"PDF no existe: {path}")
        return self.process_pdf_bytes(p.read_bytes(), **kwargs)  # type: ignore[arg-type]
