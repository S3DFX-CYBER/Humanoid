# Humanoid — bug audit and fixes

Reviewed at commit `cf1b16f`. Everything listed as **Fixed** is in the patched
tree; **Open** items need a product decision rather than a patch.

The headline: before these changes the app could not complete a single job end
to end. Four independent blockers sat in a row — provider configuration, auth,
job persistence, and document delivery — so each one hid the next.

---

## P0 — the pipeline could never finish

| # | Where | Symptom | Root cause | Fix |
| --- | --- | --- | --- | --- |
| 1 | `providers/__init__.py` | Every LLM call failed with an auth error | `GeminiProvider("gemini-2.5-flash")` passed the *model name* into the `api_key` argument. OpenAI read `settings.openai_api_key`, a field that did not exist, and fell back to `"missing_key"` | Providers are built from `Settings` with explicit keyword arguments |
| 2 | `providers/__init__.py` | `tier="premium"` routed nowhere | Both providers were constructed with the default tier `"cheap"`, so tier matching was a no-op | Gemini is `premium` (drafting/outline), OpenAI is `cheap` (verify/style), with documented fallback |
| 3 | `providers/pool.py` | One bad API key killed jobs even when a second provider was configured | `ProviderFatalError` was re-raised immediately instead of moving to the next provider | Fatal errors park that provider for an hour and continue down the pool; only an all-fatal pool raises |
| 4 | `providers/__init__.py` | `ValueError: ProviderPool requires at least one provider` when no keys were set | `StubProvider` was imported but never added; there was no zero-provider path | Clear startup error, plus an opt-in `ALLOW_STUB_PROVIDER` for UI-only local work |
| 5 | `workers/worker.py` | `job_stages` inserts failed with *expected str, got dict* | `output_data` is `jsonb`, and asyncpg needs either a string or a registered codec | `json`/`jsonb` codecs registered on every pooled connection |
| 6 | `workers/stages.py` → `render/main.py` | DOCX was never delivered; every job reported "render unavailable" | The worker called `resp.json()` on an endpoint that returns a **file**; `document_url` was never produced by any service | Render returns bytes, the worker stores them in a new `documents` table, the API streams them at `/jobs/{id}/document/file` |
| 7 | `frontend/app/page.tsx` | Every request returned 401 | The client POSTed `{topic, user_id}` with no `Authorization` header; no sign-in flow existed anywhere | Typed API client with a bearer token, a Supabase sign-in screen, and a documented dev bypass |
| 8 | `api/routes/jobs.py` | `jobs.user_id` foreign key violation on the first job | Supabase identities live in `auth.users`; nothing created the matching `public.users` row | `ensure_user()` upserts the row on first authenticated request |
| 9 | `db/schema.sql` | The "strict RLS" claim was false — any query could read any user's rows | RLS was `ENABLE`d but not `FORCE`d, and the app connected as the table **owner** (superuser in the compose image) | `FORCE ROW LEVEL SECURITY` on all tables plus a non-owner `humanoid_app` role for the API and worker |
| 10 | `tests/test_providers.py` | 3 tests failed on `main`, so CI was red | Tests referenced `ProviderExhaustedError`, `ProviderPool()`, `pool.providers["cheap"]`, and `pool.status` — none of which existed | Tests rewritten against the real pool API (fallback, cooldown, tier preference, fatal parking) |
| 11 | `ingestion/Dockerfile` | Image build failed | `libgl1-mesa-glx` was removed in Debian 12 | Replaced with `libgl1` + `libglx-mesa0` |
| 12 | `Dockerfile`, `render/Dockerfile` | Installed package contained no code; render could not find templates | `pip install .` ran *before* the sources were copied; render never copied `templates/` | Sources copied first, templates included, non-root users added |
| 13 | `docker-compose.yml` | README promised `docker compose up` starts the app; no frontend ran | No frontend service, and no `frontend/Dockerfile` existed | Both added, with healthcheck-gated startup ordering |

