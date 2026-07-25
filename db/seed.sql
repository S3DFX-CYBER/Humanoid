-- Seed data for local development
-- NOTE: In production, users are created via Supabase Auth.
-- This seed bypasses RLS (run as superuser) for dev convenience.

INSERT INTO users (id, email) VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'dev@humanoid.local');

INSERT INTO jobs (id, user_id, topic, status) VALUES
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'The impact of transformer architectures on NLP research', 'queued');
