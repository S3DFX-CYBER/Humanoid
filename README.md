# Humanoid

AI-powered research and drafting assistant for academic papers, reports, and
essays.

Humanoid runs a six-stage background pipeline — **research → outline → draft →
verify → style → format** — and hands back a formatted DOCX with numbered
citations and an explicit list of any claims the fact-checker could not
support. The UI is deliberately achromatic and flat to keep attention on the
text.

## Architecture

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 15, React 19, TypeScript |
| API | FastAPI (Python 3.12), asyncpg |
| Database | Supabase / PostgreSQL + pgvector, Row-Level Security |
| Queue | Redis + arq |
| Providers | Gemini (`google-genai`) for drafting, OpenAI for cheap passes, with cooldown + fallback |
| Isolated services | `ingestion` (PDF/DOCX/PPTX/OCR, port 8001), `render` (DOCX/PDF, port 8002) |

## Documentation

| Document | Covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | services, request flow, the six stages, why the worker and the isolated containers exist |
| [docs/database.md](docs/database.md) | tables, the two database roles, how RLS scoping works, migrations |
| [docs/development.md](docs/development.md) | setup, environment variables, tests, troubleshooting |
| [docs/security.md](docs/security.md) | the two auth layers, the dev bypass, SSRF and upload hardening, what is *not* protected |
| [BUG_REPORT.md](BUG_REPORT.md) | the audit behind this code: every issue, its cause, its fix, and what still needs a decision |

## Quick start

```bash
cp .env.example .env          # add GEMINI_API_KEY and/or OPENAI_API_KEY
docker compose up --build
```

* API — http://localhost:8000/docs
* Frontend — http://localhost:3000
* Postgres — localhost:5432 · Redis — localhost:6379

The database is initialised from `db/schema.sql` and `db/seed.sql` on the first
boot only. To re-initialise: `docker compose down -v && docker compose up`.

### Local auth

`DEV_AUTH_USER_ID` in `.env` makes the API treat every request as that seeded
user, and `NEXT_PUBLIC_DEV_MODE=true` skips the sign-in screen. Both are
ignored when `ENVIRONMENT=production` — the API then requires a real Supabase
JWT (`Authorization: Bearer <access_token>`) and verifies it with Supabase
Auth before any query runs.

### Database roles

Two roles, on purpose:

* `humanoid` — owner. Runs migrations and seeds.
* `humanoid_app` — non-owner, non-superuser. The API and worker connect as this
  role, so Row-Level Security actually applies to them. `FORCE ROW LEVEL
  SECURITY` is set on every table; without it the owner bypasses all policies.

Every query that touches user data opens a transaction and sets
`request.jwt.claim.sub` first, which the local `auth.uid()` stub reads. The
worker receives the job's `user_id` in its queue payload for the same reason —
it never needs a privilege escalation to do its work.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/jobs` | Create a job and enqueue it |
| `GET` | `/jobs` | List your jobs (`limit`, `offset`) |
| `GET` | `/jobs/{id}` | Job status |
| `GET` | `/jobs/{id}/stages` | Per-stage status, output summary, errors |
| `GET` | `/jobs/{id}/document` | DOCX availability + Markdown body |
| `GET` | `/jobs/{id}/document/file` | Download the DOCX (Markdown fallback) |
| `POST` | `/jobs/{id}/retry` | Re-run a failed job, resuming after the last completed stage |
| `GET` | `/health`, `/readyz` | Liveness / dependency readiness |

## Tests

```bash
pip install -e ".[dev,render]"
pytest tests -v
```

Tests that need Postgres skip themselves when no database is reachable; point
`DATABASE_URL` at a running instance to include them. Lint and type checks:

```bash
flake8 api workers providers ingestion render tests
mypy api workers providers --ignore-missing-imports
```

## Design

`design.md` holds the design tokens (achromatic palette, Inter + JetBrains
Mono, 4px baseline grid, flat elevation). `frontend/app/globals.css` mirrors
them as CSS custom properties. Light is the canonical canvas; dark follows the
OS preference unless `data-theme` is set explicitly.

## Known gaps

* Outline approval (`outline_pending_approval`) exists in the schema but has no
  endpoint or UI yet — the pipeline runs straight through.
* The ingestion service parses uploads, but no API route stores them as
  sources yet.
* Drafting receives every source for the job; pgvector similarity selection is
  stored but not used to trim context.
* There is no cancel endpoint; a running job can only be waited out.

## License

MIT
