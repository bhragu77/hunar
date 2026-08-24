import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.integrations.transcription import transcribe
from app.main import app
from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import CallEventSource, PostCallStatus
from app.providers.factory import get_voice_provider
from app.services.calls import apply_call_update, provider_call_to_update
from app.services.hiring import compute_funnel
from app.services.post_call import post_process_call
from app.services.scorecard import build_scorecard


def _wait_for_provider_status(provider, provider_call_id: str, status: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if provider.get_call(provider_call_id).status == status:
            return
        time.sleep(0.05)
    raise AssertionError(f"provider call {provider_call_id} never reached {status}")


def test_hiring_module_end_to_end_via_api(monkeypatch):
    """Interview -> candidate -> dispatch -> completion -> transcript -> scorecard ->
    funnel, entirely through the public API, with VOICE_PROVIDER/LLM_PROVIDER/
    TRANSCRIPTION_PROVIDER all mock (forced by conftest) - no external keys involved."""
    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    client = TestClient(app)

    create_resp = client.post(
        "/api/hiring/interviews",
        json={
            "title": "Backend Engineer",
            "description": "Looking for a strong backend engineer with Python experience.",
            "agent_id": "agent_mock_001",
        },
    )
    assert create_resp.status_code == 200
    interview = create_resp.json()
    interview_id = interview["id"]
    assert interview["funnel"] == {"total": 0, "by_status": {}, "by_recommendation": {}}

    add_resp = client.post(
        f"/api/hiring/interviews/{interview_id}/candidates",
        params={"dispatch": True},
        json={
            "candidates": [
                {
                    "callee_name": "Jane Doe",
                    "mobile_number": "+10000000010",
                    "custom_data": {"role_title": "Backend Engineer", "min_experience_years": 3},
                }
            ]
        },
    )
    assert add_resp.status_code == 200
    candidates = add_resp.json()
    assert len(candidates) == 1
    call_id = candidates[0]["id"]

    call_detail = client.get(f"/api/calls/{call_id}").json()
    provider_call_id = call_detail["call"]["provider_call_id"]
    assert provider_call_id

    # No real server is listening in-process for MockProvider's self-webhook to reach, so
    # reconcile the same way the real polling reconciler would.
    provider = get_voice_provider()
    _wait_for_provider_status(provider, provider_call_id, "COMPLETED")
    update = provider_call_to_update(provider.get_call(provider_call_id), event_type="poll_snapshot")
    with Session(engine) as session:
        apply_call_update(session, update, source=CallEventSource.poll)

    detail = None
    deadline = time.time() + 5
    while time.time() < deadline:
        detail = client.get(f"/api/calls/{call_id}").json()
        if detail["call"]["scorecard_status"] != "pending" and detail["call"]["transcript_status"] != "pending":
            break
        time.sleep(0.1)
    else:
        pytest.fail("post-call pipeline did not finish in time")

    assert detail["call"]["transcript_status"] == "done"
    assert detail["call"]["transcript"]
    assert detail["call"]["scorecard_status"] == "done"
    assert detail["call"]["scorecard"]["recommendation"] in {"advance", "hold", "reject"}
    assert isinstance(detail["call"]["scorecard"]["overall_score"], int)

    interview_detail = client.get(f"/api/hiring/interviews/{interview_id}").json()
    assert interview_detail["funnel"]["total"] == 1
    assert interview_detail["funnel"]["by_status"].get("COMPLETED") == 1
    recommendation = detail["call"]["scorecard"]["recommendation"]
    assert interview_detail["funnel"]["by_recommendation"].get(recommendation) == 1
    assert interview_detail["candidates"][0]["recommendation"] == recommendation


def test_post_process_call_is_idempotent():
    with Session(engine) as session:
        call = Call(
            request_id="req_idem_pipeline_test",
            callee_name="Idempotency Target",
            mobile_number="+10000000011",
            status="COMPLETED",
            lifecycle_status="COMPLETED",
            result={"interested": True, "reachable": True},
        )
        session.add(call)
        session.commit()
        session.refresh(call)
        call_id = call.id

    post_process_call(call_id)
    with Session(engine) as session:
        call = session.get(Call, call_id)
        first_transcript = call.transcript
        first_scorecard = call.scorecard
        first_generated_at = call.scorecard_generated_at
        first_event_count = len(session.exec(select(CallEvent).where(CallEvent.call_id == call_id)).all())

    post_process_call(call_id)
    with Session(engine) as session:
        call = session.get(Call, call_id)
        assert call.transcript == first_transcript
        assert call.scorecard == first_scorecard
        assert call.scorecard_generated_at == first_generated_at
        second_event_count = len(session.exec(select(CallEvent).where(CallEvent.call_id == call_id)).all())

    assert first_event_count == second_event_count  # no duplicate work on the second run


def test_compute_funnel_counts_mixed_states():
    calls = [
        Call(
            request_id="f1",
            callee_name="A",
            mobile_number="+1",
            status="COMPLETED",
            scorecard_status=PostCallStatus.done,
            scorecard={"recommendation": "advance"},
        ),
        Call(
            request_id="f2",
            callee_name="B",
            mobile_number="+1",
            status="COMPLETED",
            scorecard_status=PostCallStatus.done,
            scorecard={"recommendation": "reject"},
        ),
        Call(request_id="f3", callee_name="C", mobile_number="+1", status="IN_PROGRESS"),
        Call(request_id="f4", callee_name="D", mobile_number="+1", status="NOT_STARTED"),
    ]

    funnel = compute_funnel(calls)

    assert funnel["total"] == 4
    assert funnel["by_status"] == {"COMPLETED": 2, "IN_PROGRESS": 1, "NOT_STARTED": 1}
    assert funnel["by_recommendation"] == {"advance": 1, "reject": 1}


def test_llm_and_transcription_mock_backends_need_no_network(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network should never be called when LLM/TRANSCRIPTION_PROVIDER=mock")

    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "get", _boom)

    call = Call(
        request_id="req_net_test",
        callee_name="Net Test",
        mobile_number="+10000000009",
        result={"interested": True, "reachable": True},
    )

    scorecard = build_scorecard(call, None)
    assert scorecard["recommendation"] in {"advance", "hold", "reject"}
    assert isinstance(scorecard["overall_score"], int)

    transcript = transcribe(call)
    assert transcript is not None
    assert "Net Test" in transcript