## P1 — features that were promised but not implemented

| # | Where | Symptom | Fix |
| --- | --- | --- | --- |
| 14 | `ingestion/parsers.py` | Every upload returned `[PDF STUB] Received N bytes` | Real PyMuPDF / python-docx / python-pptx / pytesseract parsers, run off the event loop, with size caps and clean 422s |
| 15 | `workers/stages.py` | Final documents contained raw `[cite: 3f2a…]` UUIDs, and the bibliography listed every source whether cited or not | Format stage renumbers tags `[1]`, `[2]` in order of first appearance, orders the bibliography to match, and strips anything malformed |
| 16 | `workers/stages.py` | Verification results were written to the database and then ignored — the README's "missing citations are flagged" promise was unimplemented | Flagged claims now appear as a **Verification notes** section in the document |
| 17 | `providers/search.py` | Every search blocked the whole worker's event loop | `DDGS` runs in a thread; results are normalised and de-duplicated |
| 18 | `providers/search.py` | Worker fetched any URL a search result returned, including `127.0.0.1` and cloud metadata endpoints | `is_safe_url()` rejects non-HTTP schemes, private/loopback/link-local addresses, and dangerous ports; responses are size-capped |
| 19 | `providers/embedding.py` | Missing API key produced a zero-vector, which makes every source look identical to similarity search | Returns `None` and stores SQL NULL, with a warning; dimension mismatch is dropped rather than stored |
| 20 | `providers/gemini.py` | `google-generativeai` is end-of-life; `output_dimensionality` was unsupported; JSON was parsed by string-stripping code fences | Migrated to `google-genai` with native JSON mode (`response_mime_type="application/json"`) |
| 21 | `workers/worker.py` | Resume picked the wrong stage, left stages stuck at `running`, duplicated stage rows on retry, and wrote `failed` twice | Stage order comes from one shared list; stale `running` rows are failed on restart; resume is index-based; status written once |
| 22 | `api/routes/jobs.py` | A failed job was permanently dead — no way to continue it | `POST /jobs/{id}/retry` re-enqueues and resumes after the last completed stage |
| 23 | `api/routes/jobs.py` | `GET /jobs/not-a-uuid` returned 500 | Path UUIDs parsed up front, 404 instead of a stack trace |
| 24 | `api/routes/jobs.py` | A new arq Redis pool was created and closed per request; if enqueueing failed the job sat `queued` forever | One pool for the app's lifetime; enqueue failure marks the job failed and returns 503 |
| 25 | `api/dependencies.py` | 401s were swallowed by a bare `except`, the Supabase client was rebuilt per request, and `auth.get_user` (synchronous) blocked the loop | Cached client, `asyncio.to_thread`, precise error handling |
| 26 | `api/main.py` | No readiness signal, unused Redis client, stack traces leaked as 500 text | `/readyz` checks Postgres and Redis, shared Redis/arq clients closed on shutdown, JSON error envelope |
| 27 | `render/main.py` | `/render/pdf` returned HTTP 200 with `{"status": "error"}` in the body; LibreOffice blocked the loop and needed a writable `HOME` | Proper 5xx, `asyncio.to_thread`, isolated `-env:UserInstallation` profile |
| 28 | `render/main.py` | Templates were ignored — line spacing, margins, TOC, and page numbers never applied | Template loader with unit parsing (`1in`, `2.54cm`, `72pt`), static contents page, PAGE field in the header |
| 29 | `db/seed.sql` | Guard `server_version ILIKE '%supabase%'` can never be true; re-running the seed threw duplicate-key errors | Guard checks the database name and existing rows; inserts are idempotent |
| 30 | `db/schema.sql` | Not idempotent (`CREATE TYPE` unguarded) and drifted from the migrations — `outline_pending_approval` was missing | Guarded DDL, `IF NOT EXISTS` throughout, enum value added, unique index on `sources(job_id, url)` |
| 31 | `pyproject.toml` | `duckduckgo-search` was renamed upstream; `openai`/`google-genai` versions unpinned | Dependency set updated |

