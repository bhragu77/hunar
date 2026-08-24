# Hunar

A unified HR voice-AI platform: three product modules — an **AI Hiring Assistant**, **People
Search & Reachout**, and **Attendance** (phone-call roll-call across distributed sites) — built
on one reusable **Voice Core** that dispatches calls and reliably captures their outcome no
matter how or when the result arrives.

**Live demo:** https://hunar-eta.vercel.app
**Repo:** https://github.com/bhragu77/hunar

Every provider defaults to **mock** (`VOICE_PROVIDER` / `LLM_PROVIDER` /
`TRANSCRIPTION_PROVIDER` / `PEOPLE_SEARCH_PROVIDER`), so the whole app — all three modules,
end to end — runs with **zero external API keys**. That's deliberate: the live demo link above
has to keep working after the Hunar API key used during development is revoked.

## Quickstart (2 commands)

```bash
git clone <this-repo> && cd hunar
docker compose up --build
```

Open `http://localhost:3010`. No `.env` file needed - every provider defaults to mock. See
[Running with Docker](#running-with-docker) for details, or [Running natively](#running-natively-no-docker)
if you'd rather not use Docker.

## 60-second demo script

**Hiring Assistant** (`/hiring-assistant`) - ~20s
1. New interview → title + JD/criteria text + pick an agent.
2. Add 2-3 candidates, dispatch.
3. Watch each candidate flip `NOT_STARTED → RINGING → IN_PROGRESS → COMPLETED` live, then show
   a generated transcript and AI scorecard (recommendation + competency scores). Funnel updates
   as candidates finish.

**People Search & Reachout** (`/outreach`) - ~20s
1. New campaign → paste a JD. Watch it get parsed into search criteria (titles, skills,
   seniority, locations) and auto-create a matching voice agent - no manual agent config.
2. Search → a page of sourced candidate profiles appears (name, title, mobile where available).
3. Select a few → Dispatch. Watch the funnel move candidates through
   Sourced → Contacting → Interested / Not interested / Follow-up required / No response as
   calls complete.

**Attendance** (`/attendance`) - ~20s
1. Today tab: if empty, click **Seed demo data** (~100 locations, ~1,000 workers - idempotent,
   instant). On the deployed link this is already done for you on first boot.
2. Create + dispatch today's roll-call - one supervisor call per location, dispatched in
   parallel.
3. Watch the heatmap fill in live as supervisor calls complete and get reconciled into
   present/absent per worker; drill into a location's roster, or manually override one record.
4. Design tab renders the full [design writeup](docs/attendance-design.md) for this module in
   the same page.

## Architecture

```
                     ┌─────────────────────────┐
                     │  Next.js frontend        │
                     │  (App Router, shadcn/ui,  │
                     │   React Query)            │
                     └────────────┬─────────────┘
                                  │  NEXT_PUBLIC_API_URL (public, non-secret)
                                  ▼
                     ┌─────────────────────────┐
                     │  FastAPI backend (sync)   │
                     │  ┌──────────────────────┐ │
                     │  │ Module routers:       │ │
                     │  │ hiring / outreach /   │ │
                     │  │ people_search /       │ │
                     │  │ attendance            │ │
                     │  └──────────┬───────────┘ │
                     │             ▼              │
                     │  ┌──────────────────────┐ │      ┌───────────────────┐
                     │  │   Voice Core          │◄┼──────┤ Webhook receiver   │
                     │  │ Campaign + Call model  │ │      │ (HMAC-verified,    │
                     │  │ apply_call_update()    │◄┼──┐   │ idempotent)        │
                     │  │  - the ONE place       │ │  │   └───────────────────┘
                     │  │    Call state changes  │ │  │
                     │  └──────────┬───────────┘ │  │   ┌───────────────────┐
                     │             │              │  └───┤ Polling reconciler │
                     │             ▼              │      │ (APScheduler job)  │
                     │  ┌──────────────────────┐ │      └─────────┬─────────┘
                     │  │  VoiceProvider         │ │                │
                     │  │  (Hunar | Mock)        │◄┼────────────────┘
                     │  └──────────────────────┘ │
                     │                            │
                     │  Pluggable integrations:    │
                     │  LLM (mock|anthropic|openai) │
                     │  Transcription (mock|openai) │
                     │  People search (mock|apollo|pdl) │
                     └────────────┬─────────────┘
                                  ▼
                          ┌───────────────┐
                          │  PostgreSQL    │
                          └───────────────┘
```

- **Frontend** never talks to Hunar (or any third party) directly - only the backend's `/api/*`
  routes, via `NEXT_PUBLIC_API_URL` (a plain URL, not a secret).
- **Backend** is the only place holding the Hunar API key and every other provider key. It
  exposes a `VoiceProvider` abstraction (`app/providers/`) with two implementations:
  `MockProvider` (simulates the full call lifecycle in-process, no live key/phone/ngrok needed -
  used by default) and `HunarProvider` (real client, sync httpx, verified against the live API).
- Handlers are **synchronous** on purpose - sync SQLModel sessions, sync httpx client. FastAPI
  runs them in a threadpool, so this doesn't block the event loop, and it's simple to step
  through with a debugger. No Celery/Redis - background work (call simulation, the polling
  reconciler, the post-call pipeline) runs on an in-process APScheduler `BackgroundScheduler`.

### The Voice Core

`app/services/calls.py::apply_call_update` is the **one place** Call state actually changes.
Two paths feed it, both normalized into the same `CallUpdate` shape first:

- **Webhook** (`POST /api/webhooks/hunar`) - verifies the HMAC-SHA256 signature
  (`app/providers/webhooks.py`), then calls `apply_call_update(source=webhook)`.
- **Poller** (`app/services/poller.py`, an APScheduler job every `POLL_INTERVAL_SECONDS`) -
  finds non-terminal calls whose `updated_at` is older than `POLL_STALE_AFTER_SECONDS`, asks
  the provider for its current view, and calls `apply_call_update(source=poll)`.

`apply_call_update` is idempotent: it compares the incoming update against the call's last
applied payload and no-ops (no duplicate `CallEvent`, no state change) if they're identical.
This is what lets the webhook and the poller converge on exactly the same result regardless of
which one gets there first, or whether the webhook arrives at all.

`MockProvider` keeps its own independent in-memory state per call - like a real remote provider
would - and progresses it through `NOT_STARTED → RINGING → IN_PROGRESS → COMPLETED` on a
background job. The terminal transition is sent as a **real, HMAC-signed HTTP webhook POST back
to this same backend**, so the actual signature-verified webhook path gets exercised with zero
external dependencies; if that self-POST fails for any reason, the poller picks the call up and
reconciles it anyway - both paths land on identical state.

The moment a call first reaches `lifecycle_status=COMPLETED` with a non-null `result`,
`apply_call_update` schedules a one-off **post-call pipeline** job
(`app/services/post_call.py`): transcript generation, then a module-specific step (AI scorecard
for Hiring, an outreach recap for Reachout, roster reconciliation for Attendance). All mock by
default, so every module's pipeline runs with zero network calls.

### The three modules

Each module reuses the *exact same* Campaign/Call core - none of them reimplement webhook
handling, polling, or `apply_call_update`. Only the mapping onto Campaign/Call, and the
post-call pipeline step, differ:

| Module | Campaign IS | Call IS | Post-call step |
|---|---|---|---|
| **Hiring Assistant** | an interview (`module=hiring`) | a candidate screen | AI scorecard (recommendation + competency scores) |
| **People Search & Reachout** | an outreach campaign (`module=outreach`), with criteria parsed from a JD and an auto-created voice agent | a call to a sourced candidate | Outreach recap → funnel bucket |
| **Attendance** | a daily roll-call run (`module=attendance`) | a supervisor's roll-call call for one location | Roster reconciliation into per-worker `AttendanceRecord`s |

Attendance's own design writeup (scale, phone-call-only constraints, roll-call vs. missed-call
paths, and how each maps onto the platform above) lives in
[`docs/attendance-design.md`](docs/attendance-design.md) and also renders inside the app's
Attendance → Design tab.

