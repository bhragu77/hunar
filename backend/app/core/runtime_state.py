import threading

from app.core.config import settings

# The active VoiceProvider choice, mutable at runtime via POST /api/settings/voice-provider.
# settings.VOICE_PROVIDER remains the *startup* default (and what a fresh process boots with);
# this is what actually decides which provider dispatch/poll/webhook code sees from then on.
# Deliberately process-global, not per-request or per-user: there's no auth on the backend
# itself (see README's Security section), so this is a single shared toggle for the whole
# deployment, not a per-session preference. Good enough for a single-reviewer demo; a real
# multi-tenant version would need this to be per-account state in the database instead.
_lock = threading.Lock()
_current_voice_provider = settings.VOICE_PROVIDER


def get_voice_provider_name() -> str:
    with _lock:
        return _current_voice_provider


def set_voice_provider_name(name: str) -> None:
    global _current_voice_provider
    with _lock:
        _current_voice_provider = name
