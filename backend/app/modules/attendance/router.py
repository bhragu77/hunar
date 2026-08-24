from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.models.campaign import Campaign
from app.models.worker import Worker
from app.providers.base import VoiceProvider
from app.providers.factory import get_voice_provider
from app.schemas.attendance import (
    AttendanceCounts,
    DesignDocResponse,
    DispatchRunResponse,
    LocationAttendanceSummary,
    LocationDetail,
    LocationOut,
    MissedCallRequest,
    MissedCallResponse,
    RecordMarkRequest,
    RunCreateRequest,
    RunDetail,
    RunSummary,
    SeedDemoResponse,
    SimulateMissedCallsResponse,
    WorkerAttendanceOut,
)
from app.services import attendance as attendance_service

# Module 3 - Attendance. An AttendanceRun IS a Campaign with module="attendance"; a
# supervisor's roll-call IS a Call under it. Dispatch goes through the same calls_service used
# everywhere else; nothing here reimplements webhook/poll handling. See
# docs/attendance-design.md for the design this is a POC of.
router = APIRouter(prefix="/attendance", tags=["attendance"])

SessionDep = Annotated[Session, Depends(get_session)]
ProviderDep = Annotated[VoiceProvider, Depends(get_voice_provider)]

# Two layouts to support: a native checkout (backend/app/modules/attendance/router.py ->
# repo root is 4 parents up) and the backend Docker image, which bakes docs/ in at
# /app/docs (see backend/Dockerfile) - local docker-compose additionally bind-mounts it there
# for live-editing (see docker-compose.yml).
_DESIGN_DOC_CANDIDATES = [
    Path(__file__).resolve().parents[4] / "docs" / "attendance-design.md",
    Path("/app/docs/attendance-design.md"),
]


@lru_cache
def _load_design_doc() -> str:
    for candidate in _DESIGN_DOC_CANDIDATES:
        try:
            return candidate.read_text()
        except OSError:
            continue
    return "# Attendance design\n\ndocs/attendance-design.md was not found on this server."


@router.get("/design-doc", response_model=DesignDocResponse)
def get_design_doc() -> DesignDocResponse:
    return DesignDocResponse(content=_load_design_doc())


def _run_counts(session: Session, run_id: UUID) -> AttendanceCounts:
    records = attendance_service.run_records(session, run_id)
    return AttendanceCounts(**attendance_service.counts_for_records(records))


def _run_summary(session: Session, campaign: Campaign) -> RunSummary:
    return RunSummary(
        id=campaign.id,
        run_date=(campaign.meta or {}).get("run_date", ""),
        status=campaign.status,
        created_at=campaign.created_at,
        counts=_run_counts(session, campaign.id),
    )


def _run_detail(session: Session, campaign: Campaign) -> RunDetail:
    grid = attendance_service.location_grid(session, campaign.id)
    locations = [LocationAttendanceSummary(**{**row, "counts": AttendanceCounts(**row["counts"])}) for row in grid]
    exceptions = attendance_service.exceptions(session, campaign.id)
    return RunDetail(
        id=campaign.id,
        run_date=(campaign.meta or {}).get("run_date", ""),
        status=campaign.status,
        created_at=campaign.created_at,
        counts=_run_counts(session, campaign.id),
        locations=locations,
        exceptions=exceptions,
    )


@router.post("/seed-demo", response_model=SeedDemoResponse)
def seed_demo(session: SessionDep) -> SeedDemoResponse:
    return SeedDemoResponse(**attendance_service.seed_demo(session))


@router.get("/locations", response_model=list[LocationOut])
def list_locations(session: SessionDep) -> list[LocationOut]:
    return [
        LocationOut(
            id=loc.id,
            name=loc.name,
            region=loc.region,
            supervisor_name=loc.supervisor_name,
            supervisor_mobile=loc.supervisor_mobile,
            worker_count=count,
            created_at=loc.created_at,
        )
        for loc, count in attendance_service.list_locations_with_counts(session)
    ]


@router.post("/runs", response_model=RunDetail)
def create_run(req: RunCreateRequest, session: SessionDep, provider: ProviderDep) -> RunDetail:
    campaign = attendance_service.create_run(session, provider, run_date=req.run_date)
    return _run_detail(session, campaign)


@router.get("/runs", response_model=list[RunSummary])
def list_runs(session: SessionDep) -> list[RunSummary]:
    return [_run_summary(session, c) for c in attendance_service.list_runs(session)]


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: UUID, session: SessionDep) -> RunDetail:
    campaign = attendance_service.get_run(session, run_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Attendance run not found")
    return _run_detail(session, campaign)


@router.post("/runs/{run_id}/dispatch", response_model=DispatchRunResponse)
def dispatch_run(run_id: UUID, session: SessionDep, provider: ProviderDep) -> DispatchRunResponse:
    campaign = attendance_service.get_run(session, run_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Attendance run not found")
    dispatched = attendance_service.dispatch_run(session, provider, campaign)
    return DispatchRunResponse(dispatched=dispatched)


@router.post("/runs/{run_id}/simulate-missed-calls", response_model=SimulateMissedCallsResponse)
def simulate_missed_calls(run_id: UUID, session: SessionDep) -> SimulateMissedCallsResponse:
    campaign = attendance_service.get_run(session, run_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Attendance run not found")
    result = attendance_service.simulate_missed_calls(session, campaign)
    return SimulateMissedCallsResponse(**result)


@router.post("/runs/{run_id}/missed-call", response_model=MissedCallResponse)
def missed_call(run_id: UUID, req: MissedCallRequest, session: SessionDep) -> MissedCallResponse:
    campaign = attendance_service.get_run(session, run_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Attendance run not found")
    record = attendance_service.mark_present_by_mobile(session, run_id, req.mobile)
    if record is None:
        return MissedCallResponse(marked=False)
    return MissedCallResponse(marked=True, worker_id=record.worker_id, record_id=record.id, status=record.status)


@router.get("/runs/{run_id}/locations/{location_id}", response_model=LocationDetail)
def get_location_detail(run_id: UUID, location_id: UUID, session: SessionDep) -> LocationDetail:
    campaign = attendance_service.get_run(session, run_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Attendance run not found")
    detail = attendance_service.location_detail(session, run_id, location_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Location not found in this run")
    return LocationDetail(
        location_id=detail["location_id"],
        location_name=detail["location_name"],
        region=detail["region"],
        supervisor_name=detail["supervisor_name"],
        supervisor_mobile=detail["supervisor_mobile"],
        supervisor_call_id=detail["supervisor_call_id"],
        workers=[WorkerAttendanceOut(**w) for w in detail["workers"]],
        counts=AttendanceCounts(**detail["counts"]),
    )


@router.post("/records/{record_id}/mark", response_model=WorkerAttendanceOut)
def mark_record(record_id: UUID, req: RecordMarkRequest, session: SessionDep) -> WorkerAttendanceOut:
    record = attendance_service.get_record(session, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    record = attendance_service.manual_mark(session, record, status=req.status, reason=req.reason)

    worker = session.get(Worker, record.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found for this record")
    return WorkerAttendanceOut(
        record_id=record.id,
        worker_id=worker.id,
        full_name=worker.full_name,
        employee_id=worker.employee_id,
        mobile=worker.mobile,
        status=record.status,
        source=record.source,
        reason=record.reason,
        marked_at=record.marked_at,
    )
