"""Module 3: Attendance. An AttendanceRun IS a Campaign with module="attendance"; a
supervisor's roll-call IS a Call under it. Dispatch goes through the exact same calls_service
used everywhere else - nothing here reimplements webhook/poll handling. See
docs/attendance-design.md for the full design writeup this module is a POC of.
"""

import logging
import random
from datetime import date, datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.models.attendance_record import AttendanceRecord
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import AttendanceSource, AttendanceStatus, Module
from app.models.location import Location
from app.models.worker import Worker
from app.providers.base import Agent, AgentSpec, ProviderError, VoiceProvider
from app.services import calls as calls_service

logger = logging.getLogger("app.services.attendance")

_UNREACHABLE_STATUSES = {"NOT_CONNECTED", "FAILED", "CANCELLED"}

_ROLL_CALL_AGENT_NAME = "Attendance Roll-Call Supervisor"

_ROLL_CALL_AGENT_SPEC = AgentSpec(
    name=_ROLL_CALL_AGENT_NAME,
    voice_persona="neutral_concise",
    language="en-IN",
    persona_name="Roll Call Assistant",
    objective=(
        "Call a site supervisor each morning and collect, in the supervisor's own words, which "
        "of today's expected workers are present at the site and which are absent."
    ),
    introduction=(
        "Hello, this is the automated attendance line calling for today's roll call at your site. "
        "Could you tell me who is present today, and who is absent?"
    ),
    agent_prompt=(
        "You are a concise, polite attendance assistant calling a site supervisor for the daily "
        "roll call. Read out the expected worker list one by one if needed, listen for present/"
        "absent for each, and confirm the final counts before ending the call. Support the "
        "supervisor's local language if they switch."
    ),
    result_prompt=(
        "Return the worker ids reported present and the worker ids reported absent, plus any "
        "free-form notes the supervisor gave (e.g. reasons for absence)."
    ),
    custom_variables={"location_name": "string", "expected_worker_count": "number"},
    result_schema={
        "present_employee_ids": "list",
        "absent_employee_ids": "list",
        "notes": "string",
    },
)

