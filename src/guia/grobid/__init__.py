"""GROBID client — extracción full-text de PDFs académicos (P3.2, ADR-037).

GROBID es un servicio Java estándar para parsear papers PDF a TEI XML.
Documentación: https://grobid.readthedocs.io/

GUIA usa solo el endpoint `/api/processFulltextDocument` que devuelve TEI XML
con la estructura del paper (header, abstract, body, references). Lo
parseamos a texto plano para chunking y embedding.

Diseño:
- HTTP client async (httpx) con timeout configurable
- Parsing TEI XML con stdlib (xml.etree) — sin dependencias extra
- Fallback opcional a PyPDF2 si GROBID no responde (modo degradado)
- Wrapper compatible con el harvester: process_pdf_url(url) → str

Operacional:
- GROBID corre en docker-compose como servicio aparte (no en el Mac Mini)
- Endpoint default: http://localhost:8070/api/
- Configuración via env: GROBID_URL
"""

from guia.grobid.client import GrobidClient, GrobidError

__all__ = ["GrobidClient", "GrobidError"]
