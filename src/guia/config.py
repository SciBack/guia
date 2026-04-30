"""GUIASettings — configuración central de GUIA Node.

Lee todas las variables de entorno desde .env.
Los adapters sciback-* tienen sus propias Settings que leen sus propios prefijos
(DSPACE_, OJS_, CLAUDE_, OLLAMA_, etc.) — no los repetimos aquí.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMMode(StrEnum):
    """Selector de modo de inferencia LLM para GUIA."""

    LOCAL = "LOCAL"
    HYBRID = "HYBRID"
    CLOUD = "CLOUD"


class GUIASettings(BaseSettings):
    """Configuración global de GUIA Node.

    Leída desde variables de entorno o archivo .env en el cwd.

    Attributes:
        llm_mode: Modo de inferencia LLM (LOCAL | HYBRID | CLOUD).
        environment: Entorno de ejecución (development | staging | production).
        guia_base_url: URL pública de este nodo GUIA.
        log_level: Nivel de log (DEBUG | INFO | WARNING | ERROR).
        redis_url: URL de conexión a Redis.
        semantic_cache_ttl: TTL en segundos del caché semántico.
        semantic_cache_threshold: Score mínimo para considerar cache hit (0-1).
        telegram_rate_limit: Máximo de mensajes por minuto por usuario en Telegram.
        grobid_base_url: URL del servicio GROBID para extracción de PDFs.
        harvest_cron: Expresión cron para el job de cosecha automática.
        aws_s3_backup_bucket: Bucket S3 para backups (opcional).
        aws_region: Región AWS para backups.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Modo LLM
    guia_llm_mode: LLMMode = LLMMode.HYBRID

    # Entorno
    environment: Literal["development", "staging", "production"] = "development"
    guia_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # Redis / caché semántico
    redis_url: str = "redis://localhost:6379/0"
    semantic_cache_ttl: int = 3600
    semantic_cache_threshold: float = 0.92

    # Canales
    telegram_rate_limit: int = 10

    # GROBID (Sprint 0.4)
    grobid_base_url: str = "http://grobid:8070"

    # Scheduler (Sprint 0.7)
    harvest_cron: str = "0 2 * * *"
    aws_s3_backup_bucket: str = ""
    aws_region: str = "us-east-1"

    # M3: Search backend (ADR-029)
    # "pgvector" | "opensearch" | "dual"
    # dual: escribe a ambos, lee de OpenSearch con fallback a pgvector
    search_backend: str = "dual"

    # M3: Auth / dominio permitido (ADR-034) — antes hardcodeado como @upeu.edu.pe
    # Comma-separated: "upeu.edu.pe,sciback.com"
    keycloak_allowed_domains: str = "upeu.edu.pe"

    # M3: OAI-PMH server (ADR-031)
    oai_repository_name: str = "GUIA Node"
    oai_admin_email: str = "admin@guia.sciback.com"
    oai_base_url: str = "http://localhost:8000/oai"

    # M3: midPoint enrichment (ADR-034) — opcional
    midpoint_url: str = "http://192.168.15.230:8080/midpoint"
    midpoint_username: str = "administrator"
    midpoint_password: str = ""
    midpoint_cache_ttl: int = 900

    # M4: UserProfile Postgres (ADR-034) — reutiliza la misma DB que pgvector
    # El adapter pgvector lee PGVECTOR_DATABASE_URL; lo espejamos aquí para
    # que GUIAContainer pueda pasárselo a UserProfileRepository sin instanciar pgvector config.
    pgvector_database_url: str = "postgresql+psycopg://guia:changeme@postgres:5432/guia_db"

    # Embedding backend: "ollama" (default — usa E5EmbeddingAdapter remoto)
    # o "fastembed" (local ONNX, sin red, 10× más rápido para harvest)
    embedding_backend: Literal["ollama", "fastembed"] = "ollama"

    # GROBID full-text extraction (P3.2, ADR-037).
    # Endpoint del servicio GROBID (docker compose --profile grobid up).
    # Vacío = GROBID deshabilitado (harvester usa solo abstract/TOC, no full-text).
    grobid_url: str = ""
