from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AttendanceSource, AttendanceStatus


class DesignDocResponse(BaseModel):
    content: str


class SeedDemoResponse(BaseModel):
    locations: int
    workers: int
    created_locations: int
    created_workers: int


class LocationOut(BaseModel):
    id: UUID
    name: str
    region: str | None
    supervisor_name: str
    supervisor_mobile: str
    worker_count: int
    created_at: datetime


class RunCreateRequest(BaseModel):
    run_date: date | None = None


class MissedCallRequest(BaseModel):
    mobile: str


class RecordMarkRequest(BaseModel):
    status: AttendanceStatus
    reason: str | None = None


class DispatchRunResponse(BaseModel):
    dispatched: int


class SimulateMissedCallsResponse(BaseModel):
    marked_present: int


class MissedCallResponse(BaseModel):
    marked: bool
    worker_id: UUID | None = None
    record_id: UUID | None = None
    status: AttendanceStatus | None = None


class AttendanceCounts(BaseModel):
    pending: int
    present: int
    absent: int
    unreachable: int
    total: int
    rate: float


class LocationAttendanceSummary(BaseModel):
    location_id: UUID
    location_name: str
    region: str | None
    supervisor_call_id: UUID | None
    supervisor_call_status: str | None
    counts: AttendanceCounts


class ExceptionRecord(BaseModel):
    record_id: UUID
    worker_id: UUID
    worker_name: str
    employee_id: str
    location_id: UUID
    location_name: str
    status: AttendanceStatus
    reason: str | None


class RunSummary(BaseModel):
    id: UUID
    run_date: str
    status: str
    created_at: datetime
    counts: AttendanceCounts


class RunDetail(BaseModel):
    id: UUID
    run_date: str
    status: str
    created_at: datetime
    counts: AttendanceCounts
    locations: list[LocationAttendanceSummary]
    exceptions: list[ExceptionRecord]


class WorkerAttendanceOut(BaseModel):
    record_id: UUID
    worker_id: UUID
    full_name: str
    employee_id: str
    mobile: str | None
    status: AttendanceStatus
    source: AttendanceSource | None
    reason: str | None
    marked_at: datetime | None


class LocationDetail(BaseModel):
    location_id: UUID
    location_name: str
    region: str | None
    supervisor_name: str
    supervisor_mobile: str
    supervisor_call_id: UUID | None
    workers: list[WorkerAttendanceOut]
    counts: AttendanceCounts
