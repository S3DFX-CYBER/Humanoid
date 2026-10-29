# Architecture

Humanoid turns a research topic into a formatted document through six
background stages. The API is a thin, authenticated front end over a queue; all
the work happens in the worker.

```
                    ┌──────────────┐
  browser ─────────▶│  Next.js     │  sign-in, job composer, stage progress,
                    │  (port 3000) │  document download
                    └──────┬───────┘
                           │  Bearer JWT
                    ┌──────▼───────┐        ┌─────────────┐
                    │  FastAPI     │───────▶│  Redis      │
                    │  (port 8000) │ enqueue│  + arq      │
                    └──────┬───────┘        └──────┬──────┘
                           │                       │  run_pipeline(job_id, user_id)
                    ┌──────▼───────────────────────▼──────┐
                    │  Postgres + pgvector                │
                    │  jobs · job_stages · sources        │
                    │  verification_results · documents   │
                    └──────▲──────────────────────────────┘
                           │  RLS-scoped writes
                    ┌──────┴───────┐   ┌──────────────┐   ┌─────────────┐
                    │   worker     │──▶│  render      │   │  ingestion  │
                    │  (arq)       │   │  (port 8002) │   │  (port 8001)│
                    └──────┬───────┘   └──────────────┘   └─────────────┘
                           │  HTTPS
                    ┌──────▼───────┐
                    │ Gemini /     │
                    │ OpenAI       │
                    └──────────────┘
```

## Why the worker is separate

A single job makes dozens of network calls (search, page fetches, an LLM call
per section, one per claim). Doing that inside a request would tie the HTTP
worker up for minutes and lose all progress on a deploy. The API only writes a
`jobs` row and enqueues it; the worker walks the stages and persists each
result, so a crash resumes instead of restarting.

## The stages

Defined once, in `workers/pipeline.py`, so the API, the worker, and the tests
cannot disagree about order.

| Stage | Status shown | Does |
| --- | --- | --- |
| research | `researching` | generates search queries, fetches pages, extracts text, embeds and stores sources |
| outline | `outlining` | title, thesis, section list from the sources |
| draft | `drafting` | one LLM call per section, each claim tagged `[cite: <source-uuid>]` |
| verify | `verifying` | one cheap LLM call per claim against the cited source; verdict persisted |
| style | `styling` | clarity rewrite that must preserve every citation tag, or is rejected |
| format | `formatting` | renumbers citations, compiles Markdown, renders DOCX, stores bytes |

Resume is index-based: a re-run starts after the furthest *completed* stage in
pipeline order. Stages left `running` by a crashed worker are failed on pickup,
so nothing is stuck forever.

## Isolated services

`ingestion` and `render` are deliberately separate containers with no database
or Redis credentials:

* `ingestion` parses untrusted uploads (PDF, DOCX, PPTX, images/OCR). It is the
  only place a hostile file is opened.
* `render` runs headless LibreOffice, the heaviest and most CVE-prone binary in
  the stack. It takes structured JSON and returns a file; it never sees a user
  id or a token.

The worker reaches both over the compose network by URL, so either can be
swapped or scaled without touching the pipeline.

## Where the output lives

The rendered DOCX is stored in `documents` (`BYTEA`, one row per job per kind)
rather than an object store, so a finished document needs no extra service to
configure and inherits the same RLS as everything else. `GET
/jobs/{id}/document/file` streams it, falling back to the Markdown body if
rendering failed.

## Known gaps

Tracked in `BUG_REPORT.md`: outline approval has no endpoint, uploads are parsed
but not yet stored as sources, pgvector similarity is stored but unused when
selecting drafting context, and there is no cancel endpoint.
