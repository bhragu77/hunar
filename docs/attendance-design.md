# Module 3: Attendance — Design

**Problem statement:** track daily attendance for 1,000 people across 100 locations. Workers
carry no smartphones and use no apps. Every phone — smart or basic — can place and receive a
call. LLMs and voice infrastructure exist and are cheap. Design (and demonstrate) a system
that uses only phone calls to produce a reliable daily attendance record.

This document is the design; the running product (`/attendance` in the app) is a proof of
concept built on the exact same Voice Core (`Campaign` + `Call` + provider + webhook/poll)
used by Modules 1 and 2. Section 9 maps every piece of the design onto that platform and is
explicit about what's simplified for the demo.

## 1. Problem & constraints

- **Scale**: ~1,000 workers, ~100 locations (~10 workers/location on average), every working
  day. Whatever the mechanism, it has to run in well under an hour each morning.
- **No apps**: no smartphone assumed, no app install, no push notifications, no QR codes, no
  biometric hardware. The lowest common denominator is a basic phone that can make and receive
  voice calls (and possibly SMS, but we don't rely on that either — SMS delivery and literacy
  are both less reliable than a phone call in this population).
- **Connectivity**: sites may be low-connectivity (poor data, no reliable internet), but the
  cellular voice network is assumed to reach every site — that's the one channel we can
  depend on everywhere.
- **Workforce**: multilingual, and plausibly low-literacy in the sense that a UI, a form, or an
  SMS with instructions cannot be assumed to be understood or actioned reliably. A live,
  natural-language conversation — in the worker's own language — is the most universally
  accessible interface available.
- **Integrity matters, but doesn't need to be cryptographic.** This is operational attendance
  tracking (payroll input, workforce planning), not a security system. The design optimizes
  for "correct on a normal day, self-healing on an abnormal one," not for defeating a
  determined bad actor.

## 2. Core insight

**Voice is the universal interface when apps don't exist.** Every phone can be called, and
every phone can call out. LLM voice agents turn an ordinary phone call into structured data:
the agent asks questions in the local language, the person answers naturally, and the system
gets back a clean `{worker_id: present | absent}` map — with no app, no training, and no
literacy requirement on the human end.

That reframes "track 1,000 people" as "collect 1,000 yes/no facts by voice, as cheaply and as
few times as possible." The rest of this document is about *how few calls that actually takes*
if you pick the right unit of interaction.

## 3. Primary design — supervisor roll-call (100 calls, not 1,000)

**The single biggest design decision: call the supervisor, not the worker.** A site
supervisor already knows, informally, who showed up — the same way a physical roll call or a
foreman's headcount has worked for decades. An LLM voice agent can extract that same
information over a phone call instead of a human walking a clipboard around.

**Flow:**
1. Each morning, the system places one outbound call per location (100 calls total) to that
   site's registered supervisor number.
2. The voice agent introduces itself, and asks the supervisor to go through today's expected
   worker list — who's present, who's absent (and optionally why).
3. The agent speaks and listens in the supervisor's local language, confirms the final
   counts, and ends the call.
4. The call's structured result — present/absent per worker — is written back as that
   location's attendance roster.

**Why this scales:** the unit of work is "one location," not "one worker." Headcount per site
is a supervisor's own working knowledge already, collected in a single natural conversation
instead of via 10 separate targeted interviews. Cost and call volume become a function of
*locations*, not *workers* — a **10x reduction** in call volume versus calling every worker,
and it doesn't degrade as sites get bigger. A 30-person site still costs one call, not 30.

**Cost/time math (order of magnitude):** 100 calls × ~2 minutes each, run in parallel across a
call-center-style outbound pool (the way any voice platform handles concurrent dispatch),
completes in a single wall-clock batch on the order of 10–15 minutes rather than 100 × 2 min
serialized. At typical LLM-voice-call pricing, 100 short calls a day is a rounding error next
to the cost of any manual attendance process at this scale (a human calling or visiting 100
sites, or reconciling 100 paper registers).

**Resilience to missing phones:** a worker never needs their own phone for this path to work
at all — the supervisor's phone is the only dependency. This is what makes it a *complete*
attendance mechanism on its own, unlike a worker-facing mechanism that inherently leaves out
whoever doesn't have a phone that day.

## 4. Low-tech inbound — missed-call-to-mark-present

The roll-call is authoritative, but it's still one secondhand report per site. Where a worker
*does* have a phone, we add a **direct, zero-cost self-check-in**:

- **Missed call ("give a missed call")**: the worker calls a published number from their own
  registered mobile and hangs up before it's answered (or lets it ring out) — the classic
  "give a missed call" pattern already familiar across low-connectivity markets for
  everything from voting to service requests. The system reads the caller ID; if it matches a
  registered worker number and the call lands inside the morning attendance window, that
  worker is marked present. **Zero cost to the worker** (a missed call is free on every
  carrier), works from **any phone**, and needs no app, no balance, no data.
