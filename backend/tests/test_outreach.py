import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.scheduler import wait_until_idle
from app.integrations.people_search.base import SearchCriteria
from app.integrations.people_search.mock import MockPeopleSearchProvider
from app.main import app
from app.models.call import Call
from app.models.enums import CallEventSource
from app.models.sourced_candidate import SourcedCandidate
from app.providers.base import ProviderError
from app.providers.factory import get_voice_provider
from app.services.agent_designer import RESULT_SCHEMA, design_outreach_agent
from app.services.calls import apply_call_update, provider_call_to_update
from app.services.jd_parser import parse_jd_to_criteria
from app.services.outreach import outreach_bucket
from app.services.sourced_candidates import upsert_sourced_candidates

_JD = """Senior Backend Engineer

We are hiring a Senior Backend Engineer with 4-7 years of experience in Python, FastAPI, and
PostgreSQL to join our team in Bengaluru. Strong communication skills required.
"""


def _reconcile_call(client: TestClient, call_id: str, timeout: float = 5.0) -> None:
    """No real server is listening in-process for MockProvider's self-webhook to reach (see
    test_hiring.py's identical helper), so reconcile the same way the real polling
    reconciler would: wait for the provider's own state to reach COMPLETED, then apply it -
    and then wait for the post-call pipeline job that apply_call_update just scheduled to
    actually finish, so no background job from this call is still in flight when this
    function returns (see app/core/scheduler.py::wait_until_idle)."""
    provider = get_voice_provider()
    call_detail = client.get(f"/api/calls/{call_id}").json()
    provider_call_id = call_detail["call"]["provider_call_id"]
    assert provider_call_id

    deadline = time.time() + timeout
    while time.time() < deadline:
        if provider.get_call(provider_call_id).status == "COMPLETED":
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"provider call {provider_call_id} never reached COMPLETED")

    update = provider_call_to_update(provider.get_call(provider_call_id), event_type="poll_snapshot")
    with Session(engine) as session:
        apply_call_update(session, update, source=CallEventSource.poll)
    wait_until_idle()