A developer-only **Call Console** (`/call-console`) dispatches a call straight against the
Voice Core and polls it live - the fastest way to see the whole pipeline work end to end.

## Key design decisions

- **Provider abstraction + a full mock lifecycle, not just a mock response.** `MockProvider`
  doesn't stub one HTTP call - it runs the same status lifecycle, webhook signing, and
  idempotent convergence a real provider would, in-process. That's what lets a reviewer open
  the deployed link days from now, after the real Hunar key is revoked, and still see the whole
  product work end to end.
- **Webhook and polling converge on one update path, not two.** Real async voice APIs deliver
  webhooks unreliably (or not at all, if your backend was down). Rather than trust one channel,
  both normalize into the same `CallUpdate` and hit the same idempotent `apply_call_update` -
  whichever arrives first wins, and a duplicate or late arrival is a safe no-op.
- **One Campaign/Call core reused across all three modules**, not three disconnected apps built
  against a shared library. An interview, an outreach campaign, and a roll-call run are all just
  a `Campaign` with a different `module` tag; a candidate screen, a reachout call, and a
  supervisor call are all just a `Call`. New product surface only ever adds a mapping and a
  post-call step, never a parallel dispatch/webhook/poll implementation.
- **Zero-external-key operation by default.** Every provider - voice, LLM, transcription, people
  search - has a mock implementation that makes zero network calls and is the default. This
  isn't just a dev convenience; it's what makes the deployed link gradeable without handing out
  live credentials, and safe to leave running indefinitely.

