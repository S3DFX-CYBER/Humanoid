# Database

Postgres 16 with `pgvector`. `db/schema.sql` is the single source of truth and
is idempotent; `db/migrations/` holds changes for databases that already exist.

## Tables

| Table | Holds |
| --- | --- |
| `users` | local mirror of a Supabase identity, keyed by the JWT subject |
| `jobs` | one row per research request: topic, status, citation style, config |
| `job_stages` | one row per stage attempt: status, `output_data` (jsonb), error |
| `sources` | fetched pages per job, with `content_text` and a 384-dim embedding |
| `verification_results` | one row per checked claim: `pass`, `unsupported`, `contradicted` |
| `uploads` | user-supplied files and their extracted text |
| `documents` | the rendered DOCX bytes, unique per `(job_id, kind)` |

Unique index `sources(job_id, url)` — the research stage inserts with
`ON CONFLICT DO NOTHING`, so without it a repeated URL becomes a duplicate
source and duplicated prompt context.

## Two roles, on purpose

| Role | Used by | Privileges |
| --- | --- | --- |
| `humanoid` | migrations, seeds | owner (and superuser in the compose image) |
| `humanoid_app` | API, worker | `SELECT/INSERT/UPDATE/DELETE`, not an owner, not a superuser |

This split is the whole security story. Row-Level Security does **not** apply to
a table's owner, and never applies to a superuser. If the application connects as
`humanoid`, every policy is decorative — which is exactly what the code did
before this change, while the README claimed strict isolation.

`FORCE ROW LEVEL SECURITY` is set on every table as a second belt: it extends
policies to the owner, so a mistake in the connection string cannot silently
turn isolation off.

## How a query is scoped

Supabase's `auth.uid()` reads the `request.jwt.claim.sub` session setting. The
API never sets it globally — `api/database.py:user_connection()` opens a
transaction, calls `set_config(..., true)` (transaction-local), and yields the
connection:

```python
async with user_connection(pool, user_id) as conn:
    rows = await conn.fetch("SELECT * FROM jobs")
```

A query outside that block sees zero rows rather than everyone's. The worker
does the same for every write; it receives the owner's `user_id` in its queue
payload so it needs no elevated role.

## Verifying it

```bash
pytest tests/test_rls.py -v
```

Those tests switch into `humanoid_app` and assert that another user's job,
documents included, is invisible, that no session context means no rows, and
that inserting a row for a different user is rejected. They run in CI against a
real Postgres, not a mock.

## Migrations

Applied by hand (or by the Supabase GitHub integration). Each file is
idempotent and safe to re-run:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/<file>.sql
```

On a fresh volume, `db/schema.sql` and `db/seed.sql` run automatically from
`docker-entrypoint-initdb.d`. To re-initialise: `docker compose down -v`.

## Notes

* `job_stages.output_data` is `jsonb`; asyncpg is given dicts because the pool
  registers a JSON codec on every connection (`api/database.py:init_connection`).
  Without it, inserts fail with *expected str, got dict*.
* `sources.embedding` is `vector(384)`. When no embedding provider is
  configured the column is NULL — never a zero vector, which would make every
  source look identical to a similarity search.
