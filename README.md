# Hunar

Hiring-automation platform.

- **Phase 1** built a runnable monorepo scaffold with a mock voice provider proving
  frontend ↔ backend ↔ database connectivity.
- **Phase 2** (this phase) built the **Voice Core**: dispatch a voice call (or a batch) and
  reliably capture its structured outcome, no matter how or when the result arrives. Modules
  1–3 (Hiring Assistant, Outreach, Attendance) will be thin layers on top of this later.

People-search and LLM features don't exist yet — those land in later phases. Real Hunar API
calls (agents, numbers, dispatching a call, receiving webhooks) are implemented and have been
verified against the live API — see
[Verifying against the real Hunar API](#verifying-against-the-real-hunar-api-optional).

## Architecture

```
hunar/
├── frontend/   Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + React Query
├── backend/    FastAPI (sync handlers, sync SQLModel/httpx) + PostgreSQL + APScheduler
└── docker-compose.yml
```

- **Frontend** never talks to Hunar (or any third party) directly. It only calls the
  backend's `/api/*` routes via `NEXT_PUBLIC_API_URL`.
- **Backend** is the only place that holds the Hunar API key and other secrets. It exposes a
  `VoiceProvider` abstraction (`app/providers/`) with two implementations:
  - `MockProvider` — simulates the full call lifecycle in the background (no live key, no
    phone, no ngrok), used by default (`VOICE_PROVIDER=mock`).
  - `HunarProvider` — real Hunar client. Implemented (sync httpx, error mapping, retries),
    but not exercised by an automated test since it needs a live key - see
    [Verifying against the real Hunar API](#verifying-against-the-real-hunar-api-optional).
- Handlers are **synchronous** on purpose (sync SQLModel sessions, sync httpx client).
  FastAPI runs sync def handlers in a threadpool, so this doesn't block the event loop, and
  it's much simpler to step through with a debugger. No Celery/Redis - background work
  (call simulation, the polling reconciler) runs on an in-process APScheduler
  `BackgroundScheduler`, started in `main.py`'s lifespan.

### The Voice Core

`app/services/calls.py::apply_call_update` is the one place Call state actually changes. Two
paths feed it, and both normalize into the same `CallUpdate` shape first:

- **Webhook** (`POST /api/webhooks/hunar`) — verifies the HMAC-SHA256 signature
  (`app/providers/webhooks.py`), then calls `apply_call_update(source=webhook)`.
- **Poller** (`app/services/poller.py`, an APScheduler job every `POLL_INTERVAL_SECONDS`) —
  finds non-terminal calls whose `updated_at` is older than `POLL_STALE_AFTER_SECONDS`, asks
  the provider for its current view, and calls `apply_call_update(source=poll)`.

`apply_call_update` is idempotent: it compares the incoming update against the call's last
applied payload and no-ops (no duplicate `CallEvent`, no state change) if they're identical.
This is what lets the webhook and the poller converge on exactly the same result regardless of
which one gets there first, or whether the webhook arrives at all.

`MockProvider` (`app/providers/mock.py`) keeps its own independent in-memory state per call -
like a real remote provider would - and progresses it through
`NOT_STARTED → RINGING → IN_PROGRESS → COMPLETED` on a background job. Intermediate
transitions are pushed straight into the DB in-process (`CallEvent.source = mock`); the
terminal transition is sent as a **real, HMAC-signed HTTP webhook POST back to this same
backend** (`CallEvent.source = webhook`), so the actual signature-verified webhook path gets
exercised with zero external dependencies. If that self-POST fails for any reason, the poller
picks the call up within `POLL_STALE_AFTER_SECONDS` and reconciles it anyway
(`CallEvent.source = poll`) - both paths land on identical state.

### Module layout

Four product modules exist as route/router placeholders, filled in over later phases - they'll
be built on top of the voice core above:

| Module            | Frontend route        | Backend router                          | Phase |
|-------------------|------------------------|------------------------------------------|-------|
| Hiring Assistant  | `/hiring-assistant`    | `app/modules/hiring/router.py`           | 3     |
| People Search     | `/people-search`       | `app/modules/people_search/router.py`    | 4     |
| Outreach          | `/outreach`            | `app/modules/outreach/router.py`         | 5     |
| Attendance        | `/attendance`          | `app/modules/attendance/router.py`       | 6     |

The voice core's own routes live in `app/modules/voice/router.py`, mounted directly under
`/api` (no extra prefix): `GET /agents`, `GET /numbers`, `POST|GET /campaigns`,
`POST|GET /calls`, `GET /calls/{id}`.

### Call Console (dev)

A developer-only page at `/call-console` (separate section in the sidebar, below the 4
product modules) dispatches a call straight against the voice core and polls it live - the
fastest way to see the whole pipeline work end to end, and a handy debugging tool once real
modules exist. Not part of the product; nothing here survives into later phases as user-facing
UI.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+ (the Docker image uses 3.11; if only 3.10 is available natively, the code
  still runs fine on 3.10 - nothing here is 3.11-only)
- Docker + Docker Compose (for the Docker path, and/or for running just Postgres locally)

## A note on ports

This scaffold defaults to **non-standard host ports** — backend `8010`, frontend `3010`,
Postgres `5442` — instead of the more common 8000/3000/5432, because this project was
built on a dev machine where those default ports were already in use by other projects.
Container-internal ports are still the framework defaults (8000/3000/5432); only the
host-side mapping changed. If you're on a clean machine and prefer the conventional ports,
override `BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_PORT` (compose) or edit `DATABASE_URL` /
`NEXT_PUBLIC_API_URL` (native) back to 8000/3000/5432 — nothing in the code assumes a
specific port number.

## Environment setup

```bash
cp .env.example .env          # backend reads this
cp frontend/.env.local.example frontend/.env.local   # frontend reads this (native only)
```

`VOICE_PROVIDER=mock` is the default — the app runs with zero real credentials. Leave
`HUNAR_API_KEY` etc. as `replace-me` / blank until you actually want to hit the real API.

**Security note:** the Hunar API key and all other provider keys live only in the backend's
environment. The frontend build never receives them — `NEXT_PUBLIC_API_URL` (a plain
localhost URL, not a secret) is the only environment variable exposed to browser code.

## Running with Docker

```bash
docker compose up --build
```

This starts Postgres, the backend (`:8010` → container `:8000`), and the frontend
(`:3010` → container `:3000`). The backend creates its tables on startup.

The `Call` table's shape changed in Phase 2. If you have an old Phase-1 volume around, reset
it once:

```bash
docker compose down -v && docker compose up --build
```

## Running natively (no Docker)

Start Postgres (you can still use Docker for just this piece):

```bash
docker compose up db
```

Backend:

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate   # python3 works too if 3.11 isn't installed
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev -- --port 3010
```

Or use the Makefile shortcuts (`make backend`, `make frontend`) once `.venv` exists.

## Makefile

```bash
make dev        # docker compose up --build
make backend    # run backend natively on :8010
make frontend   # run frontend natively on :3010
make lint       # ruff (backend) + tsc --noEmit (frontend)
make test       # pytest (backend)
```

## Verifying it works

```bash
curl localhost:8010/health
# {"status":"ok","provider":"mock"}

curl localhost:8010/api/agents
# [{"id":"agent_mock_001", ...}, ...]

curl -X POST localhost:8010/api/calls -H "Content-Type: application/json" -d '{
  "agent_id": "agent_mock_001", "callee_name": "Jane Doe", "mobile_number": "+15551234567",
  "custom_data": {"role_title": "Backend Engineer", "min_experience_years": 3}
}'
# {"id": "...", "status": "NOT_STARTED", ...} - poll GET /api/calls/{id}; within
# MOCK_CALL_DURATION_SECONDS (8s default) it reaches "COMPLETED" with a result and
# recording_url, and its `events` show the status source (mock/webhook/poll).
```

Or open `http://localhost:3010/call-console` and dispatch a call from the UI: pick an agent,
fill in callee name/number/custom data, hit dispatch, and watch the status badge and timeline
update live until it reaches `COMPLETED` with a result and recording link.

## Tests & linting

```bash
cd backend && pytest              # requires a reachable Postgres - `docker compose up db` first
cd backend && ruff check .
cd frontend && npx tsc --noEmit
```

`pytest` creates and uses its own `<database>_test` database (e.g. `hunar_test`), separate
from whatever `DATABASE_URL` points at - it never touches your dev/live data, even though both
share the same Postgres server by default.

## Verifying against the real Hunar API (optional)

`HunarProvider` is implemented but not exercised by CI - it needs a live key and, for the
webhook path, a publicly reachable URL (ngrok). It **has** been verified against the live API
for real, including three real dispatched calls with full webhook delivery. To reproduce:

1. Set `VOICE_PROVIDER=hunar`, `HUNAR_API_KEY=<real key>` in `.env`.
2. `curl localhost:8010/api/agents` and `/api/numbers` should return real data.
3. To test a real call end to end: run `ngrok http 8010`, set `PUBLIC_BASE_URL` to the
   `https://*.ngrok-free.dev` URL it prints, restart the backend, then dispatch a call to a
   number that has consented to receiving it, via `/call-console` or `POST /api/calls`.

**Confirmed facts about the real API** (none of this was documented anywhere - discovered by
testing against it):

- All list routes use a **trailing slash** (`/agents/`, `/numbers/`, `/calls/`) and are
  **paginated**: `{"count", "next", "previous", "results": [...]}`, not a bare array.
- Real `Agent.custom_variables` is a **list of variable names** (`["location", "company",
  "job_role"]`), not a dict of `{name: type_hint}` like MockProvider's fake agents use.
- `duration_seconds` comes back as a **float** (e.g. `50.0`), not an int.
- `callback_config`'s field names are `call_status_callback_url`,
  `call_recording_callback_url`, `call_result_callback_url`, `call_summary_callback_url` -
  Hunar's 422 response names the allowed fields if you send the wrong ones.
- **Webhooks are partial and event-scoped**, not full snapshots: `call_status_updated` carries
  status/duration/timestamps but no result or recording; `call_recording_done` carries only a
  `recording_url`; `call_result_done` carries only a `result`. `apply_call_update` merges
  fields (a field absent from a given webhook body means "not part of this update," not
  "clear it") - this was a real bug caught during live verification, where a later partial
  webhook was blanking out an already-correct status.
- The real HMAC signing scheme (secret, message format, header names) matches
  `verify_hunar_signature` exactly, confirmed by successfully verifying real signed webhooks.

## What's deliberately not here yet

- People search, outreach, LLM content generation (`app/integrations/*` are empty stubs).
- JD parsing, ASR, scorecards, or any other module business logic. `transcript` exists on
  `Call` as a field but is unused - a seam for a later ASR phase.
- Webhook event processing beyond applying the status update (no notifications, no side
  effects triggered by a call completing).
- Auth — this is single-tenant/local for now.
- Alembic / migrations — schema changes mean resetting the dev DB (`docker compose down -v`).
