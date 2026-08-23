from fastapi import APIRouter

from app.providers.base import Agent
from app.providers.factory import get_voice_provider

router = APIRouter(prefix="/agents", tags=["hiring"])


@router.get("", response_model=list[Agent])
def list_agents() -> list[Agent]:
    """Return the configured voice provider's agents. Proves provider wiring end-to-end."""
    provider = get_voice_provider()
    return provider.list_agents()
