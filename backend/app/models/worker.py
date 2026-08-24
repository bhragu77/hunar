from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Worker(SQLModel, table=True):
    """One worker attached to a Location. `mobile` is the number a missed call must come
    from to auto-mark this worker present (app/services/attendance.py::mark_present_by_mobile)
    - nullable because not every worker in the demo population has a registered phone.
    """

    __tablename__ = "worker"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    location_id: UUID = Field(foreign_key="location.id", index=True)

    full_name: str
    employee_id: str = Field(index=True, unique=True)
    mobile: str | None = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=_utcnow)
