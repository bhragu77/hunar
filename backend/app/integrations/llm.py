import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.integrations.llm")

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(Exception):
    """Raised when a real LLM provider call fails: network, auth, or an unparseable
    response. Callers decide what a sane fallback looks like for their own use case - see
    app/services/scorecard.py, which falls back to a deterministic mock scorecard."""


def generate_json(system: str, user: str) -> dict[str, Any]:
    """Ask the configured real LLM provider (anthropic or openai) for a JSON object and
    parse it: instructs JSON-only output, strips a markdown code fence if the model wraps
    its answer in one anyway, and parses leniently.

    Only handles the two real providers. LLM_PROVIDER=mock never calls this - the mock
    scorecard is built directly in app/services/scorecard.py from the call's own data,
    since a genuinely useful mock response needs the structured Call/Campaign objects, not
    just two prompt strings.
    """
    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        raw = _call_anthropic(system, user)
    elif provider == "openai":
        raw = _call_openai(system, user)
    else:
        raise LLMError(
            f"generate_json doesn't handle LLM_PROVIDER={provider!r} - only 'anthropic' and 'openai' make real calls."
        )
    return _parse_json(raw)


def _call_anthropic(system: str, user: str) -> str:
    model = settings.LLM_MODEL or _DEFAULT_ANTHROPIC_MODEL
    try:
        response = httpx.post(
            _ANTHROPIC_URL,
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2000,
                "system": system + "\n\nRespond with ONLY a single valid JSON object - no markdown, no commentary.",
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"Anthropic API call failed: {exc}") from exc

    data = response.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(system: str, user: str) -> str:
    model = settings.LLM_MODEL or _DEFAULT_OPENAI_MODEL
    try:
        response = httpx.post(
            _OPENAI_URL,
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI API call failed: {exc}") from exc

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected OpenAI response shape: {data}") from exc


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"LLM response was valid JSON but not an object ({type(parsed).__name__})")
    return parsed
