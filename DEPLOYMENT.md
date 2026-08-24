# Deployment

Backend + Postgres deploy to **Render** (Blueprint, from `render.yaml`). The frontend deploys
to **Vercel**. Both are free-tier. The deployed backend runs **every provider on `mock`** by
default (`VOICE_PROVIDER` / `LLM_PROVIDER` / `TRANSCRIPTION_PROVIDER` / `PEOPLE_SEARCH_PROVIDER`)
so the live link needs zero external API keys and keeps working forever, even after the Hunar
key used during development is revoked.

There's a chicken-and-egg pair of steps neither platform can do for you (each service needs to
know the other's URL, which only exists after the first deploy) - steps 3 and 5 below.

## 1. Push to GitHub

```bash
git push origin main
```

Both Render and Vercel deploy straight from a GitHub repo.

## 2. Backend + database on Render

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**.
2. Connect the GitHub repo. Render reads `render.yaml` at the repo root and proposes:
   - a **free Postgres** database (`hunar-db`)
   - a **free web service** (`hunar-backend`), built from `backend/Dockerfile` with the repo
     root as build context (needed so the image can bake in `docs/attendance-design.md`)
3. Click **Apply**. First deploy takes a few minutes (Docker build + `pip install`).
4. Render's free Postgres databases expire after 30 days of the free plan's lifetime - if it's
   already gone by the time you deploy, create a new free Postgres instance manually and point
   `DATABASE_URL` at it (Render Blueprint's `fromDatabase` wiring still works if you keep the
   database resource in the Blueprint; only recreate it if Render tells you it expired).

## 3. Fix the self-referencing URL (one manual edit, first deploy only)

`INTERNAL_BASE_URL` is how `MockProvider` posts its self-signed completion webhook back to this
same backend (see the README's Voice Core section) - it has to be this service's own public
URL, which doesn't exist until after step 2's first deploy.

1. Open the `hunar-backend` service → note its URL at the top (e.g.
   `https://hunar-backend-a1b2.onrender.com`).
2. **Environment** tab → edit `INTERNAL_BASE_URL` → paste that exact URL (no trailing slash) →
   **Save Changes**. This triggers a redeploy.

Skipping this step doesn't break anything - the polling reconciler still converges every call to
the correct terminal state within `POLL_STALE_AFTER_SECONDS` (default 20s) - it just makes calls
finish a bit slower than the ~8 second mock duration, which matters for a snappy demo.

3. Confirm: `curl https://<your-backend>.onrender.com/health` → `{"status":"ok","provider":"mock"}`.

## 4. Frontend on Vercel

1. [vercel.com/new](https://vercel.com/new) → import the same GitHub repo.
2. **Root Directory**: `frontend` (Vercel auto-detects Next.js once you set this).
3. **Environment Variables** → add `NEXT_PUBLIC_API_URL` = your Render backend URL from step 3
   (e.g. `https://hunar-backend-a1b2.onrender.com`, no trailing slash). This is a public,
   non-secret URL - the frontend never holds any API key (see README's security note).
4. **Deploy**.

## 5. Point the backend's CORS at the deployed frontend (one manual edit)

1. Note the Vercel URL Vercel gives you (e.g. `https://hunar.vercel.app`).
2. Back in Render, `hunar-backend` → **Environment** → edit `BACKEND_CORS_ORIGINS` → set it to
   that URL (comma-separate if you also want to allow a Vercel preview URL) → **Save Changes**.

## 6. Verify the live link

Open the Vercel URL. The Attendance dashboard should already show ~100 locations / ~1,000
workers (seeded automatically on the backend's first boot via `DEMO_SEED_ON_START=true` - see
`render.yaml`). Run through the [60-second demo script](README.md#60-second-demo-script) for
all three modules.

**Free-tier cold starts**: Render's free web services spin down after ~15 minutes idle and take
~30-50s to wake on the next request. The very first click on the live link after it's been idle
will be slow to load - that's Render, not the app. Nothing to fix; just don't be alarmed if the
first request times out in a browser and a reload then works.

## Redeploying

Both platforms auto-deploy on push to `main` by default (Render Blueprint sync + Vercel's Git
integration) - just `git push`. To change an env var (e.g. flip a provider to real), edit it in
the respective dashboard's Environment tab; Render redeploys automatically on save, Vercel
requires a redeploy from the dashboard (or a new push) since `NEXT_PUBLIC_*` vars are baked in
at build time.

## Upgrading a provider to real (optional)

Every provider defaults to mock. To swap one in on the deployed backend, edit env vars in
Render's Environment tab - no code changes:

| Provider | Env vars to set | Effect |
|---|---|---|
| Real Hunar voice | `VOICE_PROVIDER=hunar`, `HUNAR_API_KEY=<key>`, `PUBLIC_BASE_URL=<this backend's URL>` | Real calls dispatch through Hunar; webhooks arrive at `/api/webhooks/hunar` |
| Real LLM scoring | `LLM_PROVIDER=anthropic` or `openai`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Real scorecards/outreach summaries; falls back to mock on any failure |
| Real transcription | `TRANSCRIPTION_PROVIDER=openai`, `OPENAI_API_KEY` | Real transcript from the call recording |
| Real people search | `PEOPLE_SEARCH_PROVIDER=apollo` or `pdl`, `APOLLO_API_KEY` / `PDL_API_KEY` | Real candidate sourcing instead of synthesized mock profiles |

Only do this with a key you're comfortable being live on a public URL - rotate it if you ever
suspect it leaked (see the README's Security section).
