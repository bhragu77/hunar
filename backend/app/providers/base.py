from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProviderError(Exception):
    """Raised when a VoiceProvider call fails in a way the caller should handle explicitly
    (bad key, no minutes left, telephony rejection, validation error, ...)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class Agent(BaseModel):
    """A configured voice agent.

    `custom_variables` tolerates both shapes seen in practice: MockProvider's fake agents use
    a dict of {variable_name: type_hint}; the real Hunar API returns a plain list of variable
    names with no type info (e.g. ["location", "company", "job_role"]).
    """

    id: str
    name: str
    voice_persona: str
    language: str
    custom_variables: dict[str, Any] | list[str] = {}
    result_schema: dict[str, Any] = {}


class AgentSpec(BaseModel):
    """Input for create_agent - matches Hunar's real create-agent payload shape. The
    persona/prompt fields default to empty so voice-module callers that only care about
    name/voice_persona/language/result_schema (this phase's routes) don't need to supply
    them; app/services/agent_designer.py (Module 2) fills them in from a job description."""

    name: str
    voice_persona: str
    language: str
    persona_name: str = ""
    agent_prompt: str = ""
    objective: str = ""
    introduction: str = ""
    result_prompt: str = ""
    custom_variables: dict[str, Any] = {}
    result_schema: dict[str, Any] = {}


class PhoneNumber(BaseModel):
    id: str
    phone_number: str
    label: str | None = None


class CreateCallRequest(BaseModel):
    """What we ask a provider to dispatch. `request_id` is OUR correlation id - the provider
    is expected to echo it back so we can locate the Call row even before we know its
    provider_call_id."""

    agent_id: str
    callee_name: str
    mobile_number: str
    custom_data: dict[str, Any] = {}
    request_id: str


class ProviderCall(BaseModel):
    """A voice provider's current view of one call - the shape shared by create_call,
    get_call, webhook payloads, and the poller, so all three converge on the same fields."""

    provider_call_id: str
    request_id: str | None = None
    status: str
    lifecycle_status: str | None = None
    engagement_status: str | None = None
    answered_by: str | None = None
    call_ended_by: str | None = None
    recording_url: str | None = None
    result: dict[str, Any] | None = None
    duration_seconds: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class CallResult(BaseModel):
    """A call's structured outcome. `transcript` is a SEAM for a later ASR phase - unused
    for now but part of the shared shape."""

    call_id: str
    transcript: str | None = None
    structured_data: dict[str, Any] = {}


class VoiceProvider(ABC):
    """Common interface every voice provider (mock, Hunar, ...) must implement."""

    @abstractmethod
    def list_agents(self) -> list[Agent]: ...

    @abstractmethod
    def get_agent(self, agent_id: str) -> Agent: ...

    @abstractmethod
    def create_agent(self, spec: AgentSpec) -> Agent: ...

    @abstractmethod
    def list_numbers(self) -> list[PhoneNumber]: ...

    @abstractmethod
    def create_call(self, req: CreateCallRequest) -> ProviderCall: ...

    @abstractmethod
    def create_bulk_calls(self, agent_id: str, items: list[CreateCallRequest]) -> list[ProviderCall]: ...

    @abstractmethod
    def get_call(self, provider_call_id: str) -> ProviderCall: ...
