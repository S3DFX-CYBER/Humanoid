# Security model

## Two layers, both required

1. **Authentication** — `api/dependencies.py` verifies the Supabase JWT with
   Supabase Auth and resolves it to a user id. It runs before any route body and
   before any query. The call is synchronous in the SDK, so it is wrapped in
   `asyncio.to_thread` to keep the event loop free.
2. **Authorisation** — every query that touches user data runs inside a
   transaction with `request.jwt.claim.sub` set, which `auth.uid()` reads. Row
   Level Security then scopes rows. The API and worker connect as the
   non-owner `humanoid_app` role, and every table is `FORCE ROW LEVEL SECURITY`,
   so the policies apply even to the owner.

The first layer alone would be enough to *authenticate*; the second is what stops
a bug in one query from returning another user's rows.

### The development bypass

`DEV_AUTH_USER_ID` makes every request run as that user. It is refused whenever
`ENVIRONMENT=production`, and it logs a warning on every request while active.
It exists so the UI can be developed without a Supabase project. Never set it on
a shared deployment — it is a full authentication bypass.

## Secrets

* Keys arrive through the environment only; nothing is committed. `.env` is
  gitignored, `.env.example` carries placeholders.
* The worker never sees a user token. It receives the job's `user_id` in its
  queue payload and sets its own RLS context from it.
* `SUPABASE_SERVICE_KEY` bypasses RLS at the Supabase layer by design. It is
  only used server-side, never sent to the browser; the frontend gets the anon
  key.

## Fetching untrusted URLs

The research stage fetches whatever a search engine returns, which makes the
worker an SSRF candidate. `providers/search.py`:

* accepts only `http`/`https` and rejects `localhost`, cloud metadata hostnames,
  and a blocklist of service ports;
* resolves the hostname and rejects private, loopback, link-local, reserved, and
  multicast addresses;
* **follows redirects by hand**, revalidating every hop — `follow_redirects=True`
  would let a public URL bounce to `169.254.169.254` after the first check;
* caps the response at 2 MB and ignores non-text content types.

## Parsing untrusted files

Uploads are opened only inside the `ingestion` container, which has no database
or Redis credentials and no route back into the API. Parsers are bounded
(25 MB upload cap, 500k character extraction cap) and a corrupt file produces a
422, not a crash. OCR text that cannot be extracted is reported, never guessed.

## Rendering

The `render` container runs LibreOffice, the most CVE-prone component here. It
receives structured JSON and returns a file: no credentials, no database, no
user identity. Conversions run with an isolated LibreOffice profile and a
timeout.

## What is not protected

* **Rate limiting is per-user, counted in Postgres.** Adequate for the current
  quotas, not for abuse at scale; a Redis sliding window is the next step.
* **No content moderation.** Topics are not screened; the product drafts from
  the sources it retrieves, and verification only checks claims against those
  sources.
* **`documents` are stored as `BYTEA` in Postgres.** Fine at current sizes; a
  few hundred MB of DOCX per database is the point to move to object storage.
* **No audit log** of who read which job. The RLS tests prove isolation, not
  access history.

## Reporting

Found something? Open a private security advisory on the repository rather than
a public issue.