# Demo seed data - deterministic so re-running seed-demo is idempotent (see seed_demo).
_REGIONS = ["North", "South", "East", "West", "Central"]
_FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
    "Ananya", "Diya", "Priya", "Isha", "Riya", "Kavya", "Anika", "Meera", "Sneha", "Pooja",
    "Rahul", "Amit", "Suresh", "Ramesh", "Vikram", "Sanjay", "Deepak", "Manoj", "Ravi", "Ajay",
    "Neha", "Kiran", "Lakshmi", "Divya", "Shreya", "Nisha", "Pallavi", "Swati", "Anjali", "Rekha",
]
_LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Kumar", "Singh", "Reddy", "Rao", "Nair", "Iyer",
    "Menon", "Das", "Roy", "Chatterjee", "Mukherjee", "Joshi", "Desai", "Shah", "Mehta", "Yadav",
]
_SITE_KINDS = ["Warehouse", "Construction Site", "Distribution Hub", "Retail Store", "Assembly Plant"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fake_mobile(rng: random.Random) -> str:
    """Valid-format Indian mobile: +91 followed by a 10-digit number starting 6-9."""
    first_digit = rng.choice("6789")
    rest = "".join(rng.choice("0123456789") for _ in range(9))
    return f"+91{first_digit}{rest}"


def _fake_name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"


# --- Demo seeding ---


def seed_demo(session: Session, *, num_locations: int = 100, workers_per_location: int = 10) -> dict[str, int]:
    """Create `num_locations` locations x ~`workers_per_location` workers each, with a named
    supervisor and valid-format fake mobiles for everyone. Deterministic naming (Location NNN,
    employee id LNNN-Wnn) makes this idempotent: re-running only fills in whatever's missing,
    never duplicates.
    """
    existing_location_names = set(session.exec(select(Location.name)).all())
    existing_employee_ids = set(session.exec(select(Worker.employee_id)).all())

    created_locations = 0
    created_workers = 0

    for i in range(1, num_locations + 1):
        location_seq = f"{i:03d}"
        name = f"{_SITE_KINDS[i % len(_SITE_KINDS)]} {location_seq}"
        location_rng = random.Random(f"location:{location_seq}")

        if name not in existing_location_names:
            location = Location(
                name=name,
                region=_REGIONS[i % len(_REGIONS)],
                supervisor_name=_fake_name(location_rng),
                supervisor_mobile=_fake_mobile(location_rng),
            )
            session.add(location)
            session.commit()
            session.refresh(location)
            existing_location_names.add(name)
            created_locations += 1
        else:
            location = session.exec(select(Location).where(Location.name == name)).one()

        # workers_per_location is a target, not a hard count - vary it slightly per site so a
        # heatmap of 100 identical-sized sites doesn't look synthetic.
        worker_rng = random.Random(f"workers:{location_seq}")
        site_worker_count = workers_per_location + worker_rng.randint(-2, 2)

        for w in range(1, max(site_worker_count, 1) + 1):
            employee_id = f"{location_seq}-W{w:02d}"
            if employee_id in existing_employee_ids:
                continue
            worker_seed_rng = random.Random(f"worker:{employee_id}")
            worker = Worker(
                location_id=location.id,
                full_name=_fake_name(worker_seed_rng),
                employee_id=employee_id,
                # ~90% of workers have a registered mobile - the rest can only be reached via
                # the supervisor roll-call, which is exactly the point of that primary path.
                mobile=_fake_mobile(worker_seed_rng) if worker_seed_rng.random() < 0.9 else None,
            )
            session.add(worker)
            existing_employee_ids.add(employee_id)
            created_workers += 1

        session.commit()

    total_locations = session.exec(select(Location)).all()
    total_workers = session.exec(select(Worker)).all()
    return {
        "locations": len(total_locations),
        "workers": len(total_workers),
        "created_locations": created_locations,
        "created_workers": created_workers,
    }


def list_locations_with_counts(session: Session) -> list[tuple[Location, int]]:
    locations = list(session.exec(select(Location).order_by(Location.name)))
    if not locations:
        return []
    workers = list(session.exec(select(Worker.location_id)))
    counts: dict[UUID, int] = {}
    for location_id in workers:
        counts[location_id] = counts.get(location_id, 0) + 1
    return [(loc, counts.get(loc.id, 0)) for loc in locations]


# --- Run lifecycle ---


def _get_or_create_roll_call_agent(provider: VoiceProvider) -> Agent:
    for agent in provider.list_agents():
        if agent.name == _ROLL_CALL_AGENT_NAME:
            return agent
    return provider.create_agent(_ROLL_CALL_AGENT_SPEC)


def create_run(session: Session, provider: VoiceProvider, *, run_date: date | None = None) -> Campaign:
    """Materialize a new AttendanceRun: one pending AttendanceRecord per worker, and one
    (not-yet-dispatched) supervisor roll-call Call per location, carrying that location's
    expected worker roster in custom_data. Dispatch is a separate step (dispatch_run)."""
    resolved_date = run_date or date.today()
    agent = _get_or_create_roll_call_agent(provider)

    campaign = Campaign(
        name=f"Attendance Roll-Call - {resolved_date.isoformat()}",
        module=Module.attendance,
        agent_id=agent.id,
        result_schema=agent.result_schema,
        status="active",
        meta={"run_date": resolved_date.isoformat(), "mode": "supervisor"},
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    locations = list(session.exec(select(Location).order_by(Location.name)))
    for location in locations:
        workers = list(session.exec(select(Worker).where(Worker.location_id == location.id)))

        call = calls_service.create_draft_call(
            session,
            campaign_id=campaign.id,
            callee_name=location.supervisor_name,
            mobile_number=location.supervisor_mobile,
            custom_data={
                "location_id": str(location.id),
                "location_name": location.name,
                "expected_employee_ids": [w.employee_id for w in workers],
            },
        )
        for worker in workers:
            session.add(
                AttendanceRecord(run_id=campaign.id, location_id=location.id, worker_id=worker.id, call_id=call.id)
            )

    session.commit()
    return campaign


def dispatch_run(session: Session, provider: VoiceProvider, campaign: Campaign) -> int:
    """Dispatch every not-yet-dispatched supervisor call under this run. A dispatch that fails
    outright (bad number, provider outage) is the one place a call never reaches the normal
    COMPLETED post-call pipeline, so we resolve that location's records right here instead of
    waiting on a webhook that will never come."""
    calls = list(session.exec(select(Call).where(Call.campaign_id == campaign.id).order_by(Call.created_at)))
    dispatched = 0
    for call in calls:
        if call.provider_call_id is not None:
            continue
        try:
            call = calls_service.dispatch_call(session, provider, call, agent_id=campaign.agent_id)
        except ProviderError:
            call = session.get(Call, call.id)  # already persisted as FAILED by dispatch_call
            process_supervisor_call(session, call, campaign)
        dispatched += 1
    return dispatched


# --- Roster reconciliation (called from post_call.py's attendance branch, and from the
# dispatch-failure path above) ---


def process_supervisor_call(session: Session, call: Call, campaign: Campaign) -> dict[str, int]:
    """Reconcile one location's AttendanceRecords against its supervisor call's outcome.
    Idempotent: calling this more than once for the same call yields identical records, since
    every branch below either sets a deterministic value or is a no-op on an already-resolved
    record. Never downgrades a `present` record (e.g. from an earlier missed call) to absent.
    """
    location_id_raw = call.custom_data.get("location_id")
    if not location_id_raw:
        return {"present": 0, "absent": 0, "unreachable": 0}
    location_id = UUID(location_id_raw)

    records = list(
        session.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.run_id == campaign.id,
                AttendanceRecord.location_id == location_id,
            )
        )
    )
    if not records:
        return {"present": 0, "absent": 0, "unreachable": 0}

    if call.status in _UNREACHABLE_STATUSES or call.lifecycle_status in _UNREACHABLE_STATUSES:
        return _mark_unreachable(session, records, call)

    if call.lifecycle_status != "COMPLETED" or call.result is None:
        return {"present": 0, "absent": 0, "unreachable": 0}

    workers = {w.id: w for w in session.exec(select(Worker).where(Worker.location_id == location_id))}
    workers_by_employee_id = {w.employee_id: w for w in workers.values()}
    expected_employee_ids = call.custom_data.get("expected_employee_ids", [])

    present_ids, absent_ids = _parse_roster(call, expected_employee_ids)
    return _apply_roster(session, records, workers_by_employee_id, present_ids, absent_ids, call)


