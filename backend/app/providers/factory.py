from functools import lru_cache

from app.core.runtime_state import get_voice_provider_name
from app.core.scheduler import scheduler
from app.providers.base import VoiceProvider
from app.providers.hunar import HunarProvider
from app.providers.mock import MockProvider


@lru_cache
def _mock_provider() -> MockProvider:
    return MockProvider(scheduler)


@lru_cache
def _hunar_provider() -> HunarProvider:
    return HunarProvider()


def clear_provider_cache() -> None:
    """Test-only: drop cached provider singletons (e.g. after monkeypatching one, or between
    tests that must each get a fresh MockProvider instance)."""
    _mock_provider.cache_clear()
    _hunar_provider.cache_clear()


def get_voice_provider() -> VoiceProvider:
    """Return the currently active VoiceProvider singleton.

    Which one is "active" is app.core.runtime_state's mutable current choice (defaults to
    settings.VOICE_PROVIDER at startup, changeable live via POST /api/settings/voice-provider)
    - not a per-call decision, so the poller and webhook paths always agree with whatever the
    UI's Mock/Real toggle currently shows.

    Each concrete provider is still its own singleton (cached), never rebuilt per call:
    MockProvider holds in-memory per-call state that must stay the same instance across
    requests, the poller, and background simulation jobs.
    """
    name = get_voice_provider_name()
    if name == "hunar":
        return _hunar_provider()
    if name == "mock":
        return _mock_provider()
    raise ValueError(f"Unknown voice provider: {name!r}")
