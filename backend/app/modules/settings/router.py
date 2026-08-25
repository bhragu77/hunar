from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.runtime_state import get_voice_provider_name, set_voice_provider_name
from app.schemas.settings import VoiceProviderState, VoiceProviderUpdate

# Runtime-togglable app settings - currently just the voice provider. GET is open (just
# reveals which mode is active, not a secret). POST requires INTERNAL_API_TOKEN - see
# settings.INTERNAL_API_TOKEN's docstring: only the frontend's own server-side route
# (frontend/app/api/voice-provider/route.ts) knows it, and that route is what actually
# rejects guests (checks the NextAuth session before ever forwarding the request here).
router = APIRouter(prefix="/settings", tags=["settings"])

_VALID_PROVIDERS = {"mock", "hunar"}


def _hunar_configured() -> bool:
    return bool(settings.HUNAR_API_KEY) and settings.HUNAR_API_KEY != "replace-me"


@router.get("/voice-provider", response_model=VoiceProviderState)
def get_voice_provider_state() -> VoiceProviderState:
    return VoiceProviderState(provider=get_voice_provider_name(), hunar_configured=_hunar_configured())


@router.post("/voice-provider", response_model=VoiceProviderState)
def set_voice_provider_state(
    req: VoiceProviderUpdate,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> VoiceProviderState:
    if x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(status_code=403, detail="Not authorized to change the voice provider")
    if req.provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"provider must be one of {sorted(_VALID_PROVIDERS)}")
    if req.provider == "hunar" and not _hunar_configured():
        raise HTTPException(status_code=422, detail="HUNAR_API_KEY is not configured on this backend")
    set_voice_provider_name(req.provider)
    return VoiceProviderState(provider=get_voice_provider_name(), hunar_configured=_hunar_configured())
