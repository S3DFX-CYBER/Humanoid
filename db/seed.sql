-- Development seed data.
--
-- Runs as the database owner (migrations do), so it is deliberately guarded:
-- it refuses to insert into a database that already holds real users, and it
-- is idempotent so `docker compose up` can run repeatedly.

DO $$
DECLARE
    existing_users integer;
BEGIN
    SELECT count(*) INTO existing_users FROM users;

    IF existing_users > 0 THEN
        RAISE NOTICE 'Seed skipped: users table already has % row(s).',
            existing_users;
        RETURN;
    END IF;

    IF current_database() NOT IN ('humanoid', 'postgres', 'test') THEN
        RAISE EXCEPTION
            'Refusing to seed database % — expected a local dev database.',
            current_database();
    END IF;

    INSERT INTO users (id, email)
    VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'dev@humanoid.local')
    ON CONFLICT DO NOTHING;

    INSERT INTO jobs (id, user_id, topic, status)
    VALUES (
        'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
        'The impact of transformer architectures on NLP research',
        'queued'
    )
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Seeded dev user a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
END $$;
