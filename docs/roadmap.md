# Roadmap

## Fase 0 — Node piloto UPeU (Q2-Q3 2026)

**Objetivo:** GUIA Node funcionando en UPeU con DSpace + OJS + Koha, chat web y Telegram.

| # | Actividad | Estado |
|---|-----------|--------|
| 0.1 | Reunir con DTI UPeU — presentar piloto | Pendiente |
| 0.2 | Configurar guia.sciback.com (DNS) | Pendiente |
| 0.3 | Desplegar harvester OAI-PMH para DSpace UPeU | Pendiente |
| 0.4 | Integrar GROBID para full-text de PDFs | Pendiente |
| 0.5 | Configurar pgvector + embeddings | Pendiente |
| 0.6 | Implementar RAG basico con LLM | Pendiente |
| 0.7 | Conector OJS para revistas UPeU | Pendiente |
| 0.8 | Conector Koha para biblioteca UPeU | Pendiente |
| 0.9 | Chat web (widget embebible) | Pendiente |
| 0.10 | Telegram bot | Pendiente |
| 0.11 | Demo interna a DTI UPeU | Pendiente |

### Entregables
- [ ] GUIA Node desplegado en AWS con URL publica
- [ ] Chat funcionando con respuestas sobre tesis/articulos UPeU
- [ ] Consulta de prestamos de biblioteca via chat
- [ ] Demo grabada para presentaciones

---

## Fase 1 — Node empaquetado (Q4 2026)

**Objetivo:** Docker Compose listo para que cualquier universidad despliegue GUIA Node.

| # | Actividad | Estado |
|---|-----------|--------|
| 1.1 | Empaquetar Node en Docker Compose reproducible | Pendiente |
| 1.2 | Documentar quickstart ("levanta tu Node en 15 min") | Pendiente |
| 1.3 | Pilotar en 2-3 universidades adicionales | Pendiente |
| 1.4 | Publicar repo open source (Apache 2.0) | Pendiente |
| 1.5 | Primeros clientes SciBack (Campus Basic) | Pendiente |

---

## Fase 2 — Hub piloto (H1 2027)

**Objetivo:** Federacion de nodos para busqueda unificada de investigacion.

| # | Actividad | Estado |
|---|-----------|--------|
| 2.1 | Implementar Hub federation broker | Pendiente |
| 2.2 | OAI-PMH endpoint del Hub hacia redes nacionales | Pendiente |
| 2.3 | Conectores SIS y ERP (Campus Pro) | Pendiente |
| 2.4 | WhatsApp Business API | Pendiente |
| 2.5 | Escalar a 10+ universidades | Pendiente |
| 2.6 | Aplicar IOI Fund (si hay convocatoria) | Pendiente |

---

## Fase 3 — Hub escalado (2028+)

**Objetivo:** Plataforma madura, 50+ universidades, sostenibilidad comercial.

| # | Actividad | Estado |
|---|-----------|--------|
| 3.1 | MCP server publico | Pendiente |
| 3.2 | 50+ universidades conectadas | Pendiente |
| 3.3 | Integracion con OpenAIRE / LA Referencia | Pendiente |
| 3.4 | Sostenibilidad via revenue SciBack | Pendiente |
| 3.5 | Dashboard de analiticas por universidad | Pendiente |

---

## KPIs

| Indicador | Fase 0 | Fase 1 | Fase 2 | Fase 3 |
|-----------|--------|--------|--------|--------|
| Universidades | 1 (UPeU) | 3-5 | 10+ | 50+ |
| Conectores activos | 3 (DSpace+OJS+Koha) | 3 | 5+ | 7+ |
| Queries/dia | 50 | 500 | 5,000 | 50,000 |
| Revenue mensual | $0 | $500 | $5,000 | $25,000+ |
| Canales de chat | 2 (web+TG) | 2 | 3 (+WA) | 4 (+Teams) |
