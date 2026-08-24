from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import Module


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(SQLModel, table=True):
    """A batch of calls sharing one agent + result schema - an interview round, an outreach
    push, an attendance run are all this same shape. Snapshots the agent's result_schema at
    creation so a campaign's expected result shape doesn't drift if the agent changes later.
    """

    __tablename__ = "campaign"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    description: str | None = None  # the JD / evaluation criteria for the role (hiring module)
    module: Module
    agent_id: str
    result_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "active"
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
