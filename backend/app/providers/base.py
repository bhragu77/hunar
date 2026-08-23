from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class Agent(BaseModel):
    """A configured voice agent, shaped like Hunar's real agent schema."""

    id: str
    name: str
    voice_persona: str
    language: str
    custom_variables: dict[str, Any] = {}
    result_schema: dict[str, Any] = {}


class Call(BaseModel):
    """A single outbound/inbound call placed through a voice provider."""

    id: str
    agent_id: str
    phone_number: str
    status: str  # e.g. "queued" | "in_progress" | "completed" | "failed"


class CallResult(BaseModel):
    """The structured outcome of a completed call."""

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
    def create_call(self, agent_id: str, phone_number: str) -> Call: ...

    @abstractmethod
    def get_call(self, call_id: str) -> Call: ...

    @abstractmethod
    def get_call_result(self, call_id: str) -> CallResult: ...
