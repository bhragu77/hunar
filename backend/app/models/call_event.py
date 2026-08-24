from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import CallEventSource


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CallEvent(SQLModel, table=True):
    """Append-only history of every update applied to a Call: what changed, when, and whether
    it came from a webhook, the poller, or the mock provider's own intermediate transitions.
    Exists purely for debuggability - nothing reads it to make decisions.
    """

    __tablename__ = "call_event"

    id: int | None = Field(default=None, primary_key=True)
    call_id: UUID = Field(foreign_key="call.id", index=True)
    event_type: str
    source: CallEventSource
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    received_at: datetime = Field(default_factory=_utcnow)
