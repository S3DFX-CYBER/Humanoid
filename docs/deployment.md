# Deployment

The API, worker, Postgres, Redis, and the two isolated services are containers.
The frontend is a static-ish Next.js app and can live on any Node host. This
document covers the split that most often goes wrong: the frontend deployed on
its own, pointing at an API that is not reachable.

## What must exist before the frontend can work

1. **An API reachable over HTTPS.** The browser calls it directly, so
   `http://api:8000` is not enough — it needs a public URL.
2. **`CORS_ORIGINS` on the API must include the frontend's origin**, exactly,
   including scheme. `https://humanoid.example.com`, not `humanoid.example.com`.
3. **Three variables in the frontend's build environment** (see below). They are
   inlined at build time, so changing them requires a redeploy.

## Frontend

| Variable | Required | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | yes | public URL of the API, no trailing slash |
| `NEXT_PUBLIC_SUPABASE_URL` | for sign-in | from the Supabase project settings |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | for sign-in | the **anon** key; never the service key |
| `NEXT_PUBLIC_DEV_MODE` | no | must be unset or `false` in any deployment |

### Vercel

* **Root Directory must be `frontend`.** The repository root holds the Python
  services and has no `package.json`; if the root directory is left at the
  repository root, the build has nothing to build.
* Framework preset: Next.js. Build `npm run build`, output `.next`.
* Set the variables above under *Settings → Environment Variables* for
  Production **and** Preview, then redeploy — a build that ran without them
  bakes in the `http://localhost:8000` fallback.
* `/` is prerendered (`export const dynamic = "force-static"`), so the landing
  page is served as static HTML and needs no serverless invocation. If the
  deployment reports `FUNCTION_INVOCATION_FAILED` on `/`, the deployment is
  older than that change.

### Anywhere else

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=https://api.example.com npm run build
npm run start          # or serve .next with your platform's Node runtime
```

`frontend/Dockerfile` builds a standalone Node image if you prefer containers.

## API

```bash
docker compose up -d postgres redis render ingestion
# then the API and worker with real environment values
```

Required at minimum: `DATABASE_URL` (as `humanoid_app`), `REDIS_URL`,
`GEMINI_API_KEY` or `OPENAI_API_KEY`, `CORS_ORIGINS`, and — if you want real
authentication — `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`.

**Leave `DEV_AUTH_USER_ID` empty in production.** It is ignored when
`ENVIRONMENT=production`, but do not rely on that alone: it is a full
authentication bypass.

## First-run checklist

```bash
curl -fsS https://api.example.com/health    # liveness
curl -fsS https://api.example.com/readyz    # Postgres + Redis reachable
```

`/readyz` returning 503 names the failing dependency. A job created while Redis
is down returns 503 and is marked failed rather than sitting in `queued`.

## When the frontend shows an error page

The app has two error boundaries, so a crash renders a readable message with a
reference id instead of the platform's generic 500:

* `app/error.tsx` — a screen failed to render; the rest of the app still works.
* `app/global-error.tsx` — the root layout itself failed, usually a build or
  configuration problem.

Look the reference id up in the host's function logs. In order of likelihood:

1. `NEXT_PUBLIC_API_URL` missing from the build → the UI now says so explicitly.
2. Root Directory not set to `frontend` → the build fails before deploy.
3. CORS rejection → the browser console shows a CORS error and the request
   never reaches the API.
4. `NEXT_PUBLIC_SUPABASE_*` missing → the sign-in screen explains it rather than
   failing silently.
