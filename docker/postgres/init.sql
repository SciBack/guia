-- Inicialización de la base de datos GUIA
-- Este script corre automáticamente al crear el contenedor postgres por primera vez.

-- Extensión pgvector (requerida por sciback-vectorstore-pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Extensión para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Tabla de vectores ──────────────────────────────────────────
-- sciback-vectorstore-pgvector crea su propia tabla (sciback_vectors / guia_vectors)
-- vía SQLAlchemy al iniciar PgVectorStore. Este script solo garantiza que la extensión
-- esté disponible antes de que la app conecte.

-- ── Schema de metadatos de cosecha ────────────────────────────
CREATE TABLE IF NOT EXISTS harvest_runs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source      VARCHAR(50) NOT NULL,  -- dspace | ojs | alicia
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      VARCHAR(20) NOT NULL DEFAULT 'running',  -- running | success | failed
    items_total INTEGER DEFAULT 0,
    items_ok    INTEGER DEFAULT 0,
    error_msg   TEXT,
    metadata    JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_harvest_runs_source ON harvest_runs(source);
CREATE INDEX IF NOT EXISTS idx_harvest_runs_started_at ON harvest_runs(started_at DESC);

-- ── Schema de caché semántico ──────────────────────────────────
-- Redis maneja el caché en runtime, pero guardamos estadísticas en PG
CREATE TABLE IF NOT EXISTS cache_stats (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hits        BIGINT DEFAULT 0,
    misses      BIGINT DEFAULT 0,
    total       BIGINT DEFAULT 0
);

COMMENT ON TABLE harvest_runs IS 'Registro de corridas de cosecha OAI-PMH por fuente';
COMMENT ON TABLE cache_stats IS 'Estadísticas de hit/miss del caché semántico Redis';

-- ── Historial de conversaciones ────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    email       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    intent      VARCHAR(20),
    model_used  VARCHAR(80),
    cached      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_email   ON chat_sessions(email, updated_at DESC);

COMMENT ON TABLE chat_sessions IS 'Sesiones de chat — una por conexión Chainlit/Telegram';
COMMENT ON TABLE chat_messages IS 'Historial de mensajes persistidos para memoria conversacional';

-- ── Tablas nativas del Data Layer de Chainlit 2.x ─────────────
-- Habilitan el sidebar de historial de threads y persistencia nativa.
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    identifier   TEXT NOT NULL UNIQUE,
    "createdAt"  TEXT,
    metadata     JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS threads (
    id               TEXT PRIMARY KEY,
    "createdAt"      TEXT,
    name             TEXT,
    "userId"         TEXT REFERENCES users(id) ON DELETE CASCADE,
    "userIdentifier" TEXT,
    tags             TEXT[],
    metadata         JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    "threadId"      TEXT REFERENCES threads(id) ON DELETE CASCADE,
    "parentId"      TEXT,
    streaming       BOOLEAN DEFAULT FALSE,
    "waitForAnswer" BOOLEAN,
    "isError"       BOOLEAN DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}',
    tags            TEXT[],
    input           TEXT DEFAULT '',
    output          TEXT DEFAULT '',
    "createdAt"     TEXT,
    start           TEXT,
    "end"           TEXT,
    generation      JSONB,
    "showInput"     TEXT,
    language        TEXT,
    "defaultOpen"   BOOLEAN DEFAULT FALSE,
    "autoCollapse"  BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id       TEXT PRIMARY KEY,
    "forId"  TEXT REFERENCES steps(id) ON DELETE CASCADE,
    value    INTEGER NOT NULL,
    comment  TEXT
);

CREATE TABLE IF NOT EXISTS elements (
    id             TEXT PRIMARY KEY,
    "threadId"     TEXT REFERENCES threads(id) ON DELETE CASCADE,
    type           TEXT,
    name           TEXT NOT NULL,
    display        TEXT,
    url            TEXT,
    "objectKey"    TEXT,
    "chainlitKey"  TEXT,
    size           TEXT,
    language       TEXT,
    page           INTEGER,
    "autoPlay"     BOOLEAN,
    "playerConfig" JSONB,
    props          JSONB DEFAULT '{}',
    "forId"        TEXT,
    mime           TEXT
);

CREATE INDEX IF NOT EXISTS idx_threads_userId     ON threads("userId");
CREATE INDEX IF NOT EXISTS idx_steps_threadId     ON steps("threadId");
CREATE INDEX IF NOT EXISTS idx_elements_threadId  ON elements("threadId");
CREATE INDEX IF NOT EXISTS idx_feedbacks_forId    ON feedbacks("forId");
