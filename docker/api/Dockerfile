# ── Build stage ───────────────────────────────────────────────
FROM python:3.13-slim AS builder

# Build tools para paquetes que requieren compilación C++ (fasttext-langdetect)
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ cmake && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar manifiestos primero (cache-friendly)
COPY pyproject.toml .
# En CI/producción los paquetes sciback-* se copian o instalan desde PyPI.
# Para desarrollo local se montan los src/ como volumen.
# El lock se copia si existe.
COPY uv.lock* ./

# Instalar deps sin el proyecto (sin src/) para cachear capa de deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null || \
    uv sync --no-install-project --no-dev

# Instalar detoxify con torch CPU-only (no está en uv.lock para evitar CUDA torch de PyPI)
# torch CPU para linux/amd64: ~280MB vs ~2GB CUDA
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python .venv/bin/python3 \
    "torch==2.5.1+cpu" "torchvision==0.20.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --python .venv/bin/python3 "detoxify>=0.5"

# ── Runtime stage ─────────────────────────────────────────────
FROM python:3.13-slim

# Herramientas mínimas para healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar venv del builder
COPY --from=builder /app/.venv /app/.venv

# Copiar código fuente
COPY src/ ./src/

# Activar venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Usuario no-root
RUN useradd -m -u 1000 guia && chown -R guia:guia /app
USER guia

EXPOSE 8000

CMD ["python", "-m", "guia", "serve"]