## What's real vs. mocked

| Piece | Status |
|---|---|
| Voice dispatch, webhook signature verification, polling reconciler | **Real**, and verified against the live Hunar API (see below) - `MockProvider` is a full simulation of the same lifecycle, not a stand-in for untested code |
| JD → search criteria parsing, agent auto-design | **Real** logic; the LLM step itself is mocked by default (deterministic, keyword-based) - set `LLM_PROVIDER=anthropic`/`openai` for real generation |
| AI scorecards / outreach recaps / transcripts | **Real** pipeline and schema; mock backends synthesize plausible content deterministically from the call's result, no network. Set `LLM_PROVIDER` / `TRANSCRIPTION_PROVIDER` to a real backend to generate them for real |
| People search (candidate sourcing) | **Real** dedupe/upsert logic; mock backend generates synthetic-but-realistic profiles. `apollo`/`pdl` backends are implemented for real sourcing |
| Attendance roll-call, missed-call inbound, roster reconciliation | **Real**, running at full demo scale (100 locations / ~1,000 workers) on mock voice |
| Supervisor roll-call name matching | **Simplified** - the mock result generator returns present/absent employee-ID lists directly; a production version would need real fuzzy name matching against a roster from natural speech/ASR output |
| Real ASR (speech-to-text) | Only wired for `TRANSCRIPTION_PROVIDER=openai`; mock synthesizes plausible transcript text instead of transcribing audio |
| Enrichment credits for phone numbers | Not implemented - Apollo/PDL's real APIs meter/charge for phone number reveals; the integration handles it, but no budget/quota tracking exists |
| Auth / multi-tenancy | Not implemented - this is single-tenant, unauthenticated, for demo/grading purposes |
| Migrations | None - `SQLModel.metadata.create_all()` on startup is the documented approach; a schema change means resetting the dev DB |

**On Proxycurl:** the assignment's suggested people-search provider list included Proxycurl, but
Proxycurl shut down in July 2025 (after a lawsuit from LinkedIn) - it's gone. This project
integrates **Apollo** and **PDL** (People Data Labs) instead, both still-active alternatives with
similar person-search APIs.

## Tech stack

- **Frontend**: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + React Query
- **Backend**: FastAPI (sync handlers, sync SQLModel/httpx) + PostgreSQL + APScheduler
  (`BackgroundScheduler`, no Celery/Redis)
- **Voice**: Hunar (real) / an in-process mock with an identical lifecycle
- **LLM**: Anthropic / OpenAI (real) / a deterministic mock
- **People search**: Apollo / PDL (real) / a deterministic mock

## Environment variables

Full reference: [`.env.example`](.env.example) (backend) and
[`frontend/.env.local.example`](frontend/.env.local.example) (frontend, native dev only).

| Variable | Default | Purpose |
|---|---|---|
| `VOICE_PROVIDER` | `mock` | `mock` \| `hunar` |
| `HUNAR_API_KEY` / `HUNAR_BASE_URL` | `replace-me` / real base URL | Only read when `VOICE_PROVIDER=hunar` |
| `DATABASE_URL` | local Postgres | Normalizes a `postgres://` scheme (Render/Railway) to `postgresql://` automatically |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3010` | Comma-separated allowed origins |
| `INTERNAL_BASE_URL` | `http://localhost:8010` | This backend's own URL, so `MockProvider` can self-POST its webhook |
| `PUBLIC_BASE_URL` | empty | Public https base for real Hunar webhooks (ngrok / deploy) |
| `MOCK_WEBHOOK_SECRET` | dev placeholder | `MockProvider` signs its self-sent webhooks with this |
| `MOCK_CALL_DURATION_SECONDS` | `8` | How long a simulated call takes to reach `COMPLETED` |
| `POLL_INTERVAL_SECONDS` / `POLL_STALE_AFTER_SECONDS` | `10` / `20` | Polling reconciler cadence / staleness threshold |
| `LLM_PROVIDER` / `LLM_MODEL` | `mock` / empty | `mock` \| `anthropic` \| `openai`, for scorecards/summaries |
| `TRANSCRIPTION_PROVIDER` | `mock` | `mock` \| `openai` \| `disabled` |
| `ENABLE_POST_CALL_PIPELINE` | `true` | Master switch for the transcript/scorecard/outreach/attendance post-call step |
| `PEOPLE_SEARCH_PROVIDER` / `PEOPLE_SEARCH_MAX_RESULTS` | `mock` / `25` | `mock` \| `apollo` \| `pdl` |
| `AGENT_AUTOCREATE` | `true` | Auto-create the outreach voice agent from the JD |
| `ATTENDANCE_PRESENT_RATE` / `ATTENDANCE_MISSED_CALL_RATE` | `0.85` / `0.4` | Mock roll-call demo realism knobs |
| `DEMO_SEED_ON_START` | `false` | Seed the Attendance demo dataset on boot if empty (idempotent). Set `true` on the deployed backend so the live link is pre-populated; left `false` locally on purpose - use the in-app "Seed demo data" button instead |
| `APOLLO_API_KEY` / `PDL_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | empty | Only read when the matching provider is selected |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8010` | The only var the frontend build gets - a plain URL, never a secret |