- **Alternative: inbound IVR self-check-in.** A worker calls in and lets the call connect to a
  short voice/IVR flow ("press 1 for present" or a one-line voice confirmation) instead of
  hanging up. This carries a small connection cost to the worker (or is toll-free if the
  system supports it) but gives a slightly stronger positive signal than a bare missed call
  (a connected, confirmed action vs. an unanswered ring) and doubles as a channel a worker
  could use to also report *why* they're absent. We recommend missed-call as the default for
  cost reasons, with IVR check-in as a fallback/complement for sites that want additional
  confirmation.

Either way, this channel is optional and additive — the system's completeness never depends
on it, because the supervisor roll-call already covers every worker regardless of whether
they self-report.

## 5. Hybrid + exception handling

The two channels above are reconciled into one attendance record per worker, and the
**expensive per-worker voice call is reserved for the cases that actually need it**:

1. **Missed-call log** (workers who self-reported) is merged against the **supervisor
   roster** (the source of truth for the whole site). Where they agree, done — no further
   action.
2. **Discrepancies and gaps** — a worker the supervisor marked absent but who gave a missed
   call (or vice versa), or a worker the supervisor couldn't account for at all — are flagged
   as exceptions.
3. **Only exceptions get an LLM voice callback**: a short, targeted call (to the worker
   directly, or back to the supervisor for clarification) to resolve the specific discrepancy.
   This is the *only* place per-worker call volume exists in the whole system, and in a normal
   day it's a small fraction of the 1,000 — most days it's near zero, since the supervisor
   roll-call already resolves the overwhelming majority.
