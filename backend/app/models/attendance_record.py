from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.enums import AttendanceSource, AttendanceStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceRecord(SQLModel, table=True):
    """One worker's attendance outcome for one AttendanceRun (a Campaign with
    module="attendance" - run_id IS that campaign's id). Created as `pending` for every
    worker the moment a run is materialized, then upgraded by whichever source resolves it
    first: the supervisor's roll-call, a worker's own missed call, an exception callback, or
    a manual override. See app/services/attendance.py for the reconciliation rules (present
    is never downgraded once set).
    """

    __tablename__ = "attendance_record"
    __table_args__ = (UniqueConstraint("run_id", "worker_id", name="uq_attendance_record_run_worker"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="campaign.id", index=True)
    location_id: UUID = Field(foreign_key="location.id", index=True)
    worker_id: UUID = Field(foreign_key="worker.id", index=True)

    status: AttendanceStatus = AttendanceStatus.pending
    source: AttendanceSource | None = None
    call_id: UUID | None = Field(default=None, foreign_key="call.id")
    reason: str | None = None
    marked_at: datetime | None = None

    created_at: datetime = Field(default_factory=_utcnow)
