import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import settings
from app.core.scheduler import scheduler
from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import CallEventSource
from app.providers.base import CreateCallRequest, ProviderCall, ProviderError, VoiceProvider
from app.services.post_call import post_process_call

logger = logging.getLogger("app.services.calls")


class CallUpdate(BaseModel):
    """Canonical shape both the webhook receiver and the poller normalize into before calling
    apply_call_update. This is what makes the two paths converge on identical logic instead of
    each hand-rolling its own field mapping.

    Every field except provider_call_id/event_type is optional because real Hunar webhooks
    are PARTIAL and event-scoped: call_status_updated carries status/duration/timestamps but
    no result or recording_url; call_recording_done carries only a recording_url;
    call_result_done carries only a result. apply_call_update merges - a field left as None
    here means "not part of this update," not "clear this field."
    """

    provider_call_id: str
    request_id: str | None = None
    event_type: str
    status: str | None = None
    lifecycle_status: str | None = None
    engagement_status: str | None = None
    answered_by: str | None = None
    call_ended_by: str | None = None
    recording_url: str | None = None
    result: dict[str, Any] | None = None
    duration_seconds: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


def provider_call_to_update(provider_call: ProviderCall, *, event_type: str) -> CallUpdate:
    return CallUpdate(event_type=event_type, **provider_call.model_dump())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_draft_call(
    session: Session,
    *,
    callee_name: str,
    mobile_number: str,
    custom_data: dict[str, Any] | None = None,
    campaign_id: UUID | None = None,
) -> Call:
    """Persist a Call row with its own request_id, but don't dispatch it to a provider yet.
    A webhook or poll can already find this row by request_id from this point on, even
    though it isn't dispatched - useful for a module (like Hiring) that wants to add
    candidates now and dispatch them later or in bulk. See dispatch_call."""
    call = Call(
        campaign_id=campaign_id,
        request_id=f"req_{uuid4().hex}",
        callee_name=callee_name,
        mobile_number=mobile_number,
        custom_data=custom_data or {},
        status="NOT_STARTED",
        lifecycle_status="NOT_STARTED",
    )
    session.add(call)
    session.commit()
    session.refresh(call)
    return call


def dispatch_call(session: Session, provider: VoiceProvider, call: Call, *, agent_id: str) -> Call:
    """Dispatch (or re-dispatch/retry) an existing Call row to the provider. Reuses the
    call's own request_id, so a retry after a failed dispatch keeps the same Call row - and
    its CallEvent history - instead of creating a new one."""
    req = CreateCallRequest(
        agent_id=agent_id,
        callee_name=call.callee_name,
        mobile_number=call.mobile_number,
        custom_data=call.custom_data,
        request_id=call.request_id,
    )
    try:
        provider_call = provider.create_call(req)
    except ProviderError:
        call.status = "FAILED"
        call.updated_at = _utcnow()
        session.add(call)
        session.commit()
        raise

    call.provider_call_id = provider_call.provider_call_id
    call.status = provider_call.status
    call.lifecycle_status = provider_call.lifecycle_status
    call.updated_at = _utcnow()
    session.add(call)
    session.commit()
    session.refresh(call)
    return call


def create_call(
    session: Session,
    provider: VoiceProvider,
    *,
    agent_id: str,
    callee_name: str,
    mobile_number: str,
    custom_data: dict[str, Any] | None = None,
    campaign_id: UUID | None = None,
) -> Call:
    """Create and immediately dispatch one call - create_draft_call + dispatch_call in one
    step, for the dev Call Console and any other one-shot caller that doesn't need the
    draft/dispatch split."""
    call = create_draft_call(
        session,
        callee_name=callee_name,
        mobile_number=mobile_number,
        custom_data=custom_data,
        campaign_id=campaign_id,
    )
    return dispatch_call(session, provider, call, agent_id=agent_id)


