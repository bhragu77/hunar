import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session

from app.core.db import engine
from app.integrations.transcription import transcribe
from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.campaign import Campaign
from app.models.enums import CallEventSource, PostCallStatus
from app.services.scorecard import build_scorecard

logger = logging.getLogger("app.services.post_call")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def post_process_call(call_id: UUID) -> None:
    """Run the transcript + scorecard pipeline for one completed call.

    Scheduled as a one-off APScheduler job by apply_call_update the moment a call first has
    both a terminal lifecycle_status and a non-null result (see app/services/calls.py), and
    re-triggered explicitly by the /rescore endpoint. Idempotent: each step only does work
    if its status is still "pending" - safe to call more than once, never duplicates work or
    flip-flops state. Runs on its own DB session since this executes on a scheduler thread.
    """
    with Session(engine) as session:
        call = session.get(Call, call_id)
        if call is None:
            logger.warning("post_process_call: call %s not found", call_id)
            return
        campaign = session.get(Campaign, call.campaign_id) if call.campaign_id else None

        _run_transcript_step(session, call)
        _run_scorecard_step(session, call, campaign)


def _run_transcript_step(session: Session, call: Call) -> None:
    if call.transcript_status != PostCallStatus.pending:
        return

    try:
        text = transcribe(call)
    except Exception as exc:  # a flaky transcription backend must never break the pipeline
        logger.exception("Transcription failed for call %s", call.id)
        call.transcript_status = PostCallStatus.failed
        call.transcript_error = str(exc)
        _save(session, call)
        _log_event(session, call, "transcript_failed", payload={"error": str(exc)})
        return

    if not text:
        call.transcript_status = PostCallStatus.skipped
        _save(session, call)
        _log_event(session, call, "transcript_skipped")
        return

    call.transcript = text
    call.transcript_status = PostCallStatus.done
    _save(session, call)
    _log_event(session, call, "transcript_generated")


def _run_scorecard_step(session: Session, call: Call, campaign: Campaign | None) -> None:
    if call.scorecard_status != PostCallStatus.pending:
        return

    try:
        scorecard = build_scorecard(call, campaign)
    except Exception as exc:  # a flaky LLM backend must never break the pipeline
        logger.exception("Scorecard generation failed for call %s", call.id)
        call.scorecard_status = PostCallStatus.failed
        call.scorecard_error = str(exc)
        _save(session, call)
        _log_event(session, call, "scorecard_failed", payload={"error": str(exc)})
        return

    call.scorecard = scorecard
    call.scorecard_status = PostCallStatus.done
    call.scorecard_generated_at = _utcnow()
    _save(session, call)
    _log_event(session, call, "scorecard_generated", payload={"recommendation": scorecard.get("recommendation")})


def _save(session: Session, call: Call) -> None:
    call.updated_at = _utcnow()
    session.add(call)
    session.commit()
    session.refresh(call)


def _log_event(session: Session, call: Call, event_type: str, *, payload: dict | None = None) -> None:
    session.add(
        CallEvent(
            call_id=call.id,
            event_type=event_type,
            source=CallEventSource.pipeline,
            payload=payload or {},
            received_at=_utcnow(),
        )
    )
    session.commit()