## Security

- The Hunar API key (and every other provider key) lives **only** in the backend's environment.
  The frontend build never receives them - `NEXT_PUBLIC_API_URL` (a plain localhost/deployed
  URL, not a secret) is the only environment variable exposed to browser code.
- `.env` and `frontend/.env.local` are gitignored and were never committed - only
  `.env.example` / `frontend/.env.local.example` (placeholders) are tracked.
- If a real key is ever accidentally exposed (committed, logged, pasted somewhere public),
  **rotate it immediately** in the Hunar/Anthropic/OpenAI/Apollo/PDL dashboard - treat it as
  compromised, don't just remove it from the file.
- The deployed link runs on mock providers by default specifically so it never needs a live key
  in the first place - see [DEPLOYMENT.md](DEPLOYMENT.md).

## A note on ports

This scaffold defaults to **non-standard host ports** — backend `8010`, frontend `3010`,
Postgres `5442` — instead of the more common 8000/3000/5432, because this project was built on
a dev machine where those default ports were already in use by other projects.
Container-internal ports are still the framework defaults (8000/3000/5432); only the host-side
mapping changed. Override `BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_PORT` (compose) or edit
`DATABASE_URL` / `NEXT_PUBLIC_API_URL` (native) if you prefer the conventional ports - nothing
in the code assumes a specific port number.

## Running with Docker

```bash
docker compose up --build
```

Starts Postgres, the backend (`:8010` → container `:8000`), and the frontend (`:3010` →
container `:3000`) - no `.env` required, every provider defaults to mock. The backend creates
its tables on startup.

If you have an old volume from before the `Call` table's Phase-2 shape change, reset it once:

```bash
docker compose down -v && docker compose up --build
```

## Running natively (no Docker)

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Start Postgres (Docker for just this piece is fine):

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

```bash
make dev        # docker compose up --build
make backend    # run backend natively on :8010
make frontend   # run frontend natively on :3010
make lint       # ruff (backend) + tsc --noEmit (frontend)
make test       # pytest (backend)
```

## Tests & linting

```bash
cd backend && pytest              # requires a reachable Postgres - `docker compose up db` first
cd backend && ruff check .
cd frontend && npx tsc --noEmit
cd frontend && npx eslint .
```

`pytest` creates and uses its own `<database>_test` database (e.g. `hunar_test`), separate from
whatever `DATABASE_URL` points at - it never touches dev/live data, even sharing the same
Postgres server by default. The suite runs 35 tests and passes deterministically (verified 10
consecutive clean runs) - background scheduler jobs (mock call simulation, the post-call
pipeline) are drained via `app/core/scheduler.py::wait_until_idle()` before each test's table
cleanup and before any test asserts on a background job's result, so nothing races.

## Verifying it works

```bash
curl localhost:8010/health
# {"status":"ok","provider":"mock"}

curl localhost:8010/api/agents
# [{"id":"agent_mock_001", ...}, ...]
```

Or just open `http://localhost:3010` and follow the [60-second demo script](#60-second-demo-script)
above.

## Verifying against the real Hunar API (optional)

`HunarProvider` is implemented but not exercised by the automated test suite - it needs a live
key and, for the webhook path, a publicly reachable URL (ngrok). It **has** been verified
against the live API for real, including real dispatched calls with full webhook delivery:

1. Set `VOICE_PROVIDER=hunar`, `HUNAR_API_KEY=<real key>` in `.env`.
2. `curl localhost:8010/api/agents` and `/api/numbers` should return real data.
3. For a full call end to end: run `ngrok http 8010`, set `PUBLIC_BASE_URL` to the
   `https://*.ngrok-free.dev` URL it prints, restart the backend, then dispatch a call to a
   number that has consented to receiving it, via `/call-console` or `POST /api/calls`.

**Confirmed facts about the real API** (undocumented anywhere - discovered by testing against
it): list routes use a **trailing slash** and are **paginated**
(`{"count","next","previous","results":[...]}`, not a bare array); real `Agent.custom_variables`
is a **list of variable names**, not a dict; `duration_seconds` is a **float**; webhooks are
**partial and event-scoped** (`call_status_updated` carries status but no result; a field absent
from a webhook body means "not part of this update," not "clear it" - `apply_call_update`'s
merge semantics exist specifically because of this).
