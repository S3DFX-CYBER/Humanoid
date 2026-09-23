# Humanoid

AI-powered research and drafting assistant for academic papers, reports, and essays. 

Humanoid acts as a multi-stage background agent that runs async pipeline stages (Research → Outline → Draft → Verify → Style → Format) and produces submission-ready documents with fully verified citations. 

It is designed with a strictly minimal UI (black & white achromatic flat design) to enable zero-distraction focus, inspired by modern technical documentation.

## Architecture

- **Frontend**: Next.js (TypeScript, React 19)
- **API**: FastAPI (Python 3.12)
- **Database**: Supabase / PostgreSQL (with pgvector for embeddings and Row-Level Security for strict per-user isolation)
- **Job Orchestration**: Redis + arq (async worker framework)
- **Providers**: Gemini Flash (primary) + resilient fallback pool with backoff and tier-based routing
- **Ingestion & Render Services**: Fully isolated Docker containers processing untrusted inputs (PDFs, PPTs) and orchestrating headless LibreOffice

## Security & Constraints

- **Strict RLS**: Every database table is locked behind Row-Level Security scoped strictly to the current `auth.uid()`.
- **Zero Hallucination Generation**: RAG-constrained drafting means every claim requires a citation. Missing citations are explicitly flagged.
- **No Detector Evading Design**: This product does not optimize text to evade AI detection. It prioritizes clarity and truthfulness.

## Getting Started (Local Development)

1. Clone this repository.
2. Duplicate `.env.example` to `.env` and fill in your Supabase credentials.
3. Start the entire application using Docker Compose:

```bash
docker compose up
```

## Vercel deployment

The repository includes a root `vercel.json` so Vercel builds the Next.js app
from `frontend/` instead of attempting to deploy the FastAPI service. Set
`NEXT_PUBLIC_API_URL` in the Vercel project to the HTTPS URL of the separately
deployed API before enabling job creation. The API, Redis worker, and Postgres
database require a long-running deployment and are not Vercel functions.

## License

MIT License
