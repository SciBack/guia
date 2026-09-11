#!/usr/bin/env bash
#
# Lo que GUIA tiene que revisar cada día para no quedarse desfasada.
#
# Son dos cosas distintas y las dos hacen falta:
#
#   1. El mapa institucional (SGC). Las áreas y los procesos cambian —se crean
#      unidades, se asignan dueños, se aprueban fichas— y GUIA responde con lo
#      que cosechó la última vez. Son 147 documentos: cuesta segundos.
#
#   2. El inventario del índice. Es lo que GUIA contesta cuando le preguntan
#      qué información maneja, y lo que publica el endpoint de transparencia
#      que exige el DS 115-2025-PCM. Antes estaba escrito a mano en el código
#      y el 11-sep-2026 tres de sus cuatro cifras eran falsas.
#
# Y una advertencia que costó una recosecha entera de Koha entenderla:
# **cosechar no publica**. `harvest` escribe en pgvector; la búsqueda lee de
# OpenSearch. Sin el `reindex` de en medio, la cosecha termina diciendo "0
# errores" y el buscador no se entera de nada.
#
# Las fuentes grandes (koha, dspace, cris, ojs) NO se tocan aquí: son horas de
# cosecha y cambian despacio. Van aparte, cuando toque.

set -uo pipefail

CONTENEDOR="${GUIA_CONTENEDOR:-guia-api-1}"
LOG_DIR="${GUIA_LOG_DIR:-/opt/guia/logs}"
LOG="$LOG_DIR/actualizacion-diaria.log"
API="${GUIA_API:-http://localhost:8000}"

mkdir -p "$LOG_DIR"

decir() { printf '%s  %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG"; }

en_guia() { docker exec "$CONTENEDOR" sh -c "cd /app && $1" >> "$LOG" 2>&1; }

decir "── inicio ──────────────────────────────────────────────"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
    decir "✗ el contenedor $CONTENEDOR no está levantado; no hay nada que hacer"
    exit 1
fi

fallos=0

decir "1/3 cosechando el mapa institucional del SGC"
if en_guia "python -m guia harvest --source sgc"; then
    decir "    ok"
else
    decir "    ✗ falló la cosecha del SGC"
    fallos=$((fallos + 1))
fi

# Sin esto la cosecha no llega al buscador. No es opcional.
decir "2/3 publicando en OpenSearch"
if en_guia "python -m guia reindex --target opensearch --source sgc"; then
    decir "    ok"
else
    decir "    ✗ falló el reindex — lo cosechado NO está en el buscador"
    fallos=$((fallos + 1))
fi

decir "3/3 recontando el índice"
respuesta=$(curl -s -m 120 -X POST "$API/api/transparency/recalcular" 2>&1)
if printf '%s' "$respuesta" | grep -q '"recalculado":true'; then
    decir "    ok — $respuesta"
else
    # No es fatal: la API recalcula sola al arrancar. Pero conviene saberlo,
    # porque mientras tanto publica las cifras del último arranque.
    decir "    ✗ no se pudo recontar: $respuesta"
    fallos=$((fallos + 1))
fi

if [ "$fallos" -eq 0 ]; then
    decir "── fin: todo correcto ──────────────────────────────────"
else
    decir "── fin: $fallos paso(s) con error ──────────────────────"
fi

exit "$fallos"
