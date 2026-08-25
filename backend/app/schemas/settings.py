from pydantic import BaseModel


class VoiceProviderState(BaseModel):
    provider: str  # "mock" | "hunar" - the currently active provider
    hunar_configured: bool  # whether HUNAR_API_KEY looks like a real key, not the placeholder


class VoiceProviderUpdate(BaseModel):
    provider: str  # "mock" | "hunar"