def _parse_roster(call: Call, expected_employee_ids: list[str]) -> tuple[set[str], set[str]]:
    """The real-agent path: a voice agent that actually spoke to the supervisor would return
    present/absent employee ids directly in its structured result. In production the
    supervisor speaks NAMES, not ids - matching those back to workers needs fuzzy name
    resolution and/or a spoken confirmation step ("that's Aarav Sharma, correct?"); this POC
    uses employee_ids so the demo is a clean, deterministic reconciliation instead of a fuzzy-
    matching exercise. The mock voice provider doesn't know our result_schema's "list" fields
    (it only fills booleans/numbers/strings - see providers/mock.py::_fake_result), so its
    generic result never carries these keys and we fall through to a synthetic split below.
    """
    result = call.result or {}
    present_raw = result.get("present_employee_ids")
    absent_raw = result.get("absent_employee_ids")

    if isinstance(present_raw, list) or isinstance(absent_raw, list):
        present = {str(x) for x in (present_raw or [])}
        absent = {str(x) for x in (absent_raw or [])}
        unaccounted = [eid for eid in expected_employee_ids if eid not in present and eid not in absent]
        if unaccounted:
            synth_present, synth_absent = _synthesize_split(call.id, unaccounted)
            present |= synth_present
            absent |= synth_absent
        return present, absent

    return _synthesize_split(call.id, expected_employee_ids)


def _synthesize_split(call_id: UUID, employee_ids: list[str]) -> tuple[set[str], set[str]]:
    """Deterministic present/absent split seeded by call id, targeting
    settings.ATTENDANCE_PRESENT_RATE - stable across repeated calls (idempotent) but varied
    across locations, for demo realism."""
    rng = random.Random(str(call_id))
    present: set[str] = set()
    absent: set[str] = set()
    for employee_id in employee_ids:
        if rng.random() < settings.ATTENDANCE_PRESENT_RATE:
            present.add(employee_id)
        else:
            absent.add(employee_id)
    return present, absent


