# Hunar

Hiring-automation platform. This is **Phase 1**: a runnable monorepo scaffold with a mock
voice provider proving frontend ↔ backend ↔ database connectivity. No real Hunar API calls,
people-search, or LLM features exist yet — those land in later phases.

## Architecture

```
hunar/
├── frontend/   Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + React Query
├── backend/    FastAPI (sync handlers, sync SQLModel/httpx) + PostgreSQL
└── docker-compose.yml
```

- **Frontend** never talks to Hunar (or any third party) directly. It only calls the
  backend's `/api/*` routes via `NEXT_PUBLIC_API_URL`.
- **Backend** is the only place that holds the Hunar API key and other secrets. It exposes a
  `VoiceProvider` abstraction (`app/providers/`) with two implementations:
  - `MockProvider` — returns fake agents/calls, used by default (`VOICE_PROVIDER=mock`).
  - `HunarProvider` — real Hunar client; every method currently raises `NotImplementedError`
    with a `TODO(phase2)` marker. Implemented in Phase 2.
- Handlers are **synchronous** on purpose (sync SQLModel sessions, sync httpx client).
  FastAPI runs sync def handlers in a threadpool, so this doesn't block the event loop, and
  it's much simpler to step through with a debugger.

### Module layout

Four product modules exist as route/router placeholders now, filled in over later phases:

| Module            | Frontend route        | Backend router                          | Phase |
|-------------------|------------------------|------------------------------------------|-------|
| Hiring Assistant  | `/hiring-assistant`    | `app/modules/hiring/router.py`           | 2     |
| People Search     | `/people-search`       | `app/modules/people_search/router.py`    | 4     |
| Outreach          | `/outreach`            | `app/modules/outreach/router.py`         | 5     |
| Attendance        | `/attendance`          | `app/modules/attendance/router.py`       | 6     |

`GET /api/agents` (backed by `modules/hiring/router.py`) is the one real endpoint in this
phase — it proves the provider abstraction and the frontend's data fetching both work.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
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
`HUNAR_API_KEY` etc. as `replace-me` / blank until Phase 2+.

**Security note:** the Hunar API key and all other provider keys live only in the backend's
environment. The frontend build never receives them — `NEXT_PUBLIC_API_URL` (a plain
localhost URL, not a secret) is the only environment variable exposed to browser code.

## Running with Docker

```bash
docker compose up --build
```

This starts Postgres, the backend (`:8010` → container `:8000`), and the frontend
(`:3010` → container `:3000`). The backend creates its tables on startup; no manual
migration step is needed in this phase.

## Running natively (no Docker)

Start Postgres (you can still use Docker for just this piece):

```bash
docker compose up db
```

Backend:

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
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
```

Open `http://localhost:3010` — the sidebar shows all four modules, and the overview page
displays a badge with the live agent count fetched from the backend.

## Tests & linting

```bash
cd backend && pytest              # health check + webhook signature verifier
cd backend && ruff check .
cd frontend && npx tsc --noEmit
```

## What's deliberately not here yet

- Real Hunar HTTP calls (`HunarProvider` methods raise `NotImplementedError`).
- People search, outreach, LLM content generation (`app/integrations/*` are empty stubs).
- Webhook event processing beyond signature verification (`/api/webhooks/hunar` verifies
  and returns `{"received": true}`; it doesn't act on the payload yet).
- Auth — this is single-tenant/local for now.