def _wait_for_terminal(client: TestClient, call_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    detail = None
    while time.time() < deadline:
        detail = client.get(f"/api/calls/{call_id}").json()
        call = detail["call"]
        if call["status"] in ("COMPLETED", "FAILED", "CANCELLED") and call["outreach_summary"] is not None:
            return detail
        time.sleep(0.1)
    pytest.fail(f"call {call_id} never reached a settled state with an outreach_summary")
    return detail  # unreachable, keeps type-checkers happy


def test_jd_parser_mock_needs_no_network(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network should never be called when LLM_PROVIDER=mock")

    monkeypatch.setattr(httpx, "post", _boom)

    criteria = parse_jd_to_criteria(_JD)
    assert isinstance(criteria, SearchCriteria)
    assert "Backend Engineer" in criteria.titles
    assert "senior" in criteria.seniorities
    assert "python" in criteria.skills
    assert "Bengaluru" in criteria.locations
    assert criteria.min_years == 4
    assert criteria.max_years == 7


def test_agent_designer_mock_needs_no_network(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network should never be called when LLM_PROVIDER=mock")

    monkeypatch.setattr(httpx, "post", _boom)

    spec = design_outreach_agent(_JD, "Senior Backend Engineer")
    assert spec.name
    assert spec.agent_prompt
    assert spec.result_schema == RESULT_SCHEMA


def test_people_search_mock_needs_no_network(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network should never be called for the mock people-search provider")

    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "get", _boom)

    provider = MockPeopleSearchProvider()
    criteria = SearchCriteria(titles=["Backend Engineer"], locations=["Bengaluru, India"])
    profiles = provider.search(criteria, 10)
    assert len(profiles) == 10
    assert all(p.full_name for p in profiles)
    # exercises the "occasional null phone" skip path
    assert any(p.mobile_number is None for p in profiles)
    assert any(p.mobile_number is not None for p in profiles)


@pytest.mark.parametrize(
    "call_kwargs,expected_bucket",
    [
        (None, "Sourced"),
        ({"status": "NOT_STARTED"}, "Contacting"),
        ({"status": "IN_PROGRESS"}, "Contacting"),
        ({"status": "FAILED"}, "No response"),
        ({"status": "CANCELLED"}, "No response"),
        ({"status": "COMPLETED", "engagement_status": "NOT_ENGAGED"}, "No response"),
        ({"status": "COMPLETED", "result": {"interested": True}}, "Interested"),
        ({"status": "COMPLETED", "result": {"interested": False}}, "Not interested"),
        ({"status": "COMPLETED", "result": {"callback_requested": True}}, "Follow-up required"),
        (
            {"status": "COMPLETED", "result": {"interested": True, "callback_requested": True}},
            "Follow-up required",
        ),
        ({"status": "COMPLETED", "result": {}}, "Contacted"),
        ({"status": "COMPLETED", "result": None}, "Contacted"),
    ],
)
def test_outreach_bucket_mapping(call_kwargs, expected_bucket):
    candidate = SourcedCandidate(
        campaign_id="00000000-0000-0000-0000-000000000000",
        full_name="Test Candidate",
        source="mock",
        dedupe_key="nc:test candidate|",
        call_id=None if call_kwargs is None else "11111111-1111-1111-1111-111111111111",
    )
    call = None
    if call_kwargs is not None:
        call = Call(request_id="req_bucket_test", callee_name="Test Candidate", mobile_number="+1", **call_kwargs)
    assert outreach_bucket(candidate, call) == expected_bucket


def test_search_again_dedupes_by_dedupe_key():
    provider = MockPeopleSearchProvider()
    criteria = SearchCriteria(titles=["Backend Engineer"], locations=["Bengaluru, India"])

    with Session(engine) as session:
        client = TestClient(app)
        create_resp = client.post("/api/outreach/campaigns", json={"title": "Backend Engineer", "job_description": _JD})
        campaign_id = create_resp.json()["id"]

        first_batch = upsert_sourced_candidates(
            session, campaign_id=campaign_id, profiles=provider.search(criteria, 10), source="mock"
        )
        assert len(first_batch) == 10

        # Same criteria -> the mock provider is deterministic -> re-searching is a true no-op.
        second_batch = upsert_sourced_candidates(
            session, campaign_id=campaign_id, profiles=provider.search(criteria, 10), source="mock"
        )
        assert len(second_batch) == 10

        # Different criteria -> mostly new, distinct profiles get appended.
        other_criteria = SearchCriteria(titles=["Data Scientist"], locations=["Mumbai, India"])
        third_batch = upsert_sourced_candidates(
            session, campaign_id=campaign_id, profiles=provider.search(other_criteria, 10), source="mock"
        )
        assert len(third_batch) > 10


def test_agent_autocreate_failure_path_returns_200(monkeypatch):
    def _boom(self, spec):
        raise ProviderError("mock outage", status_code=502)

    from app.providers.mock import MockProvider

    monkeypatch.setattr(MockProvider, "create_agent", _boom)
    get_voice_provider.cache_clear()

    client = TestClient(app)
    resp = client.post("/api/outreach/campaigns", json={"title": "Backend Engineer", "job_description": _JD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] is None
    assert body["agent_autocreated"] is False
    assert "mock outage" in body["agent_create_error"]

    get_voice_provider.cache_clear()


def test_dispatch_skips_candidates_without_phone(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    client = TestClient(app)

    create_resp = client.post("/api/outreach/campaigns", json={"title": "Backend Engineer", "job_description": _JD})
    campaign = create_resp.json()
    assert campaign["agent_id"]  # autocreate succeeded (mock)

    search_resp = client.post(f"/api/outreach/campaigns/{campaign['id']}/search")
    candidates = search_resp.json()
    assert len(candidates) == settings.PEOPLE_SEARCH_MAX_RESULTS

    with_phone = [c for c in candidates if c["mobile_number"]]
    without_phone = [c for c in candidates if not c["mobile_number"]]
    assert with_phone and without_phone

    select_ids = [c["id"] for c in with_phone[:2]] + [c["id"] for c in without_phone[:1]]
    client.post("/api/outreach/candidates/select", json={"candidate_ids": select_ids, "selected": True})

    dispatch_resp = client.post(f"/api/outreach/campaigns/{campaign['id']}/dispatch")
    assert dispatch_resp.status_code == 200
    result = dispatch_resp.json()
    assert len(result["dispatched"]) == 2
    assert result["skipped_no_phone"] == [without_phone[0]["id"]]

    # Drain the dispatched calls' background simulation threads before the test ends, so they
    # don't race the next test's table-cleanup fixture (see _reconcile_call's docstring).
    for candidate_id in result["dispatched"]:
        detail = client.get(f"/api/outreach/campaigns/{campaign['id']}").json()
        call_id = next(c["call_id"] for c in detail["candidates"] if c["id"] == candidate_id)
        _reconcile_call(client, call_id)


def test_outreach_end_to_end_via_api(monkeypatch):
    """JD -> criteria -> autocreated agent -> mock search -> select -> dispatch -> completion
    -> outreach_summary -> derived funnel bucket, entirely through the public API with
    PEOPLE_SEARCH_PROVIDER/LLM_PROVIDER/VOICE_PROVIDER/TRANSCRIPTION_PROVIDER all mock (forced
    by conftest) - no external keys involved."""
    monkeypatch.setattr(settings, "MOCK_CALL_DURATION_SECONDS", 1)
    client = TestClient(app)

    create_resp = client.post("/api/outreach/campaigns", json={"title": "Senior Backend Engineer", "job_description": _JD})
    assert create_resp.status_code == 200
    campaign = create_resp.json()
    assert campaign["criteria"]["titles"]
    assert campaign["agent_spec"]["result_schema"] == RESULT_SCHEMA
    assert campaign["agent_id"]  # AGENT_AUTOCREATE succeeded against the mock voice provider
    assert campaign["funnel"]["counts"]["Sourced"] == 0

    search_resp = client.post(f"/api/outreach/campaigns/{campaign['id']}/search")
    assert search_resp.status_code == 200
    candidates = search_resp.json()
    assert len(candidates) == settings.PEOPLE_SEARCH_MAX_RESULTS
    assert all(c["bucket"] == "Sourced" for c in candidates)

    dispatchable = [c for c in candidates if c["mobile_number"]][:3]
    select_resp = client.post(
        "/api/outreach/candidates/select",
        json={"candidate_ids": [c["id"] for c in dispatchable], "selected": True},
    )
    assert select_resp.status_code == 200
    assert all(c["selected"] for c in select_resp.json())

    dispatch_resp = client.post(f"/api/outreach/campaigns/{campaign['id']}/dispatch")
    assert dispatch_resp.status_code == 200
    dispatch_result = dispatch_resp.json()
    assert len(dispatch_result["dispatched"]) == 3

    detail = client.get(f"/api/outreach/campaigns/{campaign['id']}").json()
    dispatched_candidates = [c for c in detail["candidates"] if c["id"] in dispatch_result["dispatched"]]
    assert all(c["call_id"] for c in dispatched_candidates)

    for candidate in dispatched_candidates:
        _reconcile_call(client, candidate["call_id"])
        call_detail = _wait_for_terminal(client, candidate["call_id"])
        assert call_detail["call"]["transcript_status"] == "done"
        assert call_detail["call"]["outreach_summary"]
        # outreach calls never get a hiring scorecard
        assert call_detail["call"]["scorecard_status"] == "pending"

    final_detail = client.get(f"/api/outreach/campaigns/{campaign['id']}").json()
    final_candidates = {c["id"]: c for c in final_detail["candidates"]}
    settled_buckets = {final_candidates[c["id"]]["bucket"] for c in dispatched_candidates}
    assert settled_buckets <= {"Interested", "Not interested", "Follow-up required", "Contacted", "No response"}
    assert final_detail["funnel"]["total"] == len(candidates)

    overview = client.get("/api/outreach/overview").json()
    assert overview["total_candidates"] >= len(candidates)
    campaign_ids = [c["id"] for c in overview["campaigns"]]
    assert campaign["id"] in campaign_ids
