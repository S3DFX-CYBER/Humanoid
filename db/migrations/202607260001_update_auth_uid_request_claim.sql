-- Upgrade local Supabase auth.uid() stubs to read the production claim name.
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

    IF uid_source IS NULL
       OR (
           uid_source LIKE '%jwt.claims.sub%'
           AND uid_source NOT LIKE '%request.jwt.claim.sub%'
       ) THEN
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
