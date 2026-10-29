-- Migration: rendered document storage, source dedupe, and real RLS enforcement.

-- 1. Finished documents live in Postgres so the API can stream them.
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

CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

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

-- 2. One row per URL per job — the research stage inserts with
--    ON CONFLICT (job_id, url) DO NOTHING and needs this index to exist.
--    Existing duplicates are removed first.
DELETE FROM sources a
    USING sources b
    WHERE a.job_id = b.job_id
      AND a.url = b.url
      AND a.ctid > b.ctid;

CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_job_url ON sources(job_id, url);

-- 3. RLS was enabled but not FORCEd, so the owning application role bypassed
--    every policy. This is the fix that makes the isolation claim true.
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE job_stages FORCE ROW LEVEL SECURITY;
ALTER TABLE sources FORCE ROW LEVEL SECURITY;
ALTER TABLE verification_results FORCE ROW LEVEL SECURITY;
ALTER TABLE uploads FORCE ROW LEVEL SECURITY;

-- 4. WITH CHECK on policies: without it an INSERT is only checked against
--    USING for FOR ALL policies, which is easy to get subtly wrong.
DROP POLICY IF EXISTS jobs_isolation ON jobs;
CREATE POLICY jobs_isolation ON jobs
    FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS users_isolation ON users;
CREATE POLICY users_isolation ON users
    FOR ALL USING (id = auth.uid()) WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS uploads_isolation ON uploads;
CREATE POLICY uploads_isolation ON uploads
    FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- 5. Non-owner application role.
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