4. **Escalation**: a worker still unresolved after an exception callback (no answer, no
   missed call, supervisor still can't confirm) is marked `unreachable`/`pending` and
   surfaces on the daily report for human follow-up — the system never silently guesses.

This hybrid design is why 100 calls (not 1,000) is achievable *without* sacrificing
worker-level granularity: the roll-call gives per-worker resolution in the aggregate, the
missed-call channel gives free corroboration where available, and voice calls to individual
workers are spent only where they add real information.

## 6. Edge cases & integrity

- **Buddy-punching / shared phones**: a missed call only proves *a call came from a
  registered number*, not who dialed it. This is a known, accepted limitation of any
  phone-based system, mitigated by (a) the supervisor roll-call being the primary,
  authoritative source — a missed call can only *corroborate*, and a supervisor who marks
  someone absent is not overridden by a missed call alone without reconciliation, and (b) an
  unusual pattern (one number giving missed calls for multiple workers, or a worker's missed
  call directly contradicting their supervisor's report) is exactly the kind of discrepancy
  Section 5 routes to a callback instead of trusting it blindly.
- **Wrong / changed numbers**: registration drift (a worker gets a new SIM, a supervisor
  changes phones) shows up as "expected but unreachable" and is a data-hygiene workflow (an
  HR/admin correction), not something the daily attendance run needs to solve in real time —
  it just needs to *flag* it reliably, which the exceptions list does.
- **No-answer & retries**: calls that ring out are retried with backoff within a bounded
  calling-hours window (e.g. don't retry a supervisor call outside 8–10am local time; don't
  keep calling a number that's declared invalid). A supervisor who is truly unreachable
  degrades that location's whole roster to `unreachable` rather than silently marking
  everyone absent — see Section 7 in `app/services/attendance.py`'s roster reconciliation.
- **Shift / timezone windows**: the "morning window" for missed-calls and the roll-call
  schedule are per-site configurable, since not every site runs the same shift start time;
  the design generalizes to multiple daily windows (e.g. a second roll-call for an evening
  shift) without any structural change — it's just another run.
- **Name-matching (the honest simplification)**: in a live conversation, a supervisor speaks
  worker *names*, not database ids. Turning "Aarav Sharma was there, and Meera didn't come
  in" into a specific worker row requires fuzzy name resolution and/or a spoken confirmation
  step ("that's Aarav Sharma, employee 042-W03 — correct?"). This is a real, solvable NLP/UX
  problem, but it's a separate concern from the attendance *pipeline* itself. The POC (Section
  9) uses employee ids directly so the demo shows a clean, deterministic reconciliation
  instead of re-solving entity resolution — see the comment in
  `app/services/attendance.py::_parse_roster`.

## 7. Daily workflow timeline

A representative morning schedule (times illustrative, configurable per deployment):

| Time          | Step                                                                 |
|---------------|-----------------------------------------------------------------------|
| 08:00 – 09:00 | Missed-call window open — workers with a phone self-report present   |
| 09:00 – 09:30 | Supervisor roll-calls dispatched (100 calls, run in parallel)        |
| 09:30 – 10:00 | Reconcile missed-call log vs. roll-call roster; exception callbacks  |
| 10:00         | Daily attendance report finalized (per-location + org-wide)          |

Everything before 10:00 runs unattended. Only the exception list needs a human glance, and
even that is optional — unresolved records are visible on the dashboard for whenever someone
looks.

## 8. Scale & cost, multilingual support, data model

**Scale.** The design's cost profile is dominated by the ~100 supervisor calls; it doesn't
grow linearly with worker count the way a per-worker system would. Doubling the workforce at
the same site count doesn't add a single call. Doubling the *site* count doubles supervisor
calls (still ~200, an order of magnitude below 2,000 workers) but exception-callback volume —
the only per-worker cost — stays small as long as most locations resolve cleanly.

**Multilingual support.** The voice agent's language is a per-location (or per-supervisor)
configuration, not a system-wide constant — a Hindi-speaking supervisor and a
Tamil-speaking one are just two different agent language configs dispatched by the same
pipeline. This is a natural fit for LLM voice agents, which don't need separately trained
models per language the way legacy IVR trees historically did.

**Data model.**
- `Location` — one work site: name, region, supervisor name/mobile.
- `Worker` — belongs to a `Location`: name, employee id, (optional) mobile.
- An **AttendanceRun** *is* a `Campaign` (`module="attendance"`), one per day/shift; its
  `meta` carries the run date and mode.
- Each **supervisor roll-call** *is* a `Call` under that campaign, one per location, carrying
  that location's expected worker roster in `custom_data`.
- `AttendanceRecord` — one row per (run, worker): status (`pending` → `present` / `absent` /
  `unreachable`), source (`supervisor_call` / `missed_call` / `manual` / `worker_call`), the
  call that resolved it, and a timestamp. Aggregates (per-location and org-wide counts/rates,
  the exceptions list) are always **derived on read** from these rows, never stored
  separately — so they can never drift out of sync with the underlying calls.

## 9. Mapping onto the platform already built

Nothing about attendance needed a new pipeline. It reuses the exact same primitives Modules 1
and 2 already established:

- **An attendance run is a `Campaign`.** Same table, same `agent_id` + `result_schema`
  snapshot, just `module="attendance"` and a `meta` shape of its own (`run_date`, `mode`) —
  identical to how an outreach campaign or a hiring interview is "just" a `Campaign` with a
  different module tag and a different `meta` shape.
- **A supervisor roll-call is a `Call`.** Dispatch goes through the exact same
  `create_draft_call` / `dispatch_call` used by every other module — no new dispatch code
  exists. Its progress (ringing → in-progress → completed) is tracked by the exact same
  webhook + polling convergence (`apply_call_update`) as every other call in the system.
  Nothing about webhook delivery, retry, or reconciliation was touched.
- **The roster reconciliation is one branch in the existing post-call pipeline.**
  `app/services/post_call.py::post_process_call` already runs a transcript step and then
  branches per module (scorecard for hiring, a summary for outreach); attendance adds a third
  branch that reconciles that location's `AttendanceRecord`s the moment its supervisor call
  completes — no parallel pipeline, no new webhook receiver, no new poller.
- **What the POC demonstrates:** the full shape of the design at real scale — seed ~1,000
  workers across 100 locations, materialize and dispatch 100 real (mock) supervisor calls
  concurrently through the existing voice core, watch a live heatmap fill in as calls
  complete, simulate the missed-call window, drill into any location's per-worker roster, and
  see exceptions surface — all with zero external API keys.
- **What's simplified for the demo, deliberately and documented in code:**
  - The mock voice agent doesn't actually understand speech, so it can't produce a genuine
    present/absent roster from a "conversation." `app/services/attendance.py` handles this
    honestly: it always checks first for a real structured roster in the call's result (the
    shape a real, connected voice agent would return), and only falls back to a **seeded,
    deterministic synthetic split** (targeting `ATTENDANCE_PRESENT_RATE`) when the result is
    the mock provider's generic filler. The seam is explicit and commented at the fallback
    site, not hidden.
  - The POC matches roster entries by **employee id**, not by fuzzy name matching against
    what a supervisor actually says — see the name-matching discussion in Section 6. A
    production build would add a name-resolution/confirmation layer in front of the same
    reconciliation logic; the reconciliation logic itself doesn't change.
  - "Missed call" is simulated (`simulate-missed-calls`) rather than wired to a live inbound
    telephony number, since that requires a real number + carrier integration outside this
    repo's scope. The single-worker `missed-call` endpoint is the real integration seam: a
    live inbound webhook would call it exactly the same way the demo's simulator does.
