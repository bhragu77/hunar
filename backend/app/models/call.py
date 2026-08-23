from datetime import datetime

from sqlmodel import Field, SQLModel


class Call(SQLModel, table=True):
    """Minimal local record of a voice call, so init_db has a table to create.

    Phase 2 will expand this with full call/result persistence tied to the
    Hunar webhook flow.
    """

    id: int | None = Field(default=None, primary_key=True)
    provider_call_id: str = Field(index=True)
    agent_id: str
    phone_number: str
    status: str = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)
