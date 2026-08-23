import httpx

from app.core.config import settings
from app.providers.base import Agent, Call, CallResult, VoiceProvider


class HunarProvider(VoiceProvider):
    """Real Hunar voice API client.

    Not implemented in Phase 1 - this phase only proves the provider
    abstraction and wiring via MockProvider. Real HTTP calls land in Phase 2.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.HUNAR_BASE_URL,
            headers={"Authorization": f"Bearer {settings.HUNAR_API_KEY}"},
            timeout=30.0,
        )

    def list_agents(self) -> list[Agent]:
        raise NotImplementedError("TODO(phase2): call GET /agents on the Hunar API")

    def get_agent(self, agent_id: str) -> Agent:
        raise NotImplementedError("TODO(phase2): call GET /agents/{id} on the Hunar API")

    def create_call(self, agent_id: str, phone_number: str) -> Call:
        raise NotImplementedError("TODO(phase2): call POST /calls on the Hunar API")

    def get_call(self, call_id: str) -> Call:
        raise NotImplementedError("TODO(phase2): call GET /calls/{id} on the Hunar API")

    def get_call_result(self, call_id: str) -> CallResult:
        raise NotImplementedError("TODO(phase2): call GET /calls/{id}/result on the Hunar API")
