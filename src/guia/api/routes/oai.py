"""OAI-PMH endpoint de GUIA Node (ADR-031).

Implementa el protocolo OAI-PMH 2.0 para exposición de metadatos.

M3: Identify y ListSets funcionales.
    GetRecord, ListRecords, ListIdentifiers → noRecordsMatch (M4).
    ListMetadataFormats → oai_dc siempre disponible.

Spec: http://www.openarchives.org/OAI/openarchivesprotocol.html
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

router = APIRouter(prefix="/oai", tags=["oai-pmh"])

_OAI_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ '
    'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"'
)


def _xml_response(body: str) -> Response:
    date_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_OAI_NS}>
  <responseDate>{date_str}</responseDate>
  {body}
</OAI-PMH>"""
    return Response(content=xml, media_type="text/xml; charset=utf-8")


def _error_response(request_url: str, verb: str, code: str, message: str) -> Response:
    body = f"""<request verb="{verb}">{request_url}</request>
  <error code="{code}">{message}</error>"""
    return _xml_response(body)


@router.get("")
@router.get("/")
async def oai_endpoint(
    request: Request,
    verb: Annotated[str, Query()] = "",
    identifier: Annotated[str, Query()] = "",
    metadata_prefix: Annotated[str, Query(alias="metadataPrefix")] = "",
    set_spec: Annotated[str, Query(alias="set")] = "",
    from_: Annotated[str, Query(alias="from")] = "",
    until: Annotated[str, Query()] = "",
    resumption_token: Annotated[str, Query(alias="resumptionToken")] = "",
) -> Response:
    """Endpoint OAI-PMH 2.0 unificado.

    Soporta todos los verbos en una sola URL /oai (según spec).
    """
    settings = request.app.state.settings
    base_url = str(request.url).split("?")[0]

    if not verb:
        return _error_response(base_url, "", "badVerb", "Verb is missing or illegal")

    if verb == "Identify":
        return _handle_identify(base_url, settings)

    if verb == "ListSets":
        return _handle_list_sets(base_url, settings)

    if verb == "ListMetadataFormats":
        return _handle_list_metadata_formats(base_url)

    if verb in ("GetRecord", "ListRecords", "ListIdentifiers"):
        # M3: no hay registros OAI-PMH aún — retornar noRecordsMatch
        return _error_response(
            base_url, verb, "noRecordsMatch",
            "No records available yet. OAI-PMH harvesting will be implemented in M4."
        )

    return _error_response(base_url, verb, "badVerb", f"Illegal verb: {verb!r}")


def _handle_identify(base_url: str, settings: object) -> Response:
    """Retorna descripción del repositorio (OAI-PMH Identify)."""
    repo_name = getattr(settings, "oai_repository_name", "GUIA Node")
    admin_email = getattr(settings, "oai_admin_email", "admin@guia.sciback.com")
    oai_url = getattr(settings, "oai_base_url", base_url)
    earliest_date = "2020-01-01T00:00:00Z"  # TODO M4: consultar min(date) desde store

    body = f"""<request verb="Identify">{oai_url}</request>
  <Identify>
    <repositoryName>{repo_name}</repositoryName>
    <baseURL>{oai_url}</baseURL>
    <protocolVersion>2.0</protocolVersion>
    <adminEmail>{admin_email}</adminEmail>
    <earliestDatestamp>{earliest_date}</earliestDatestamp>
    <deletedRecord>no</deletedRecord>
    <granularity>YYYY-MM-DDThh:mm:ssZ</granularity>
    <description>
      <oai-identifier xmlns="http://www.openarchives.org/OAI/2.0/oai-identifier"
        xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai-identifier
        http://www.openarchives.org/OAI/2.0/oai-identifier.xsd">
        <scheme>oai</scheme>
        <repositoryIdentifier>guia.sciback.com</repositoryIdentifier>
        <delimiter>:</delimiter>
        <sampleIdentifier>oai:guia.sciback.com:publications/1</sampleIdentifier>
      </oai-identifier>
    </description>
  </Identify>"""
    return _xml_response(body)


def _handle_list_sets(base_url: str, settings: object) -> Response:
    """Lista los sets disponibles (fuentes de datos configuradas)."""
    oai_url = getattr(settings, "oai_base_url", base_url)

    # M3: sets estáticos correspondientes a las fuentes de harvesting
    sets = [
        ("dspace", "DSpace Institutional Repository", "Publicaciones del repositorio DSpace"),
        ("ojs", "OJS Journals", "Artículos de revistas Open Journal Systems"),
        ("alicia", "ALICIA CONCYTEC", "Publicaciones validadas ALICIA 2.1.0"),
    ]

    set_items = "\n".join(
        f"""    <set>
      <setSpec>{spec}</setSpec>
      <setName>{name}</setName>
      <setDescription>{desc}</setDescription>
    </set>"""
        for spec, name, desc in sets
    )

    body = f"""<request verb="ListSets">{oai_url}</request>
  <ListSets>
{set_items}
  </ListSets>"""
    return _xml_response(body)


def _handle_list_metadata_formats(base_url: str) -> Response:
    """Lista los formatos de metadatos soportados."""
    body = f"""<request verb="ListMetadataFormats">{base_url}</request>
  <ListMetadataFormats>
    <metadataFormat>
      <metadataPrefix>oai_dc</metadataPrefix>
      <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
      <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
    </metadataFormat>
    <metadataFormat>
      <metadataPrefix>dim</metadataPrefix>
      <schema>http://www.dspace.org/xmlns/dspace/dim</schema>
      <metadataNamespace>http://www.dspace.org/xmlns/dspace/dim</metadataNamespace>
    </metadataFormat>
  </ListMetadataFormats>"""
    return _xml_response(body)
