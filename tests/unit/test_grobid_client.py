"""Tests del cliente GROBID + parser TEI XML (P3.2)."""

from __future__ import annotations

import pytest

from guia.grobid import GrobidClient, GrobidError
from guia.grobid.client import parse_tei_to_text


# ── TEI XML samples ──────────────────────────────────────────────────────


SAMPLE_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Inteligencia Artificial en Educación Superior</title>
      </titleStmt>
    </fileDesc>
    <profileDesc>
      <abstract>
        <p>Este estudio analiza el impacto de la IA en universidades peruanas
        durante el periodo 2020-2024. Se aplicaron técnicas de NLP a 500 tesis.</p>
      </abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head>1. Introducción</head>
        <p>El uso de modelos de lenguaje en educación ha crecido significativamente.</p>
      </div>
      <div>
        <head>2. Metodología</head>
        <p>Se usó un corpus de tesis del repositorio institucional.</p>
      </div>
    </body>
    <back>
      <div>
        <listBibl>
          <biblStruct><analytic><title>Ref 1</title></analytic></biblStruct>
          <biblStruct><analytic><title>Ref 2</title></analytic></biblStruct>
        </listBibl>
      </div>
    </back>
  </text>
</TEI>
"""


# ── parse_tei_to_text ─────────────────────────────────────────────────────


def test_parse_tei_extracts_title() -> None:
    e = parse_tei_to_text(SAMPLE_TEI)
    assert e.title == "Inteligencia Artificial en Educación Superior"


def test_parse_tei_extracts_abstract() -> None:
    e = parse_tei_to_text(SAMPLE_TEI)
    assert "IA en universidades peruanas" in e.abstract
    assert "2020-2024" in e.abstract


def test_parse_tei_extracts_body_sections() -> None:
    e = parse_tei_to_text(SAMPLE_TEI)
    assert "1. Introducción" in e.body_text
    assert "2. Metodología" in e.body_text
    assert "modelos de lenguaje en educación" in e.body_text
    assert "corpus de tesis" in e.body_text
    # Las dos secciones se separan por dobles saltos
    assert "\n\n" in e.body_text


def test_parse_tei_counts_references() -> None:
    e = parse_tei_to_text(SAMPLE_TEI)
    assert e.references_count == 2


def test_parse_tei_preserves_raw_xml() -> None:
    e = parse_tei_to_text(SAMPLE_TEI)
    assert e.tei_xml == SAMPLE_TEI


def test_parse_tei_invalid_xml_raises() -> None:
    with pytest.raises(GrobidError):
        parse_tei_to_text("<tei>esto no cierra")


def test_parse_tei_empty_body_handles_gracefully() -> None:
    minimal = """<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title>T</title></titleStmt></fileDesc></teiHeader>
</TEI>
"""
    e = parse_tei_to_text(minimal)
    assert e.title == "T"
    assert e.abstract == ""
    assert e.body_text == ""
    assert e.references_count == 0


# ── GrobidClient (HTTP mockeado) ──────────────────────────────────────────


def test_client_is_alive_returns_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

    def fake_get(url: str, timeout: float = 0) -> FakeResponse:
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GrobidClient("http://fake-grobid:8070")
    assert client.is_alive() is True


def test_client_is_alive_returns_false_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def fake_get(url: str, timeout: float = 0) -> object:
        raise httpx.ConnectError("no hay servicio")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GrobidClient("http://nope:9999")
    assert client.is_alive() is False


def test_client_process_pdf_bytes_returns_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200
        text = SAMPLE_TEI

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        # Validar que el endpoint y form son correctos
        assert "processFulltextDocument" in url
        assert "files" in kwargs
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GrobidClient("http://fake-grobid:8070")
    extraction = client.process_pdf_bytes(b"%PDF-1.4 fake")

    assert extraction.title == "Inteligencia Artificial en Educación Superior"
    assert extraction.references_count == 2
    assert "metodología" in extraction.body_text.lower()


def test_client_process_pdf_bytes_raises_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 500
        text = "internal server error"

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GrobidClient("http://fake-grobid:8070")
    with pytest.raises(GrobidError, match="500"):
        client.process_pdf_bytes(b"fake")


def test_client_process_pdf_path_missing_file_raises(tmp_path: object) -> None:
    client = GrobidClient("http://fake-grobid:8070")
    with pytest.raises(GrobidError, match="no existe"):
        client.process_pdf_path("/ruta/que/no/existe.pdf")


def test_client_process_pdf_path_reads_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    class FakeResponse:
        status_code = 200
        text = SAMPLE_TEI

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    pdf_file = tmp_path / "test.pdf"  # type: ignore[operator]
    pdf_file.write_bytes(b"%PDF-1.4 fake content")

    client = GrobidClient("http://fake-grobid:8070")
    extraction = client.process_pdf_path(pdf_file)
    assert extraction.title == "Inteligencia Artificial en Educación Superior"


def test_client_base_url_strips_trailing_slash() -> None:
    c = GrobidClient("http://x:8070/")
    assert c.base_url == "http://x:8070"