## P2 — frontend and design-system

| # | Where | Symptom | Fix |
| --- | --- | --- | --- |
| 32 | `app/layout.tsx` | Hardcoded `data-theme="dark"` while `design.md` defines a white canvas — implementation contradicted the design system | Light is canonical; dark follows `prefers-color-scheme`, with an explicit override still available |
| 33 | `app/page.tsx` | Nothing to show when a job finished — status said "COMPLETE" and the user got no document | Result panel with a DOCX download, Markdown preview, and citation count |
| 34 | `app/page.tsx` | Progress was a stream of log lines; you could not tell which stage was running | Six-row stage table with `[RUNNING] / [DONE] / [FAILED]`, a one-line result per stage, and the error inline |
| 35 | `app/page.tsx` | API errors were swallowed (`if (!res.ok) return;`) | `detail` from the API surfaces in an alert banner, with a **Continue from the last completed step** action |
| 36 | `app/page.tsx` | Input had a placeholder but no label; buttons read `RESEARCH` / `RUNNING...` | Real `<label>`, and outcome-naming copy: **Start research** / **Researching…** |
| 37 | `app/page.tsx` | Polling re-created intervals on every state change and never aborted in flight | `useResearchJob` hook with abortable requests, a failure budget, and clean teardown |
| 38 | `app/globals.css` | `.btn:disabled` unstyled, no focus-visible ring, no skip link, no reduced-motion handling, composer overflowed on mobile | All added, plus `.sr-only`, example-topic chips, and a stacked mobile composer |
| 39 | `app/page.tsx` | Sidebar "Sources" / "Documents" were dead `<div>`s that looked clickable | Real links where they work, marked `SOON` and non-interactive where they do not |

---

## Open — needs your call

1. **Outline approval.** `outline_pending_approval` is in the enum, but no
   endpoint pauses the pipeline. Decide whether approval is per-job or per-user
   opt-in, then add a `POST /jobs/{id}/approve` that enqueues the remaining
   stages.
2. **Uploads as sources.** The ingestion service now really parses files, but
   nothing stores them. The `uploads` table exists; the missing piece is an API
   route that calls `/extract`, stores the text as a `source`, and lets the
   user mark it required reading.
3. **Context selection.** Drafting currently receives every source for the job.
   Embeddings are stored but unused — retrieve the top-k per section with
   `embedding <=> $1::vector` instead of stuffing the prompt.
4. **Cancellation.** No way to stop a running job. A `cancelled` status plus an
   arq job abort would close that gap.
5. **Rate limits.** Quotas are counted in Postgres per request. Under load a
   Redis counter with a sliding window is cheaper.

## How this was verified

* `pytest tests -q` — **35 passed, 13 skipped** with no database; **47 passed,
  1 skipped** against a real Postgres (the skip is a DNS-dependent search test).
* The database suite includes a real end-to-end pipeline run: all six stages,
  citation renumbering, document persistence, and resume-after-crash, with only
  search, the LLM, and the render service stubbed (`tests/test_pipeline.py`).
* The RLS suite runs as the non-owner `humanoid_app` role, so it proves the
  policies bite rather than trusting that they exist.
* `flake8` clean, `mypy` clean on `api`, `workers`, `providers`.
* `tsc --noEmit` clean on the frontend.
* Render smoke over ASGI: a 37 KB DOCX that re-opens in python-docx with title,
  headings, numbered references, and no leftover cite tags; invalid payloads
  return 422. Ingestion round-trips a generated DOCX and rejects an unsupported
  type with 415.

Not verified here: `next build` (needs more memory than this sandbox allows).
The CI workflow runs the schema, lint, types, the full test suite, and a
frontend type check + build.

## Suggested merge order

The fixes are stacked, because each layer exposed the next: providers → database
/ RLS → API → worker → render + ingestion → frontend → infra and docs.
