-- Humanoid Phase 0 Schema
-- Enable pgvector for embedding storage
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- DEV ENVIRONMENT MOCK FOR SUPABASE RLS
-- ============================================================
-- Supabase includes `auth.uid()`, pure Postgres does not.
-- This block safely creates the schema and function only if it's missing,
-- stubbing it to read Supabase's real session variable `request.jwt.claim.sub`.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc JOIN pg_namespace ON pg_proc.pronamespace = pg_namespace.oid 
        WHERE pg_namespace.nspname = 'auth' AND pg_proc.proname = 'uid'
    ) THEN
        CREATE SCHEMA IF NOT EXISTS auth;
        EXECUTE 'CREATE FUNCTION auth.uid() RETURNS uuid AS $func$ SELECT NULLIF(current_setting(''request.jwt.claim.sub'', true), '''')::uuid; $func$ LANGUAGE SQL STABLE;';
    END IF;
END $$;

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE job_status AS ENUM (
    'queued',
    'researching',
    'outlining',
    'drafting',
    'verifying',
    'styling',
    'formatting',
    'done',
    'failed'
);

CREATE TYPE stage_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed'
);

CREATE TYPE source_type AS ENUM (
    'web',
    'pdf',
    'docx',
    'ppt',
    'image'
);

CREATE TYPE verdict_type AS ENUM (
    'pass',
    'unsupported',
    'contradicted'
);

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL,
    status          job_status NOT NULL DEFAULT 'queued',
    citation_style  TEXT DEFAULT 'apa',
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE job_stages (
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

CREATE TABLE sources (
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

CREATE TABLE verification_results (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id           UUID REFERENCES sources(id) ON DELETE SET NULL,
    claim_text          TEXT NOT NULL,
    verdict             verdict_type NOT NULL,
    evidence_excerpt    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uploads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT,
    storage_path    TEXT NOT NULL,
    extracted_text  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_job_stages_job_id ON job_stages(job_id);
CREATE INDEX idx_sources_job_id ON sources(job_id);
CREATE INDEX idx_verification_results_job_id ON verification_results(job_id);
CREATE INDEX idx_uploads_job_id ON uploads(job_id);
CREATE INDEX idx_uploads_user_id ON uploads(user_id);

-- ============================================================
-- ROW-LEVEL SECURITY
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploads ENABLE ROW LEVEL SECURITY;

-- Users: can only see their own row
CREATE POLICY users_isolation ON users
    FOR ALL USING (id = auth.uid());

-- Jobs: scoped to user_id
CREATE POLICY jobs_isolation ON jobs
    FOR ALL USING (user_id = auth.uid());

-- Job stages: scoped via parent job's user_id
CREATE POLICY job_stages_isolation ON job_stages
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = job_stages.job_id
            AND jobs.user_id = auth.uid()
        )
    );

-- Sources: scoped via parent job's user_id
CREATE POLICY sources_isolation ON sources
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = sources.job_id
            AND jobs.user_id = auth.uid()
        )
    );

-- Verification results: scoped via parent job's user_id
CREATE POLICY verification_results_isolation ON verification_results
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM jobs WHERE jobs.id = verification_results.job_id
            AND jobs.user_id = auth.uid()
        )
    );

-- Uploads: scoped to user_id directly
CREATE POLICY uploads_isolation ON uploads
    FOR ALL USING (user_id = auth.uid());

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

CREATE TRIGGER jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
