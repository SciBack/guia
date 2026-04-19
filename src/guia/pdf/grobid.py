"""Cliente GROBID para extracción de texto de PDFs académicos (Sprint 0.4).

GROBID (https://github.com/kermitt2/grobid) es el gold standard para
extracción de estructura semántica de papers: título, autores, abstract,
secciones, referencias.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_GROBID_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


class GrobidClient:
    """Cliente HTTP para el servicio GROBID.

    Args:
        base_url: URL base del servicio GROBID (ej: http://grobid:8070).
        timeout: Timeout HTTP en segundos.
    """

    def __init__(self, base_url: str = "http://grobid:8070", *, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def is_alive(self) -> bool:
        """Verifica que el servicio GROBID esté disponible."""
        try:
            resp = self._client.get("/api/isalive")
            return resp.status_code == 200
        except Exception:
            return False

    def process_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """Procesa un PDF y retorna texto estructurado extraído.

        Usa el endpoint /api/processFulltextDocument de GROBID.

        Args:
            pdf_bytes: Contenido del PDF como bytes.

        Returns:
            Dict con title, abstract, sections, references extraídos.
        """
        resp = self._client.post(
            "/api/processFulltextDocument",
            files={"input": ("document.pdf", pdf_bytes, "application/pdf")},
        )
        resp.raise_for_status()
        return self._parse_tei_xml(resp.text)

    def process_header_only(self, pdf_bytes: bytes) -> dict[str, Any]:
        """Procesa solo el header del PDF (más rápido que full text).

        Útil para extraer título, autores, abstract sin procesar el cuerpo completo.

        Args:
            pdf_bytes: Contenido del PDF como bytes.

        Returns:
            Dict con title, abstract, authors extraídos del header.
        """
        resp = self._client.post(
            "/api/processHeaderDocument",
            files={"input": ("document.pdf", pdf_bytes, "application/pdf")},
        )
        resp.raise_for_status()
        return self._parse_tei_xml(resp.text)

    def _parse_tei_xml(self, tei_xml: str) -> dict[str, Any]:
        """Parsea la respuesta TEI-XML de GROBID.

        Args:
            tei_xml: Respuesta XML de GROBID.

        Returns:
            Dict estructurado con los campos extraídos.
        """
        result: dict[str, Any] = {
            "title": "",
            "abstract": "",
            "authors": [],
            "sections": [],
            "references": [],
            "raw_xml": tei_xml,
        }

        try:
            root = ET.fromstring(tei_xml)

            # Título
            title_el = root.find(".//tei:titleStmt/tei:title", _GROBID_NS)
            if title_el is not None and title_el.text:
                result["title"] = title_el.text.strip()

            # Abstract
            abstract_el = root.find(".//tei:abstract", _GROBID_NS)
            if abstract_el is not None:
                result["abstract"] = " ".join(abstract_el.itertext()).strip()

            # Autores
            for author_el in root.findall(".//tei:author", _GROBID_NS):
                forename_el = author_el.find(".//tei:forename", _GROBID_NS)
                surname_el = author_el.find(".//tei:surname", _GROBID_NS)
                parts = []
                if forename_el is not None and forename_el.text:
                    parts.append(forename_el.text.strip())
                if surname_el is not None and surname_el.text:
                    parts.append(surname_el.text.strip())
                if parts:
                    result["authors"].append(" ".join(parts))

            # Secciones del cuerpo
            for div_el in root.findall(".//tei:body//tei:div", _GROBID_NS):
                head_el = div_el.find("tei:head", _GROBID_NS)
                text_parts = list(div_el.itertext())
                if text_parts:
                    heading = (
                        head_el.text.strip() if head_el is not None and head_el.text else ""
                    )
                    result["sections"].append({
                        "heading": heading,
                        "text": " ".join(text_parts).strip()[:2000],
                    })

        except ET.ParseError as exc:
            logger.warning("grobid_xml_parse_error", exc_info=exc)

        return result

    def pdf_to_chunks(self, pdf_bytes: bytes, *, chunk_size: int = 500) -> list[str]:
        """Procesa un PDF y retorna chunks de texto para embedding.

        Combina title + abstract + secciones y los divide en chunks de
        aproximadamente chunk_size palabras.

        Args:
            pdf_bytes: Contenido del PDF.
            chunk_size: Tamaño aproximado de cada chunk en palabras.

        Returns:
            Lista de chunks de texto listos para embed_passages().
        """
        data = self.process_pdf(pdf_bytes)
        texts: list[str] = []

        if data["title"]:
            texts.append(data["title"])
        if data["abstract"]:
            texts.append(data["abstract"])
        for section in data["sections"]:
            if section["text"]:
                texts.append(section["text"])

        full_text = " ".join(texts)
        words = full_text.split()

        chunks: list[str] = []
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            if chunk:
                chunks.append(chunk)

        return chunks

    def close(self) -> None:
        """Cierra el cliente HTTP."""
        self._client.close()

    def __enter__(self) -> GrobidClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
