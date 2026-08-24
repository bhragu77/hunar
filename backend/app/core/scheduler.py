import threading
import time

from apscheduler.events import (
    EVENT_JOB_ADDED,
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
)
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

# Single shared scheduler for the whole process: MockProvider uses it to simulate call
# progression, and main.py registers the polling reconciler job on it. Started in main.py's
# lifespan (or explicitly in tests) and shut down on exit.
#
# max_workers=10 (APScheduler's default) is fine for Modules 1/2, which dispatch at most a
# few dozen calls at once, but Module 3's supervisor roll-call dispatches up to 100 calls in
# one batch - with only 10 workers those would serialize into ~10 waves (a "live" demo would
# actually trickle in over ~80s instead of settling in one MOCK_CALL_DURATION_SECONDS window).
# 128 workers is enough for a single roll-call batch to run genuinely in parallel, and costs
# nothing at rest since APScheduler's pool is lazy (threads spin up only as jobs arrive).
scheduler = BackgroundScheduler(executors={"default": ThreadPoolExecutor(128)})

# --- in-flight job tracking -------------------------------------------------------------
#
# MockProvider's simulated call (app/providers/mock.py::_simulate_call) and the post-call
# pipeline (app/services/post_call.py::post_process_call) both run as one-off scheduler jobs.
# A test can observe a call reach a *terminal* status (via the provider's in-memory state or
# the DB) well before the job that produced it actually returns - e.g. _simulate_call flips
# its in-memory status to COMPLETED and only *then* sends its self-signed webhook POST, which
# can take up to its full httpx timeout if nothing is listening. Without draining, that stray
# job keeps running into the next test, which can race its table-cleanup fixture.
#
# Track "added but not yet finished" jobs. Increment on EVENT_JOB_ADDED rather than
# EVENT_JOB_SUBMITTED: add_job() dispatches EVENT_JOB_ADDED *synchronously* before returning
# to the caller, so a caller that does `scheduler.add_job(...); wait_until_idle()` can never
# race the scheduler's own background thread noticing and submitting the job - the increment
# has already happened by the time add_job() returns. EVENT_JOB_SUBMITTED, by contrast, only
# fires later from that background thread, leaving a real window where wait_until_idle() could
# observe _inflight == 0 and return before the job it was meant to wait for ever started.
# Decrement on whichever terminal executor event actually applies.
#
# Expose wait_until_idle() as a real synchronization primitive - a blocking Condition wait,
# not a fixed sleep or a retry - so callers (tests, or a graceful shutdown) can deterministically
# wait for every in-flight job to actually finish.
_inflight = 0
_idle = threading.Condition()


def _on_job_added(event: object) -> None:
    global _inflight
    with _idle:
        _inflight += 1


def _on_job_finished(event: object) -> None:
    global _inflight
    with _idle:
        _inflight = max(0, _inflight - 1)
        if _inflight == 0:
            _idle.notify_all()


scheduler.add_listener(_on_job_added, EVENT_JOB_ADDED)
scheduler.add_listener(_on_job_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)


def wait_until_idle(timeout: float = 10.0) -> None:
    """Block until every job submitted to the scheduler's executor has actually finished
    running (not merely reached some terminal state observable elsewhere). Raises
    TimeoutError if jobs are still in flight after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    with _idle:
        while _inflight > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"scheduler still has {_inflight} job(s) in flight after {timeout}s")
            _idle.wait(remaining)
