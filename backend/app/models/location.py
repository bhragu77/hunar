from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Location(SQLModel, table=True):
    """One work site (a warehouse, a construction site, a store) that runs its own daily
    attendance roll-call, taken by phone from its supervisor - see app/services/attendance.py.
    """

    __tablename__ = "location"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    region: str | None = None
    supervisor_name: str
    supervisor_mobile: str
    created_at: datetime = Field(default_factory=_utcnow)
