-- Humanoid schema
-- Idempotent: safe to re-run against an existing database.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- SUPABASE AUTH STUB (local Postgres only)
-- ============================================================
-- Supabase ships auth.uid(); plain Postgres does not. The stub reads the
-- same session setting the application writes (request.jwt.claim.sub), so
-- local behaviour matches production.

DO $$
DECLARE
    uid_source text;
BEGIN
    CREATE SCHEMA IF NOT EXISTS auth;

    SELECT pg_proc.prosrc
    INTO uid_source
    FROM pg_proc
    JOIN pg_namespace ON pg_proc.pronamespace = pg_namespace.oid
    WHERE pg_namespace.nspname = 'auth'
      AND pg_proc.proname = 'uid'
    LIMIT 1;

    IF uid_source IS NULL THEN
        EXECUTE '
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $func$
            SELECT NULLIF(
                current_setting(''request.jwt.claim.sub'', true),
                ''''
            )::uuid;
            $func$ LANGUAGE SQL STABLE;
        ';
    END IF;
END $$;

-- ============================================================
-- ENUMS
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
        CREATE TYPE job_status AS ENUM (
            'queued',
            'researching',
            'outlining',
            'outline_pending_approval',
            'drafting',
            'verifying',
            'styling',
            'formatting',
            'done',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'stage_status') THEN
        CREATE TYPE stage_status AS ENUM (
            'pending',
            'running',
            'completed',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'source_type') THEN
        CREATE TYPE source_type AS ENUM (
            'web',
            'pdf',
            'docx',
            'ppt',
            'image'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verdict_type') THEN
        CREATE TYPE verdict_type AS ENUM (
            'pass',
            'unsupported',
            'contradicted'
        );
    END IF;
END $$;

-- Older databases predate outline approval; keep them in step.
ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'outline_pending_approval'
    AFTER 'outlining';

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL,
    status          job_status NOT NULL DEFAULT 'queued',
    citation_style  TEXT DEFAULT 'apa',
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job_stages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage_name      TEXT NOT NULL,
    status          stage_status NOT NULL DEFAULT 'pending',
    input_data      JSONB DEFAULT '{}',
    output_data     JSONB DEFAULT '{}',
    error           TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    url                 TEXT,
    title               TEXT,
    content_text        TEXT,
    source_type         source_type NOT NULL DEFAULT 'web',
    credibility_score   REAL,
    embedding           vector(384),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verification_results (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id           UUID REFERENCES sources(id) ON DELETE SET NULL,
    claim_text          TEXT NOT NULL,
    verdict             verdict_type NOT NULL,
    evidence_excerpt    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS uploads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT,
    storage_path    TEXT NOT NULL,
    extracted_text  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rendered output. Keeping the bytes in Postgres means the API can stream a
-- finished DOCX without a second storage service to configure.
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'docx',
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    content         BYTEA NOT NULL,
    byte_size       INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, kind)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_stages_job_id ON job_stages(job_id);
CREATE INDEX IF NOT EXISTS idx_job_stages_job_stage ON job_stages(job_id, stage_name);
CREATE INDEX IF NOT EXISTS idx_sources_job_id ON sources(job_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_job_id
    ON verification_results(job_id);
CREATE INDEX IF NOT EXISTS idx_uploads_job_id ON uploads(job_id);
CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id);

-- One row per URL per job: the research stage relies on this to dedupe.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_job_url ON sources(job_id, url);

-- ============================================================
-- ROW-LEVEL SECURITY
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- FORCE makes the policies apply to the table owner too. Without it, the
-- application role (which owns these tables) silently bypasses every policy.
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE job_stages FORCE ROW LEVEL SECURITY;
ALTER TABLE sources FORCE ROW LEVEL SECURITY;
ALTER TABLE verification_results FORCE ROW LEVEL SECURITY;
ALTER TABLE uploads FORCE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_isolation ON users;
CREATE POLICY users_isolation ON users
    FOR ALL USING (id = auth.uid()) WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS jobs_isolation ON jobs;
CREATE POLICY jobs_isolation ON jobs
    FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS job_stages_isolation ON job_stages;
CREATE POLICY job_stages_isolation ON job_stages
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = job_stages.job_id
            AND jobs.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = job_stages.job_id
            AND jobs.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS sources_isolation ON sources;
CREATE POLICY sources_isolation ON sources
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = sources.job_id
            AND jobs.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = sources.job_id
            AND jobs.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS verification_results_isolation ON verification_results;
CREATE POLICY verification_results_isolation ON verification_results
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = verification_results.job_id
            AND jobs.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = verification_results.job_id
            AND jobs.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS uploads_isolation ON uploads;
CREATE POLICY uploads_isolation ON uploads
    FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS documents_isolation ON documents;
CREATE POLICY documents_isolation ON documents
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = documents.job_id
            AND jobs.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = documents.job_id
            AND jobs.user_id = auth.uid()
        )
    );

-- ============================================================
-- APPLICATION ROLE
-- ============================================================
-- The API and worker connect as a non-superuser, non-owner role so RLS
-- actually applies to them. Migrations and seeds run as the owner.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'humanoid_app') THEN
        CREATE ROLE humanoid_app LOGIN PASSWORD 'humanoid_app';
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO humanoid_app;
GRANT USAGE ON SCHEMA auth TO humanoid_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
    TO humanoid_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO humanoid_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO humanoid_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO humanoid_app;

-- ============================================================
-- TRIGGER: auto-update updated_at on jobs
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_updated_at ON jobs;
CREATE TRIGGER jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
