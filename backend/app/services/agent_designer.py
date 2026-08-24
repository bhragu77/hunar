import logging
from typing import Any

from app.core.config import settings
from app.integrations.llm import LLMError, generate_json
from app.providers.base import AgentSpec

logger = logging.getLogger("app.services.agent_designer")

# The recruitment-outreach result shape every outreach agent is designed to fill in. Type
# hints ("boolean"/"number"/string-default) match the convention app/providers/mock.py's
# _fake_result already understands, so a mock-mode dispatch produces a plausible, VARIED
# result without any extra wiring.
RESULT_SCHEMA: dict[str, str] = {
    "interested": "boolean",
    "current_ctc": "string",
    "expected_ctc": "string",
    "notice_period": "string",
    "relevant_experience": "string",
    "open_to_interview": "boolean",
    "callback_requested": "boolean",
}

_SYSTEM_PROMPT = (
    "You design a purpose-built AI voice outreach agent for recruiting. Given a role title and "
    "job description, produce an agent configuration for calling sourced candidates. Respond "
    'with ONLY a single JSON object matching this exact shape: {"name": string, '
    '"language": string, "voice_persona": string, "persona_name": string, "agent_prompt": '
    'string, "objective": string, "introduction": string, "result_prompt": string}'
)

_DEFAULT_PERSONA_NAME = "Aria"


def design_outreach_agent(job_description: str, title: str) -> AgentSpec:
    """Design a purpose-built outreach voice agent from a job description.

    Uses the real LLM provider when configured; always falls back to a sensible template
    spec if that fails, or immediately if LLM_PROVIDER=mock - so the agent auto-creation step
    never needs a real key to demo end to end.
    """
    if settings.LLM_PROVIDER == "mock":
        return _mock_design(job_description, title)
    try:
        user_prompt = f"Role: {title}\n\nJob description:\n{job_description}"
        raw = generate_json(_SYSTEM_PROMPT, user_prompt)
        return _normalize(raw, title)
    except LLMError:
        logger.exception("Agent design LLM call failed; falling back to template agent")
        return _mock_design(job_description, title)


def _mock_design(job_description: str, title: str) -> AgentSpec:
    persona_name = _DEFAULT_PERSONA_NAME
    first_line = next((line.strip() for line in (job_description or "").splitlines() if line.strip()), "")
    highlight = first_line[:160] if first_line else f"an exciting {title} opportunity"

    return AgentSpec(
        name=f"{title} Outreach Agent"[:80],
        language="en-IN",
        voice_persona="warm_consultative",
        persona_name=persona_name,
        objective=(
            f"Reach out to candidates about the {title} role, gauge genuine interest, and "
            "collect current CTC, expected CTC, notice period, and relevant experience - "
            "without ever sounding scripted."
        ),
        introduction=(
            f"Hi, this is {persona_name} calling on behalf of the hiring team about {highlight}. "
            "Do you have a couple of minutes to talk?"
        ),
        agent_prompt=(
            f"You are {persona_name}, a warm and professional recruiting outreach agent calling "
            f"candidates about the {title} role. Job context:\n{job_description}\n\n"
            "Confirm you're speaking with the right person, briefly introduce the opportunity, "
            "and gauge interest. If they're interested or undecided, collect their current CTC, "
            "expected CTC, notice period, and relevant experience. If they ask for a callback "
            "instead, note that explicitly. Be concise, respectful of their time, and never pushy."
        ),
        result_prompt=(
            "Summarize the call: whether the candidate is interested, their current CTC, "
            "expected CTC, notice period, relevant experience, whether they're open to an "
            "interview, and whether they asked for a callback."
        ),
        custom_variables={"role_title": "string"},
        result_schema=dict(RESULT_SCHEMA),
    )


def _normalize(raw: dict[str, Any], title: str) -> AgentSpec:
    return AgentSpec(
        name=str(raw.get("name") or f"{title} Outreach Agent")[:80],
        language=str(raw.get("language") or "en-IN"),
        voice_persona=str(raw.get("voice_persona") or "warm_consultative"),
        persona_name=str(raw.get("persona_name") or _DEFAULT_PERSONA_NAME),
        agent_prompt=str(raw.get("agent_prompt") or ""),
        objective=str(raw.get("objective") or ""),
        introduction=str(raw.get("introduction") or ""),
        result_prompt=str(raw.get("result_prompt") or ""),
        custom_variables={"role_title": "string"},
        result_schema=dict(RESULT_SCHEMA),
    )
