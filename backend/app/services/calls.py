import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import Session, select

from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import CallEventSource
from app.providers.base import CreateCallRequest, ProviderCall, ProviderError, VoiceProvider

logger = logging.getLogger("app.services.calls")


class CallUpdate(BaseModel):
    """Canonical shape both the webhook receiver and the poller normalize into before calling
    apply_call_update. This is what makes the two paths converge on identical logic instead of
    each hand-rolling its own field mapping."""

    provider_call_id: str
    request_id: str | None = None
    event_type: str
    status: str
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
    """Dispatch one call. The Call row (and its request_id) is persisted BEFORE we ever call
    the provider, so a webhook or poll can always find it - even one that races ahead of this
    function returning."""
    request_id = f"req_{uuid4().hex}"
    call = Call(
        campaign_id=campaign_id,
        request_id=request_id,
        callee_name=callee_name,
        mobile_number=mobile_number,
        custom_data=custom_data or {},
        status="NOT_STARTED",
        lifecycle_status="NOT_STARTED",
    )
    session.add(call)
    session.commit()
    session.refresh(call)

    req = CreateCallRequest(
        agent_id=agent_id,
        callee_name=callee_name,
        mobile_number=mobile_number,
        custom_data=custom_data or {},
        request_id=request_id,
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

    call.provider_call_id = update.provider_call_id
    call.status = update.status
    call.lifecycle_status = update.lifecycle_status
    call.engagement_status = update.engagement_status
    call.answered_by = update.answered_by
    call.call_ended_by = update.call_ended_by
    call.recording_url = update.recording_url
    call.result = update.result
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
    return call


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