def _apply_roster(
    session: Session,
    records: list[AttendanceRecord],
    workers_by_employee_id: dict[str, Worker],
    present_ids: set[str],
    absent_ids: set[str],
    call: Call,
) -> dict[str, int]:
    records_by_worker_id = {r.worker_id: r for r in records}
    present_count = 0
    absent_count = 0

    for employee_id in present_ids:
        worker = workers_by_employee_id.get(employee_id)
        record = records_by_worker_id.get(worker.id) if worker else None
        if record is None:
            continue
        present_count += 1
        if record.status != AttendanceStatus.present:
            record.status = AttendanceStatus.present
            record.source = AttendanceSource.supervisor_call
            record.call_id = call.id
            record.reason = None
            record.marked_at = _utcnow()
            session.add(record)

    for employee_id in absent_ids:
        worker = workers_by_employee_id.get(employee_id)
        record = records_by_worker_id.get(worker.id) if worker else None
        if record is None:
            continue
        absent_count += 1
        if record.status == AttendanceStatus.pending:  # never downgrade an existing present
            record.status = AttendanceStatus.absent
            record.source = AttendanceSource.supervisor_call
            record.call_id = call.id
            record.marked_at = _utcnow()
            session.add(record)

    session.commit()
    return {"present": present_count, "absent": absent_count, "unreachable": 0}


def _mark_unreachable(session: Session, records: list[AttendanceRecord], call: Call) -> dict[str, int]:
    count = 0
    for record in records:
        if record.status == AttendanceStatus.pending:
            record.status = AttendanceStatus.unreachable
            record.source = AttendanceSource.supervisor_call
            record.call_id = call.id
            record.reason = "Supervisor unreachable"
            record.marked_at = _utcnow()
            session.add(record)
            count += 1
    session.commit()
    return {"present": 0, "absent": 0, "unreachable": count}


# --- Missed-call inbound (low-tech, zero-cost-to-worker path) ---


def mark_present_by_mobile(session: Session, run_id: UUID, mobile: str) -> AttendanceRecord | None:
    """A worker's registered mobile giving a missed call marks them present for the run.
    Idempotent, and never downgrades: wins only over pending/absent/unreachable, never
    overwrites an existing `present`."""
    worker = session.exec(select(Worker).where(Worker.mobile == mobile)).first()
    if worker is None:
        return None

    record = session.exec(
        select(AttendanceRecord).where(AttendanceRecord.run_id == run_id, AttendanceRecord.worker_id == worker.id)
    ).first()
    if record is None:
        return None

    if record.status != AttendanceStatus.present:
        record.status = AttendanceStatus.present
        record.source = AttendanceSource.missed_call
        record.reason = None
        record.marked_at = _utcnow()
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def simulate_missed_calls(session: Session, campaign: Campaign) -> dict[str, int]:
    """Demo stand-in for the morning missed-call window: deterministically (seeded by run id +
    worker id, so repeat calls are idempotent) mark ATTENDANCE_MISSED_CALL_RATE of workers with
    a registered mobile present via the same mark_present_by_mobile path a real missed call
    would use."""
    records = list(session.exec(select(AttendanceRecord).where(AttendanceRecord.run_id == campaign.id)))
    if not records:
        return {"marked_present": 0}

    worker_ids = [r.worker_id for r in records]
    workers = {w.id: w for w in session.exec(select(Worker).where(Worker.id.in_(worker_ids)))}

    marked = 0
    for record in records:
        worker = workers.get(record.worker_id)
        if worker is None or not worker.mobile:
            continue
        rng = random.Random(f"{campaign.id}:{worker.id}")
        if rng.random() < settings.ATTENDANCE_MISSED_CALL_RATE:
            updated = mark_present_by_mobile(session, campaign.id, worker.mobile)
            if updated is not None:
                marked += 1
    return {"marked_present": marked}


# --- Reads (aggregates are always derived, never stored) ---


def list_runs(session: Session) -> list[Campaign]:
    stmt = select(Campaign).where(Campaign.module == Module.attendance).order_by(Campaign.created_at.desc())
    return list(session.exec(stmt).all())


def get_run(session: Session, run_id: UUID) -> Campaign | None:
    campaign = session.get(Campaign, run_id)
    if campaign is None or campaign.module != Module.attendance:
        return None
    return campaign


def counts_for_records(records: list[AttendanceRecord]) -> dict[str, float | int]:
    counts = {status.value: 0 for status in AttendanceStatus}
    for record in records:
        counts[record.status.value] += 1
    total = len(records)
    rate = (counts["present"] / total) if total else 0.0
    return {**counts, "total": total, "rate": rate}


def run_records(session: Session, run_id: UUID) -> list[AttendanceRecord]:
    return list(session.exec(select(AttendanceRecord).where(AttendanceRecord.run_id == run_id)))


