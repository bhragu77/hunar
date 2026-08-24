import time

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.main import app
from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import CallEventSource
from app.providers.factory import get_voice_provider
from app.providers.webhooks import compute_hunar_signature
from app.services.calls import CallUpdate, apply_call_update, create_call, provider_call_to_update


def _wait_for_provider_status(provider, provider_call_id: str, status: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if provider.get_call(provider_call_id).status == status:
            return
        time.sleep(0.05)
    raise AssertionError(f"provider call {provider_call_id} never reached {status}")


def test_mock_call_completes_and_poll_reconciles(monkeypatch):
    """The mock's own internal state (independent of our DB/webhook) reaches COMPLETED on its
    own, and the polling path - simulated directly here, with no live server involved - drives
    our Call row to the same terminal state. This is the fallback acceptance criterion: it
    works even when the webhook never arrives."""
    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    provider = get_voice_provider()

    with Session(engine) as session:
        call = create_call(
            session,
            provider,
            agent_id="agent_mock_001",
            callee_name="Test Candidate",
            mobile_number="+10000000000",
        )
        call_id = call.id
        provider_call_id = call.provider_call_id

    assert provider_call_id is not None

    _wait_for_provider_status(provider, provider_call_id, "COMPLETED")
    provider_call = provider.get_call(provider_call_id)

    update = provider_call_to_update(provider_call, event_type="poll_snapshot")
    with Session(engine) as session:
        reconciled = apply_call_update(session, update, source=CallEventSource.poll)

    assert reconciled is not None
    assert reconciled.id == call_id
    assert reconciled.status == "COMPLETED"
    assert reconciled.result
    assert reconciled.recording_url
    assert reconciled.duration_seconds is not None


def test_apply_call_update_is_idempotent():
    with Session(engine) as session:
        call = Call(
            request_id="req_idem_test",
            provider_call_id="call_idem_test",
            callee_name="Idempotency Target",
            mobile_number="+10000000001",
        )
        session.add(call)
        session.commit()
        session.refresh(call)
        call_id = call.id

    update = CallUpdate(
        provider_call_id="call_idem_test",
        request_id="req_idem_test",
        event_type="call_summary",
        status="COMPLETED",
        result={"interested": True},
        recording_url="https://example.test/rec.mp3",
        duration_seconds=12,
    )

    with Session(engine) as session:
        first = apply_call_update(session, update, source=CallEventSource.webhook)
    with Session(engine) as session:
        second = apply_call_update(session, update, source=CallEventSource.webhook)

    assert first is not None and second is not None
    assert first.status == second.status == "COMPLETED"
    assert first.updated_at == second.updated_at  # second call was a true no-op

    with Session(engine) as session:
        events = session.exec(select(CallEvent).where(CallEvent.call_id == call_id)).all()
    assert len(events) == 1


def test_webhook_endpoint_accepts_valid_and_rejects_bad_signatures():
    with Session(engine) as session:
        call = Call(
            request_id="req_webhook_test",
            provider_call_id="call_webhook_test",
            callee_name="Webhook Target",
            mobile_number="+10000000002",
            status="IN_PROGRESS",
        )
        session.add(call)
        session.commit()
        call_id = call.id

    payload = (
        b'{"event_type":"call_summary","call_id":"call_webhook_test",'
        b'"request_id":"req_webhook_test","status":"COMPLETED",'
        b'"result":{"interested":true},"recording_url":"https://example.test/r.mp3",'
        b'"duration_seconds":9}'
    )
    timestamp = str(int(time.time()))
    signature = compute_hunar_signature(settings.MOCK_WEBHOOK_SECRET, timestamp, payload)

    client = TestClient(app)

    # invalid signature -> 401
    bad_response = client.post(
        "/api/webhooks/hunar",
        content=payload,
        headers={"X-Hunar-Signature": "not-valid", "X-Hunar-Timestamp": timestamp},
    )
    assert bad_response.status_code == 401

    # stale timestamp -> 401
    stale_timestamp = str(int(time.time()) - 400)
    stale_signature = compute_hunar_signature(settings.MOCK_WEBHOOK_SECRET, stale_timestamp, payload)
    stale_response = client.post(
        "/api/webhooks/hunar",
        content=payload,
        headers={"X-Hunar-Signature": stale_signature, "X-Hunar-Timestamp": stale_timestamp},
    )
    assert stale_response.status_code == 401

    # valid signature -> 200, and the Call is updated
    good_response = client.post(
        "/api/webhooks/hunar",
        content=payload,
        headers={"X-Hunar-Signature": signature, "X-Hunar-Timestamp": timestamp},
    )
    assert good_response.status_code == 200
    assert good_response.json() == {"received": True}

    with Session(engine) as session:
        updated = session.get(Call, call_id)
    assert updated.status == "COMPLETED"
    assert updated.result == {"interested": True}

    # duplicate delivery of the exact same payload -> still 200, idempotent (no 2nd event)
    dup_response = client.post(
        "/api/webhooks/hunar",
        content=payload,
        headers={"X-Hunar-Signature": signature, "X-Hunar-Timestamp": timestamp},
    )
    assert dup_response.status_code == 200
    with Session(engine) as session:
        events = session.exec(select(CallEvent).where(CallEvent.call_id == call_id)).all()
    assert len(events) == 1


def test_poll_stale_calls_reconciles_non_terminal_calls(monkeypatch):
    from app.services.poller import poll_stale_calls

    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    monkeypatch.setattr(settings, "POLL_STALE_AFTER_SECONDS", 0)
    provider = get_voice_provider()

    with Session(engine) as session:
        call = create_call(
            session,
            provider,
            agent_id="agent_mock_001",
            callee_name="Poll Target",
            mobile_number="+10000000003",
        )
        call_id = call.id
        provider_call_id = call.provider_call_id

    _wait_for_provider_status(provider, provider_call_id, "COMPLETED")

    poll_stale_calls()

    with Session(engine) as session:
        reconciled = session.get(Call, call_id)
    assert reconciled.status == "COMPLETED"
    assert reconciled.last_polled_at is not None
