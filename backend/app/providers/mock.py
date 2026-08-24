import json
import logging
import random
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.providers.base import (
    Agent,
    AgentSpec,
    CreateCallRequest,
    PhoneNumber,
    ProviderCall,
    ProviderError,
    VoiceProvider,
)
from app.providers.webhooks import compute_hunar_signature

logger = logging.getLogger("app.providers.mock")

_MOCK_AGENTS: list[Agent] = [
    Agent(
        id="agent_mock_001",
        name="Recruiting Screener",
        voice_persona="friendly_professional",
        language="en-US",
        custom_variables={"role_title": "string", "min_experience_years": "number"},
        result_schema={"interested": "boolean", "years_experience": "number", "notes": "string"},
    ),
    Agent(
        id="agent_mock_002",
        name="Interview Scheduler",
        voice_persona="warm_efficient",
        language="en-US",
        custom_variables={"candidate_name": "string", "available_slots": "string"},
        result_schema={"slot_confirmed": "string", "reschedule_requested": "boolean"},
    ),
    Agent(
        id="agent_mock_003",
        name="Attendance Confirmation",
        voice_persona="neutral_concise",
        language="en-IN",
        custom_variables={"interview_date": "string", "interviewer_name": "string"},
        result_schema={"will_attend": "boolean", "cancellation_reason": "string"},
    ),
]

_MOCK_NUMBERS: list[PhoneNumber] = [
    PhoneNumber(id="number_mock_1", phone_number="+15550001111", label="Mock Line 1"),
    PhoneNumber(id="number_mock_2", phone_number="+15550002222", label="Mock Line 2"),
]