def apply_call_update(session: Session, update: CallUpdate, *, source: CallEventSource) -> Call | None:
    """The single idempotent convergence point for the webhook receiver, the poller, and the
    mock provider's own intermediate transitions. Applying the exact same update twice is a
    no-op: no duplicate CallEvent, no change to the stored state on the second call.
    """
    call = _find_call(session, update)
    if call is None:
        logger.warning(
            "apply_call_update: no Call found for provider_call_id=%s request_id=%s",
            update.provider_call_id,
            update.request_id,
        )
        return None

    new_payload = update.model_dump(mode="json")
    if call.raw_last_payload == new_payload:
        if source == CallEventSource.poll:
            call.last_polled_at = _utcnow()
            session.add(call)
            session.commit()
            session.refresh(call)
        return call

    # Captured before the merge below, so we can detect the FIRST moment this call has both
    # a terminal lifecycle_status and a real result - that's what triggers the post-call
    # pipeline, exactly once, regardless of which partial webhook happens to supply which
    # field last.
    was_ready = call.lifecycle_status == "COMPLETED" and call.result is not None

    call.provider_call_id = update.provider_call_id
    # Merge, don't overwrite: a None here means "this event didn't carry this field," not
    # "clear it" - see CallUpdate's docstring for why that distinction matters.
    if update.status is not None:
        call.status = update.status
    if update.lifecycle_status is not None:
        call.lifecycle_status = update.lifecycle_status
    if update.engagement_status is not None:
        call.engagement_status = update.engagement_status
    if update.answered_by is not None:
        call.answered_by = update.answered_by
    if update.call_ended_by is not None:
        call.call_ended_by = update.call_ended_by
    if update.recording_url is not None:
        call.recording_url = update.recording_url
    if update.result is not None:
        call.result = update.result
    if update.duration_seconds is not None:
        call.duration_seconds = update.duration_seconds
    if update.started_at is not None:
        call.started_at = update.started_at
    if update.ended_at is not None:
        call.ended_at = update.ended_at
    call.raw_last_payload = new_payload
    call.updated_at = _utcnow()
    if source == CallEventSource.poll:
        call.last_polled_at = _utcnow()
    session.add(call)

    event = CallEvent(
        call_id=call.id,
        event_type=update.event_type,
        source=source,
        payload=new_payload,
        received_at=_utcnow(),
    )
    session.add(event)

    session.commit()
    session.refresh(call)

    is_ready = call.lifecycle_status == "COMPLETED" and call.result is not None
    if settings.ENABLE_POST_CALL_PIPELINE and not was_ready and is_ready:
        schedule_post_processing(call.id)

    return call


def schedule_post_processing(call_id: UUID) -> None:
    """Schedule the transcript + scorecard pipeline for a completed call as a one-off
    background job. Extracted so /rescore (app/modules/hiring/router.py) can force a re-run
    through the exact same path apply_call_update uses automatically."""
    scheduler.add_job(
        post_process_call,
        trigger="date",
        args=[call_id],
        id=f"post-process-{call_id}",
        replace_existing=True,
        misfire_grace_time=None,
    )


def list_calls(session: Session, *, campaign_id: UUID | None = None) -> list[Call]:
    stmt = select(Call).order_by(Call.created_at.desc())
    if campaign_id is not None:
        stmt = stmt.where(Call.campaign_id == campaign_id)
    return list(session.exec(stmt).all())


def get_call_with_events(session: Session, call_id: UUID) -> tuple[Call, list[CallEvent]] | None:
    call = session.get(Call, call_id)
    if call is None:
        return None
    events = session.exec(
        select(CallEvent).where(CallEvent.call_id == call_id).order_by(CallEvent.received_at)
    ).all()
    return call, list(events)


def _find_call(session: Session, update: CallUpdate) -> Call | None:
    call = session.exec(select(Call).where(Call.provider_call_id == update.provider_call_id)).first()
    if call is not None:
        return call
    if update.request_id:
        return session.exec(select(Call).where(Call.request_id == update.request_id)).first()
    return None
