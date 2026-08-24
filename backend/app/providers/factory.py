from functools import lru_cache

from app.core.config import settings
from app.core.scheduler import scheduler
from app.providers.base import VoiceProvider
from app.providers.hunar import HunarProvider
from app.providers.mock import MockProvider


@lru_cache
def get_voice_provider() -> VoiceProvider:
    """Return the configured VoiceProvider singleton, chosen by settings.VOICE_PROVIDER.

    Cached deliberately: MockProvider holds in-memory per-call state that must stay the same
    instance across requests, the poller, and background simulation jobs.
    """
    if settings.VOICE_PROVIDER == "hunar":
        return HunarProvider()
    if settings.VOICE_PROVIDER == "mock":
        return MockProvider(scheduler)
    raise ValueError(f"Unknown VOICE_PROVIDER: {settings.VOICE_PROVIDER!r}")
