import json
import logging
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.integrations.llm import LLMError, generate_json
from app.integrations.people_search.base import SearchCriteria
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import Module
from app.models.sourced_candidate import SourcedCandidate
from app.providers.base import Agent, AgentSpec

logger = logging.getLogger("app.services.outreach")

_NON_TERMINAL_STATUSES = {"NOT_STARTED", "RINGING", "IN_PROGRESS"}
_NO_RESPONSE_STATUSES = {"FAILED", "CANCELLED", "NOT_CONNECTED"}

# The full set of buckets a candidate can be in, in funnel order - Sourced/Contacting are
# pre-terminal stages; the other five are the funnel the acceptance criteria describe.
FUNNEL_BUCKETS = [
    "Sourced",
    "Contacting",
    "No response",
    "Interested",
    "Not interested",
    "Follow-up required",
    "Contacted",
]

_SUMMARY_SYSTEM_PROMPT = (
    "You are a recruiting coordinator. In ONE or TWO short sentences, summarize the outcome of "
    "an AI outreach call to a candidate, based on its structured result and transcript. Respond "
    'with ONLY a single JSON object matching this exact shape: {"summary": string}'
)


# --- Campaign CRUD ---


def create_outreach_campaign(
    session: Session,
    *,
    title: str,
    job_description: str,
    criteria: SearchCriteria,
    agent_spec: AgentSpec,
    agent: Agent | None,
    agent_create_error: str | None,
) -> Campaign:
    campaign = Campaign(
        name=title,
        description=job_description,
        module=Module.outreach,
        agent_id=agent.id if agent else None,
        result_schema=agent_spec.result_schema,
        status="active",
        meta={
            "search_criteria": criteria.model_dump(),
            "agent_spec": agent_spec.model_dump(),
            "agent_autocreated": agent is not None,
            "agent_create_error": agent_create_error,
        },
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def list_outreach_campaigns(session: Session) -> list[Campaign]:
    stmt = select(Campaign).where(Campaign.module == Module.outreach).order_by(Campaign.created_at.desc())
    return list(session.exec(stmt).all())


def get_outreach_campaign(session: Session, campaign_id: UUID) -> Campaign | None:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.module != Module.outreach:
        return None
    return campaign


def update_campaign_criteria(session: Session, campaign: Campaign, criteria: SearchCriteria) -> Campaign:
    campaign.meta = {**campaign.meta, "search_criteria": criteria.model_dump()}
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def apply_agent_to_campaign(
    session: Session,
    campaign: Campaign,
    *,
    agent: Agent | None,
    agent_spec: AgentSpec | None = None,
    agent_create_error: str | None = None,
) -> Campaign:
    """Set (or override) a campaign's agent - used both for the real-mode fallback (HR picks
    an existing agent after autocreate failed) and for ?regenerate=true (a freshly designed
    spec, optionally auto-created again)."""
    meta = dict(campaign.meta)
    if agent_spec is not None:
        meta["agent_spec"] = agent_spec.model_dump()
    meta["agent_autocreated"] = agent is not None
    meta["agent_create_error"] = agent_create_error
    campaign.meta = meta

    if agent is not None:
        campaign.agent_id = agent.id
        campaign.result_schema = agent.result_schema
    elif agent_spec is not None:
        campaign.result_schema = agent_spec.result_schema

    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


# --- Funnel ---


def outreach_bucket(candidate: SourcedCandidate, call: Call | None) -> str:
    """Derive a candidate's funnel bucket from live Call state - never stored, always
    computed, so it can never drift out of sync with the call's actual status/result."""
    if candidate.call_id is None or call is None:
        return "Sourced"

    status = (call.status or "").upper()
    if status in _NO_RESPONSE_STATUSES:
        return "No response"
    if status != "COMPLETED":
        return "Contacting"

    if (call.engagement_status or "").upper() == "NOT_ENGAGED":
        return "No response"

    result = call.result or {}
    callback_requested = _truthy(result.get("callback_requested"))
    interested = _truthy(result.get("interested"))

    if callback_requested:
        return "Follow-up required"
    if interested is True:
        return "Interested"
    if interested is False:
        return "Not interested"
    return "Contacted"


def funnel_summary(session: Session, campaign: Campaign) -> dict[str, int]:
    """Counts per bucket plus "total" - computed in Python rather than a JSON SQL query,
    since candidate volume per campaign is small and this is far easier to read and debug."""
    candidates = list(session.exec(select(SourcedCandidate).where(SourcedCandidate.campaign_id == campaign.id)))
    call_ids = [c.call_id for c in candidates if c.call_id is not None]
    calls_by_id: dict[UUID, Call] = {}
    if call_ids:
        for call in session.exec(select(Call).where(Call.id.in_(call_ids))):
            calls_by_id[call.id] = call

    counts = dict.fromkeys(FUNNEL_BUCKETS, 0)
    for candidate in candidates:
        call = calls_by_id.get(candidate.call_id) if candidate.call_id else None
        bucket = outreach_bucket(candidate, call)
        counts[bucket] = counts.get(bucket, 0) + 1
    counts["total"] = len(candidates)
    return counts


# --- Post-call outreach summary (LLM) ---


def build_outreach_summary(call: Call, campaign: Campaign | None) -> str:
    """Generate a 1-2 line recap of an outreach call.

    Uses the real LLM provider when configured; always falls back to a deterministic summary
    built directly from the call's own result if that fails, or immediately if
    LLM_PROVIDER=mock - so this never needs a real key to demo the module end to end.
    """
    if settings.LLM_PROVIDER == "mock":
        return _mock_summary(call, campaign)
    try:
        raw = generate_json(_SUMMARY_SYSTEM_PROMPT, _build_summary_prompt(call, campaign))
        summary = str(raw.get("summary") or "").strip()
        return summary or _mock_summary(call, campaign)
    except LLMError:
        logger.exception("Outreach summary LLM call failed for call %s; falling back to mock summary", call.id)
        return _mock_summary(call, campaign)


def _build_summary_prompt(call: Call, campaign: Campaign | None) -> str:
    role_title = campaign.name if campaign else "the role"
    result = call.result or {}
    transcript = call.transcript or "(no transcript available)"
    return (
        f"Role: {role_title}\n\n"
        f"Structured call result:\n{json.dumps(result, indent=2)}\n\n"
        f"Transcript:\n{transcript}"
    )


def _mock_summary(call: Call, campaign: Campaign | None) -> str:
    role_title = campaign.name if campaign else "the role"
    result = call.result or {}
    interested = _truthy(result.get("interested"))
    callback = _truthy(result.get("callback_requested"))
    name = call.callee_name or "The candidate"

    if callback:
        return f"{name} asked for a follow-up call about {role_title}; not yet a firm yes or no."
    if interested is True:
        ctc_note = f" (expects {result.get('expected_ctc')})" if result.get("expected_ctc") else ""
        return f"{name} is interested in {role_title}{ctc_note} and open to next steps."
    if interested is False:
        return f"{name} is not interested in {role_title} at this time."
    return f"{name} completed the outreach call about {role_title}; outcome was inconclusive."


def _truthy(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "y", "interested"):
            return True
        if low in ("false", "no", "n", "not interested"):
            return False
    return None
