import logging
import time
from typing import Any

import httpx

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

logger = logging.getLogger("app.providers.hunar")

_RETRYABLE_STATUSES = {500, 502, 503, 504}
_MAX_RETRIES = 2
_BACKOFF_SECONDS = 0.5


class HunarProvider(VoiceProvider):
    """Real Hunar voice API client.

    Field names and endpoint paths follow Hunar's documented conventions as best we know
    them; this is the one seam in the codebase not exercised by an automated test, since it
    needs a live key. See README for the manual verification steps.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.HUNAR_BASE_URL,
            headers={"X-API-Key": settings.HUNAR_API_KEY},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

    def list_agents(self) -> list[Agent]:
        data = self._request("GET", "/agents").json()
        return [Agent(**item) for item in data]

    def get_agent(self, agent_id: str) -> Agent:
        data = self._request("GET", f"/agents/{agent_id}").json()
        return Agent(**data)

    def create_agent(self, spec: AgentSpec) -> Agent:
        data = self._request("POST", "/agents", json=spec.model_dump()).json()
        return Agent(**data)

    def list_numbers(self) -> list[PhoneNumber]:
        data = self._request("GET", "/phone-numbers").json()
        return [PhoneNumber(**item) for item in data]

    def create_call(self, req: CreateCallRequest) -> ProviderCall:
        body: dict[str, Any] = {
            "agent_id": req.agent_id,
            "callee_name": req.callee_name,
            "mobile_number": req.mobile_number,
            "custom_data": req.custom_data,
            "request_id": req.request_id,
        }
        callback_config = _callback_config()
        if callback_config:
            body["callback_config"] = callback_config
        data = self._request("POST", "/calls", json=body).json()
        return _provider_call_from_payload(data)

    def create_bulk_calls(self, agent_id: str, items: list[CreateCallRequest]) -> list[ProviderCall]:
        body: dict[str, Any] = {
            "agent_id": agent_id,
            "calls": [
                {
                    "callee_name": item.callee_name,
                    "mobile_number": item.mobile_number,
                    "custom_data": item.custom_data,
                    "request_id": item.request_id,
                }
                for item in items
            ],
        }
        callback_config = _callback_config()
        if callback_config:
            body["callback_config"] = callback_config
        data = self._request("POST", "/calls/bulk", json=body).json()
        return [_provider_call_from_payload(item) for item in data]

    def get_call(self, provider_call_id: str) -> ProviderCall:
        data = self._request("GET", f"/calls/{provider_call_id}").json()
        return _provider_call_from_payload(data)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Small retry/backoff on network errors and 5xx only - never on 4xx, those are
        genuine client errors and retrying won't help."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS * (attempt + 1))
                    continue
                raise ProviderError(f"Network error calling Hunar API: {exc}") from exc

            if response.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
                continue

            _raise_for_status(response)
            return response

        raise ProviderError(f"Hunar API request failed after retries: {last_exc}")


def _callback_config() -> dict[str, str] | None:
    """Only attach callback URLs when we have a public base to receive them at - there's no
    point asking Hunar to call back http://localhost."""
    if not settings.PUBLIC_BASE_URL:
        return None
    webhook_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/webhooks/hunar"
    return {
        "call_status_updated_url": webhook_url,
        "call_recording_done_url": webhook_url,
        "call_result_done_url": webhook_url,
        "call_summary_url": webhook_url,
    }


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = _safe_detail(response)
    status = response.status_code
    if status == 401:
        raise ProviderError("Hunar rejected the API key (401 Unauthorized).", status_code=401)
    if status == 402:
        raise ProviderError("Hunar account is out of minutes or the subscription lapsed (402).", status_code=402)
    if status == 400:
        raise ProviderError(f"Hunar rejected the request (400): {detail}", status_code=400)
    if status == 422:
        raise ProviderError(f"Hunar validation error (422): {detail}", status_code=422)
    raise ProviderError(f"Unexpected Hunar API response ({status}): {detail}", status_code=status)


def _safe_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("detail") or body.get("message") or body)
        return str(body)
    except ValueError:
        return response.text[:300]


def _provider_call_from_payload(data: dict[str, Any]) -> ProviderCall:
    return ProviderCall(
        provider_call_id=data.get("call_id") or data.get("id") or data["provider_call_id"],
        request_id=data.get("request_id"),
        status=data.get("status", "UNKNOWN"),
        lifecycle_status=data.get("lifecycle_status"),
        engagement_status=data.get("engagement_status"),
        answered_by=data.get("answered_by"),
        call_ended_by=data.get("call_ended_by"),
        recording_url=data.get("recording_url"),
        result=data.get("result"),
        duration_seconds=data.get("duration_seconds"),
        started_at=data.get("started_at"),
        ended_at=data.get("ended_at"),
    )
