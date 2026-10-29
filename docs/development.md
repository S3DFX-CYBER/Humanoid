# Development

## Setup

```bash
cp .env.example .env        # add GEMINI_API_KEY and/or OPENAI_API_KEY
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Ingestion | http://localhost:8001/health |
| Render | http://localhost:8002/health |

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,render]"
uvicorn api.main:app --reload           # API
arq workers.worker.WorkerSettings       # worker, separate shell
cd frontend && npm install && npm run dev
```

You still need Postgres and Redis. `docker compose up postgres redis` is the
quickest way to get both, then point `DATABASE_URL` at `localhost:5432` and
apply `db/schema.sql` once.

## Environment

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | use the `humanoid_app` role, not the owner — see `docs/database.md` |
| `REDIS_URL` | queue and cache |
| `GEMINI_API_KEY` | drafting and outlining (`premium` tier) |
| `OPENAI_API_KEY` | verification and styling (`cheap` tier) |
| `ALLOW_STUB_PROVIDER` | `true` serves placeholder text when no key is set. Local UI work only |
| `DEV_AUTH_USER_ID` | treats every request as this user. Ignored when `ENVIRONMENT=production` |
| `CORS_ORIGINS` | comma-separated allowed origins |
| `RENDER_SERVICE_URL`, `INGESTION_SERVICE_URL` | internal service URLs |

With at least one provider key the pipeline produces real content. With neither,
job creation still works but every stage fails at its first LLM call — by
design, so a missing key is loud rather than silently filling the document with
placeholder prose.

## Tests

```bash
pytest tests -q                 # DB-backed tests skip if no Postgres is reachable
flake8 api workers providers ingestion render tests
mypy api workers providers --ignore-missing-imports
```

To include the database tests, point `DATABASE_URL` at a running Postgres and
apply the schema first:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema.sql
pytest tests -q
```

What is covered:

* `test_providers.py` — pool fallback, cooldown, tier preference, a bad key
  parking one provider instead of the whole pool, single-counted failures.
* `test_rls.py` — real isolation as `humanoid_app`: other users' jobs and
  documents invisible, no context means no rows, cross-user insert rejected.
* `test_pipeline.py` — all six stages against Postgres with only search, the
  LLM, and the render service stubbed. Asserts the finished Markdown has no
  `[cite:` tags, that the bibliography is numbered, and that the stored DOCX is
  a real zip. A second test proves a re-run skips completed stages.
* `test_api.py` — job creation, 404 on a malformed UUID, document not ready,
  retry while queued, cross-user isolation.
* `test_render.py`, `test_citations.py`, `test_search.py` — DOCX structure,
  citation numbering, and the URL guard.

`SKIP_DB_TESTS=1` forces the database tests off.

## Frontend

`npm install && npm run dev`. `tsc --noEmit` and `next build` are the two checks
CI runs. `NEXT_PUBLIC_DEV_MODE=true` skips the sign-in screen and relies on the
API's `DEV_AUTH_USER_ID`; leave it off for any shared deployment.

## Troubleshooting

**`ValueError: ProviderPool requires at least one provider`** — no provider key
is set. Add `GEMINI_API_KEY` or `OPENAI_API_KEY`, or set
`ALLOW_STUB_PROVIDER=true` if you only need the UI to move.

**`No usable sources were found for this topic`** — the research stage found
nothing above the 200-character floor, or search was unreachable. This fails the
job deliberately rather than drafting from an empty context.

**`permission denied for table jobs`** — you are connected as the wrong role, or
`humanoid_app` was never granted. Re-run `db/schema.sql`; it creates the role and
the grants.

**`expected str, got dict`** — a connection pool without the JSON codec. Every
pool must pass `init=init_connection`.

**`relation "documents" does not exist`** — an older database. Apply
`db/migrations/202610290001_documents_and_rls_enforcement.sql`.

**Jobs sit at `queued`** — the worker is not running, or cannot reach Redis.
`docker compose logs worker`.
