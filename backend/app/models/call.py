from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import PostCallStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Call(SQLModel, table=True):
    """One dispatched voice call. `raw_last_payload` holds the last applied CallUpdate
    (see app/services/calls.py) verbatim - comparing against it is what makes
    apply_call_update idempotent.
    """

    __tablename__ = "call"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaign.id", index=True)

    # Our own correlation id, generated before we ever call the provider, so a webhook or poll
    # can always find this row even if provider_call_id hasn't round-tripped back yet.
    request_id: str = Field(index=True, unique=True)
    provider_call_id: str | None = Field(default=None, index=True)

    callee_name: str
    mobile_number: str
    custom_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    status: str = "NOT_STARTED"
    lifecycle_status: str | None = None
    engagement_status: str | None = None
    answered_by: str | None = None
    call_ended_by: str | None = None

    recording_url: str | None = None
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    duration_seconds: int | None = None

    # Post-call pipeline (app/services/post_call.py) - populated once the call completes.
    transcript: str | None = None
    transcript_status: PostCallStatus = PostCallStatus.pending
    transcript_error: str | None = None
    scorecard: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    scorecard_status: PostCallStatus = PostCallStatus.pending
    scorecard_error: str | None = None
    scorecard_generated_at: datetime | None = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_polled_at: datetime | None = None

    raw_last_payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