class MockProvider(VoiceProvider):
    """Simulates the Hunar voice API end-to-end so the whole pipeline is exercisable with no
    live key, no phone, and no ngrok.

    Every created call progresses through a realistic status lifecycle in the background
    (via the shared APScheduler instance): NOT_STARTED -> RINGING -> IN_PROGRESS -> COMPLETED.
    This provider keeps its OWN independent state per call (self._calls), separate from our
    app's Call table - exactly like a real remote provider would. That's what lets the polling
    fallback work even when the completion webhook never arrives: get_call() always reflects
    this provider's ground truth regardless of whether our webhook receiver ever heard from it.

    Intermediate transitions (RINGING, IN_PROGRESS) are pushed straight into our own DB via
    apply_call_update(source=mock) - a direct in-process call, not a real HTTP round trip -
    just to keep the Call Console feeling alive. Only the terminal COMPLETED transition goes
    out as a real, signed HTTP webhook POST back to this same backend, which is what actually
    exercises the signature-verified webhook path.
    """

    def __init__(self, scheduler: BackgroundScheduler) -> None:
        self._scheduler = scheduler
        self._lock = threading.Lock()
        self._calls: dict[str, ProviderCall] = {}
        # Seeded from the module-level defaults, then grown by create_agent - e.g. Module 2's
        # auto-created outreach agents. Per-instance so each MockProvider() (each test, each
        # process) starts clean instead of leaking agents across instances via a shared list.
        self._agents: list[Agent] = list(_MOCK_AGENTS)

    def list_agents(self) -> list[Agent]:
        with self._lock:
            return list(self._agents)

    def get_agent(self, agent_id: str) -> Agent:
        with self._lock:
            for agent in self._agents:
                if agent.id == agent_id:
                    return agent
        raise ProviderError(f"Unknown mock agent id: {agent_id}", status_code=404)

    def create_agent(self, spec: AgentSpec) -> Agent:
        agent = Agent(
            id=f"agent_mock_{uuid.uuid4().hex[:12]}",
            name=spec.name,
            voice_persona=spec.voice_persona,
            language=spec.language,
            custom_variables=spec.custom_variables,
            result_schema=spec.result_schema,
        )
        with self._lock:
            self._agents.append(agent)
        return agent

    def list_numbers(self) -> list[PhoneNumber]:
        return list(_MOCK_NUMBERS)

    def create_call(self, req: CreateCallRequest) -> ProviderCall:
        agent = self.get_agent(req.agent_id)
        provider_call_id = f"call_mock_{uuid.uuid4().hex[:12]}"
        provider_call = ProviderCall(
            provider_call_id=provider_call_id,
            request_id=req.request_id,
            status="NOT_STARTED",
            lifecycle_status="NOT_STARTED",
        )
        with self._lock:
            self._calls[provider_call_id] = provider_call

        self._scheduler.add_job(
            self._simulate_call,
            trigger="date",
            args=[provider_call_id, agent],
            id=f"mock-simulate-{provider_call_id}",
            misfire_grace_time=None,
        )
        return provider_call

    def create_bulk_calls(self, agent_id: str, items: list[CreateCallRequest]) -> list[ProviderCall]:
        return [self.create_call(item) for item in items]

    def get_call(self, provider_call_id: str) -> ProviderCall:
        with self._lock:
            call = self._calls.get(provider_call_id)
        if call is None:
            raise ProviderError(f"Unknown mock call id: {provider_call_id}", status_code=404)
        return call

    # --- internal simulation, runs on a scheduler worker thread ---

    def _set_state(self, provider_call_id: str, **fields: object) -> ProviderCall:
        with self._lock:
            current = self._calls[provider_call_id]
            updated = current.model_copy(update=fields)
            self._calls[provider_call_id] = updated
        return updated

    def _simulate_call(self, provider_call_id: str, agent: Agent) -> None:
        try:
            total = max(settings.MOCK_CALL_DURATION_SECONDS, 1)
            started_at = datetime.now(timezone.utc)

            time.sleep(total * 0.25)
            self._set_state(provider_call_id, status="RINGING", lifecycle_status="RINGING")
            self._push_intermediate_update(provider_call_id)

            time.sleep(total * 0.5)
            self._set_state(
                provider_call_id,
                status="IN_PROGRESS",
                lifecycle_status="IN_PROGRESS",
                started_at=started_at,
            )
            self._push_intermediate_update(provider_call_id)

            time.sleep(total * 0.25)
            ended_at = datetime.now(timezone.utc)
            duration_seconds = int((ended_at - started_at).total_seconds())
            completed = self._set_state(
                provider_call_id,
                status="COMPLETED",
                lifecycle_status="COMPLETED",
                engagement_status="ENGAGED",
                answered_by="HUMAN",
                call_ended_by="AGENT",
                recording_url=f"https://mock-recordings.hunar.local/{provider_call_id}.mp3",
                result=_fake_result(agent, provider_call_id),
                duration_seconds=duration_seconds,
                started_at=started_at,
                ended_at=ended_at,
            )
            self._send_webhook(completed, event_type="call_summary")
        except Exception:
            logger.exception("Mock call simulation failed for %s", provider_call_id)

    def _push_intermediate_update(self, provider_call_id: str) -> None:
        # Imported here to avoid a module-level cycle: services.calls -> providers.base is
        # fine, but providers.mock -> services.calls must stay a lazy, call-time import.
        from sqlmodel import Session

        from app.core.db import engine
        from app.models.enums import CallEventSource
        from app.services.calls import apply_call_update, provider_call_to_update

        provider_call = self.get_call(provider_call_id)
        update = provider_call_to_update(provider_call, event_type=f"provider_{provider_call.status.lower()}")
        with Session(engine) as session:
            apply_call_update(session, update, source=CallEventSource.mock)

    def _send_webhook(self, call: ProviderCall, *, event_type: str) -> None:
        payload = {
            "event_type": event_type,
            "call_id": call.provider_call_id,
            "request_id": call.request_id,
            "status": call.status,
            "lifecycle_status": call.lifecycle_status,
            "engagement_status": call.engagement_status,
            "answered_by": call.answered_by,
            "call_ended_by": call.call_ended_by,
            "recording_url": call.recording_url,
            "result": call.result,
            "duration_seconds": call.duration_seconds,
            "started_at": call.started_at.isoformat() if call.started_at else None,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        }
        raw_body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        signature = compute_hunar_signature(settings.MOCK_WEBHOOK_SECRET, timestamp, raw_body)
        url = f"{settings.INTERNAL_BASE_URL.rstrip('/')}/api/webhooks/hunar"
        try:
            response = httpx.post(
                url,
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hunar-Signature": signature,
                    "X-Hunar-Timestamp": timestamp,
                },
                timeout=5.0,
            )
            if response.is_success:
                logger.info("Mock webhook delivered for %s (%s)", call.provider_call_id, event_type)
            else:
                logger.warning(
                    "Mock webhook POST to %s returned %s; the poller will pick this call up instead.",
                    url,
                    response.status_code,
                )
        except httpx.HTTPError:
            logger.warning(
                "Mock webhook POST to %s failed; the poller will pick this call up instead.", url
            )


_STRING_SAMPLES: dict[str, list[str]] = {
    "current_ctc": ["6 LPA", "9 LPA", "12 LPA", "18 LPA"],
    "expected_ctc": ["8 LPA", "12 LPA", "16 LPA", "22 LPA"],
    "notice_period": ["Immediate", "15 days", "30 days", "60 days"],
    "relevant_experience": ["2 years", "3 years", "5 years", "7 years"],
}


def _fake_result(agent: Agent, provider_call_id: str) -> dict[str, object]:
    """Generate a believable result matching the agent's declared result_schema.

    Seeded by provider_call_id so each simulated call gets a stable-but-varied outcome
    (rather than every call being identically "interested") - this is what lets a mock
    outreach campaign's funnel actually populate across multiple buckets for a demo.
    """
    rng = random.Random(provider_call_id)
    result: dict[str, object] = {}
    for key, kind in agent.result_schema.items():
        if kind == "boolean":
            result[key] = rng.random() < 0.6
        elif kind == "number":
            result[key] = rng.randint(1, 8)
        elif key in _STRING_SAMPLES:
            result[key] = rng.choice(_STRING_SAMPLES[key])
        else:
            result[key] = f"Mock {key.replace('_', ' ')}"
    return result