def location_grid(session: Session, run_id: UUID) -> list[dict]:
    """Per-location attendance counts, driving the heatmap - includes each location's
    supervisor call status so the frontend can tell "still ringing" from "done"."""
    records = run_records(session, run_id)
    calls = list(session.exec(select(Call).where(Call.campaign_id == run_id)))
    calls_by_location: dict[UUID, Call] = {}
    for call in calls:
        loc_raw = call.custom_data.get("location_id")
        if loc_raw:
            calls_by_location[UUID(loc_raw)] = call

    by_location: dict[UUID, list[AttendanceRecord]] = {}
    for record in records:
        by_location.setdefault(record.location_id, []).append(record)

    locations = {loc.id: loc for loc in session.exec(select(Location).where(Location.id.in_(by_location.keys())))}

    grid = []
    for location_id, loc_records in by_location.items():
        location = locations.get(location_id)
        if location is None:
            continue
        call = calls_by_location.get(location_id)
        grid.append(
            {
                "location_id": location_id,
                "location_name": location.name,
                "region": location.region,
                "supervisor_call_id": call.id if call else None,
                "supervisor_call_status": call.status if call else None,
                "counts": counts_for_records(loc_records),
            }
        )
    grid.sort(key=lambda row: row["location_name"])
    return grid


def exceptions(session: Session, run_id: UUID) -> list[dict]:
    """Workers needing follow-up: still unresolved (pending) or explicitly unreachable."""
    records = [
        r
        for r in run_records(session, run_id)
        if r.status in (AttendanceStatus.pending, AttendanceStatus.unreachable)
    ]
    if not records:
        return []

    worker_ids = [r.worker_id for r in records]
    workers = {w.id: w for w in session.exec(select(Worker).where(Worker.id.in_(worker_ids)))}
    location_ids = [r.location_id for r in records]
    locations = {loc.id: loc for loc in session.exec(select(Location).where(Location.id.in_(location_ids)))}

    out = []
    for record in records:
        worker = workers.get(record.worker_id)
        location = locations.get(record.location_id)
        if worker is None or location is None:
            continue
        out.append(
            {
                "record_id": record.id,
                "worker_id": worker.id,
                "worker_name": worker.full_name,
                "employee_id": worker.employee_id,
                "location_id": location.id,
                "location_name": location.name,
                "status": record.status,
                "reason": record.reason,
            }
        )
    return out


def location_detail(session: Session, run_id: UUID, location_id: UUID) -> dict | None:
    location = session.get(Location, location_id)
    if location is None:
        return None

    records = list(
        session.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.run_id == run_id, AttendanceRecord.location_id == location_id
            )
        )
    )
    if not records:
        return None

    worker_ids = [r.worker_id for r in records]
    workers = {w.id: w for w in session.exec(select(Worker).where(Worker.id.in_(worker_ids)))}

    call = next(
        (
            c
            for c in session.exec(select(Call).where(Call.campaign_id == run_id))
            if c.custom_data.get("location_id") == str(location_id)
        ),
        None,
    )

    workers_out = []
    for record in sorted(records, key=lambda r: workers[r.worker_id].employee_id if r.worker_id in workers else ""):
        worker = workers.get(record.worker_id)
        if worker is None:
            continue
        workers_out.append(
            {
                "record_id": record.id,
                "worker_id": worker.id,
                "full_name": worker.full_name,
                "employee_id": worker.employee_id,
                "mobile": worker.mobile,
                "status": record.status,
                "source": record.source,
                "reason": record.reason,
                "marked_at": record.marked_at,
            }
        )

    return {
        "location_id": location.id,
        "location_name": location.name,
        "region": location.region,
        "supervisor_name": location.supervisor_name,
        "supervisor_mobile": location.supervisor_mobile,
        "supervisor_call_id": call.id if call else None,
        "workers": workers_out,
        "counts": counts_for_records(records),
    }


def get_record(session: Session, record_id: UUID) -> AttendanceRecord | None:
    return session.get(AttendanceRecord, record_id)


def manual_mark(
    session: Session, record: AttendanceRecord, *, status: AttendanceStatus, reason: str | None
) -> AttendanceRecord:
    record.status = status
    record.source = AttendanceSource.manual
    record.reason = reason
    record.marked_at = _utcnow()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
