import time
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.scheduler import wait_until_idle
from app.main import app
from app.models.call import Call
from app.models.enums import AttendanceSource, AttendanceStatus, CallEventSource
from app.models.location import Location
from app.models.worker import Worker
from app.providers.factory import get_voice_provider
from app.services import attendance as attendance_service
from app.services.calls import apply_call_update, provider_call_to_update

_RUN_DATE = date(2026, 8, 24)


def _wait_for_provider_status(provider, provider_call_id: str, status: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if provider.get_call(provider_call_id).status == status:
            return
        time.sleep(0.05)
    raise AssertionError(f"provider call {provider_call_id} never reached {status}")


def test_seed_demo_default_scale_is_idempotent_via_api():
    """~100 locations x ~1,000 workers total, re-running creates nothing new."""
    client = TestClient(app)

    resp = client.post("/api/attendance/seed-demo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["locations"] == 100
    assert 800 <= body["workers"] <= 1200
    assert body["created_locations"] == 100
    assert body["created_workers"] == body["workers"]

    resp2 = client.post("/api/attendance/seed-demo")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["locations"] == body["locations"]
    assert body2["workers"] == body["workers"]
    assert body2["created_locations"] == 0
    assert body2["created_workers"] == 0

    locations = client.get("/api/attendance/locations").json()
    assert len(locations) == 100
    assert sum(loc["worker_count"] for loc in locations) == body["workers"]


def test_missed_call_marks_present_and_is_idempotent():
    with Session(engine) as session:
        attendance_service.seed_demo(session, num_locations=1, workers_per_location=8)
        location = session.exec(select(Location)).first()
        worker = session.exec(
            select(Worker).where(Worker.location_id == location.id, Worker.mobile.is_not(None))
        ).first()
        assert worker is not None, "deterministic seed unexpectedly produced no worker with a mobile"

        provider = get_voice_provider()
        campaign = attendance_service.create_run(session, provider, run_date=_RUN_DATE)

        record = attendance_service.mark_present_by_mobile(session, campaign.id, worker.mobile)
        assert record is not None
        assert record.status == AttendanceStatus.present
        assert record.source == AttendanceSource.missed_call
        first_marked_at = record.marked_at

        # idempotent: calling again for the same worker is a no-op
        record_again = attendance_service.mark_present_by_mobile(session, campaign.id, worker.mobile)
        assert record_again.status == AttendanceStatus.present
        assert record_again.marked_at == first_marked_at

    client = TestClient(app)
    unknown_resp = client.post(f"/api/attendance/runs/{campaign.id}/missed-call", json={"mobile": "+919999999999"})
    assert unknown_resp.status_code == 200
    assert unknown_resp.json()["marked"] is False


def test_missed_call_present_is_never_downgraded_by_a_later_supervisor_absent_report():
    with Session(engine) as session:
        attendance_service.seed_demo(session, num_locations=1, workers_per_location=8)
        location = session.exec(select(Location)).first()
        worker = session.exec(
            select(Worker).where(Worker.location_id == location.id, Worker.mobile.is_not(None))
        ).first()
        assert worker is not None

        provider = get_voice_provider()
        campaign = attendance_service.create_run(session, provider, run_date=_RUN_DATE)

        record = attendance_service.mark_present_by_mobile(session, campaign.id, worker.mobile)
        assert record.status == AttendanceStatus.present

        call = session.exec(select(Call).where(Call.campaign_id == campaign.id)).first()
        call.status = "COMPLETED"
        call.lifecycle_status = "COMPLETED"
        call.result = {"present_employee_ids": [], "absent_employee_ids": [worker.employee_id]}
        session.add(call)
        session.commit()
        session.refresh(call)

        attendance_service.process_supervisor_call(session, call, campaign)

        session.refresh(record)
        assert record.status == AttendanceStatus.present  # never downgraded
        assert record.source == AttendanceSource.missed_call


def test_supervisor_unreachable_marks_pending_workers_unreachable():
    with Session(engine) as session:
        attendance_service.seed_demo(session, num_locations=1, workers_per_location=6)
        provider = get_voice_provider()
        campaign = attendance_service.create_run(session, provider, run_date=_RUN_DATE)

        call = session.exec(select(Call).where(Call.campaign_id == campaign.id)).first()
        call.status = "FAILED"
        session.add(call)
        session.commit()
        session.refresh(call)

        summary = attendance_service.process_supervisor_call(session, call, campaign)
        assert summary["unreachable"] > 0
        assert summary["present"] == 0 and summary["absent"] == 0

        records = attendance_service.run_records(session, campaign.id)
        assert all(r.status == AttendanceStatus.unreachable for r in records)
        assert all(r.reason == "Supervisor unreachable" for r in records)

        # idempotent: nothing left pending to mark on a second pass
        summary_again = attendance_service.process_supervisor_call(session, call, campaign)
        assert summary_again["unreachable"] == 0
        records_again = attendance_service.run_records(session, campaign.id)
        assert [r.status for r in records_again] == [r.status for r in records]


def test_attendance_processing_is_idempotent_and_near_target_present_rate(monkeypatch):
    monkeypatch.setattr(settings, "ATTENDANCE_PRESENT_RATE", 0.85)
    with Session(engine) as session:
        attendance_service.seed_demo(session, num_locations=1, workers_per_location=200)
        provider = get_voice_provider()
        campaign = attendance_service.create_run(session, provider, run_date=_RUN_DATE)

        call = session.exec(select(Call).where(Call.campaign_id == campaign.id)).first()
        call.status = "COMPLETED"
        call.lifecycle_status = "COMPLETED"
        call.result = {}  # generic mock-shaped result -> falls back to the deterministic synth split
        session.add(call)
        session.commit()
        session.refresh(call)

        first = attendance_service.process_supervisor_call(session, call, campaign)
        after_first = {
            r.id: (r.status, r.source, r.marked_at) for r in attendance_service.run_records(session, campaign.id)
        }

        second = attendance_service.process_supervisor_call(session, call, campaign)
        after_second = {
            r.id: (r.status, r.source, r.marked_at) for r in attendance_service.run_records(session, campaign.id)
        }

        assert after_first == after_second  # byte-for-byte identical on re-run
        total = first["present"] + first["absent"]
        assert total == second["present"] + second["absent"]
        rate = first["present"] / total
        assert abs(rate - 0.85) < 0.08


def test_attendance_end_to_end_via_api(monkeypatch):
    """Seed -> create run -> dispatch 100-style roll-calls (here, a handful) -> completion ->
    AttendanceRecords upserted -> heatmap/exceptions/location drill-down/manual override,
    entirely through the public API with VOICE_PROVIDER mock (forced by conftest) - no
    external keys involved, and nothing here reimplements webhook/poll handling."""
    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    with Session(engine) as session:
        attendance_service.seed_demo(session, num_locations=4, workers_per_location=6)

    client = TestClient(app)

    create_resp = client.post("/api/attendance/runs", json={})
    assert create_resp.status_code == 200
    run = create_resp.json()
    run_id = run["id"]
    assert run["counts"]["total"] > 0
    assert run["counts"]["pending"] == run["counts"]["total"]
    assert len(run["locations"]) == 4

    dispatch_resp = client.post(f"/api/attendance/runs/{run_id}/dispatch")
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["dispatched"] == 4

    detail = client.get(f"/api/attendance/runs/{run_id}").json()
    provider = get_voice_provider()
    for loc in detail["locations"]:
        call_id = loc["supervisor_call_id"]
        assert call_id
        call_detail = client.get(f"/api/calls/{call_id}").json()
        provider_call_id = call_detail["call"]["provider_call_id"]
        assert provider_call_id
        _wait_for_provider_status(provider, provider_call_id, "COMPLETED")
        update = provider_call_to_update(provider.get_call(provider_call_id), event_type="poll_snapshot")
        with Session(engine) as session:
            apply_call_update(session, update, source=CallEventSource.poll)

    # apply_call_update just scheduled post_process_call (roster reconciliation) as a one-off
    # background job for each call above - wait for all of them to actually finish rather than
    # polling the API and hoping a fixed timeout was long enough.
    wait_until_idle()
    final = client.get(f"/api/attendance/runs/{run_id}").json()

    assert final["counts"]["pending"] == 0
    assert final["counts"]["present"] + final["counts"]["absent"] == final["counts"]["total"]
    assert final["exceptions"] == []

    location_id = detail["locations"][0]["location_id"]
    loc_detail = client.get(f"/api/attendance/runs/{run_id}/locations/{location_id}").json()
    assert len(loc_detail["workers"]) > 0
    assert all(w["status"] in ("present", "absent") for w in loc_detail["workers"])

    sim_resp = client.post(f"/api/attendance/runs/{run_id}/simulate-missed-calls")
    assert sim_resp.status_code == 200
    assert "marked_present" in sim_resp.json()

    record_id = loc_detail["workers"][0]["record_id"]
    mark_resp = client.post(f"/api/attendance/records/{record_id}/mark", json={"status": "absent", "reason": "sick leave"})
    assert mark_resp.status_code == 200
    marked = mark_resp.json()
    assert marked["status"] == "absent"
    assert marked["source"] == "manual"
    assert marked["reason"] == "sick leave"

    runs_list = client.get("/api/attendance/runs").json()
    assert any(r["id"] == run_id for r in runs_list)
