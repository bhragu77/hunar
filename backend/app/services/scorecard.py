import json
import logging
from typing import Any

from app.core.config import settings
from app.integrations.llm import LLMError, generate_json
from app.models.call import Call
from app.models.campaign import Campaign

logger = logging.getLogger("app.services.scorecard")

_VALID_RECOMMENDATIONS = {"advance", "hold", "reject"}

_SYSTEM_PROMPT = (
    "You are an experienced technical recruiter producing a structured screening scorecard "
    "for a candidate's AI-conducted phone interview. Be fair, specific, and evidence-based - "
    "ground every claim in the interview result or transcript given to you. "
    'Respond with ONLY a single JSON object matching this exact shape: {"recommendation": '
    '"advance"|"hold"|"reject", "overall_score": 0-100, "summary": string, "strengths": '
    'string[], "concerns": string[], "competencies": [{"name": string, "score": 0-100, '
    '"notes": string}], "suggested_followups": string[], "red_flags": string[]}'
)


def build_scorecard(call: Call, campaign: Campaign | None) -> dict[str, Any]:
    """Generate a structured scorecard for one completed call.

    Uses the real LLM provider when configured (LLM_PROVIDER=anthropic|openai); always
    falls back to a deterministic scorecard derived directly from the call's own Hunar
    result if that fails, or immediately if LLM_PROVIDER=mock. This never crashes the
    post-call pipeline and never needs a real key to demo the module end to end.
    """
    if settings.LLM_PROVIDER == "mock":
        return _mock_scorecard(call, campaign)

    user_prompt = _build_user_prompt(call, campaign)
    try:
        raw = generate_json(_SYSTEM_PROMPT, user_prompt)
        return _normalize(raw)
    except LLMError:
        logger.exception("Scorecard LLM call failed for call %s; falling back to mock scorecard", call.id)
        return _mock_scorecard(call, campaign)


def _build_user_prompt(call: Call, campaign: Campaign | None) -> str:
    role_title = campaign.name if campaign else "Unknown role"
    criteria = campaign.description if campaign and campaign.description else "No specific criteria provided."
    result = call.result or {}
    transcript = call.transcript or "(no transcript available)"
    return (
        f"Role: {role_title}\n\n"
        f"Evaluation criteria / job description:\n{criteria}\n\n"
        f"Structured call result from the interview:\n{json.dumps(result, indent=2)}\n\n"
        f"Interview transcript:\n{transcript}"
    )


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a real LLM's response into the exact scorecard shape, leniently - values may
    come back as strings where numbers are expected, keys may be missing entirely."""

    def _score(value: Any, default: int = 50) -> int:
        try:
            return max(0, min(100, round(float(value))))
        except (TypeError, ValueError):
            return default

    def _str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if value:
            return [str(value)]
        return []

    recommendation = str(raw.get("recommendation", "hold")).lower()
    if recommendation not in _VALID_RECOMMENDATIONS:
        recommendation = "hold"

    competencies = []
    for item in raw.get("competencies") or []:
        if isinstance(item, dict):
            competencies.append(
                {
                    "name": str(item.get("name", "General")),
                    "score": _score(item.get("score")),
                    "notes": str(item.get("notes", "")),
                }
            )

    return {
        "recommendation": recommendation,
        "overall_score": _score(raw.get("overall_score")),
        "summary": str(raw.get("summary", "")),
        "strengths": _str_list(raw.get("strengths")),
        "concerns": _str_list(raw.get("concerns")),
        "competencies": competencies,
        "suggested_followups": _str_list(raw.get("suggested_followups")),
        "red_flags": _str_list(raw.get("red_flags")),
    }


def _mock_scorecard(call: Call, campaign: Campaign | None) -> dict[str, Any]:
    """Deterministic, plausible scorecard derived from the call's own Hunar result. No
    network - this is what makes the whole module demoable with zero external keys.
    """
    result = call.result or {}
    role_title = campaign.name if campaign else "the role"

    interested = _truthy(result.get("interested"))
    reachable = _truthy(result.get("reachable"))
    if reachable is None:
        reachable = True  # most result schemas don't have this field; assume reachable if we got a result at all
    negative_signal = result.get("interest_level") in ("not interested", "no") or _truthy(
        result.get("declined") or result.get("not_interested")
    )

    if not reachable:
        recommendation, overall_score = "hold", 40
        summary = f"Candidate for {role_title} was not reliably reachable during the call."
    elif negative_signal or interested is False:
        recommendation, overall_score = "reject", 30
        summary = f"Candidate for {role_title} indicated they are not interested or not a fit."
    elif interested is True:
        recommendation, overall_score = "advance", 78
        summary = f"Candidate for {role_title} engaged well and expressed genuine interest."
    else:
        recommendation, overall_score = "hold", 55
        summary = f"Call with the candidate for {role_title} completed; interest level was unclear from the result."

    return {
        "recommendation": recommendation,
        "overall_score": overall_score,
        "summary": summary,
        "strengths": ["Answered the call and engaged with the agent"] if reachable else [],
        "concerns": [] if recommendation == "advance" else ["Limited signal on genuine interest from this call alone"],
        "competencies": [
            {
                "name": "Communication",
                "score": 70 if reachable else 30,
                "notes": "Derived from call engagement (LLM_PROVIDER=mock, not a real assessment).",
            },
            {
                "name": "Role fit",
                "score": overall_score,
                "notes": "Derived from Hunar's structured call result (LLM_PROVIDER=mock, not a real assessment).",
            },
        ],
        "suggested_followups": (
            ["Schedule a live technical round"]
            if recommendation == "advance"
            else (["Reconnect later if timing improves"] if recommendation == "hold" else [])
        ),
        "red_flags": [],
    }


def _truthy(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "y"):
            return True
        if low in ("false", "no", "n"):
            return False
    return None
