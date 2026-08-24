import logging

import httpx

from app.core.config import settings
from app.models.call import Call

logger = logging.getLogger("app.integrations.transcription")


class TranscriptionError(Exception):
    """Raised for a genuine transcription failure (network, bad response) - not raised for
    "nothing to transcribe" cases, which just return None."""


def transcribe(call: Call) -> str | None:
    """Return a transcript for this call, or None if transcription is disabled or there's
    nothing to transcribe. Raises TranscriptionError only for real failures - the caller
    (app/services/post_call.py) records that as transcript_status=failed.
    """
    provider = settings.TRANSCRIPTION_PROVIDER
    if provider == "disabled":
        return None
    if provider == "mock":
        return _mock_transcript(call)
    if provider == "openai":
        return _transcribe_openai(call)
    raise TranscriptionError(f"Unknown TRANSCRIPTION_PROVIDER: {provider!r}")


def _transcribe_openai(call: Call) -> str | None:
    if not call.recording_url:
        return None

    try:
        audio_response = httpx.get(call.recording_url, timeout=30.0)
        audio_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Could not download recording: {exc}") from exc

    try:
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            files={"file": ("recording.mp3", audio_response.content, "audio/mpeg")},
            data={"model": "whisper-1"},
            timeout=120.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"OpenAI transcription failed: {exc}") from exc

    text = response.json().get("text")
    return text or None


def _mock_transcript(call: Call) -> str:
    """Synthesize a short, believable interview transcript consistent with the call's
    result/custom_data. No network - this is what makes the transcript step demoable with
    zero external keys.
    """
    candidate_name = call.callee_name or "the candidate"
    role = call.custom_data.get("job_role") or call.custom_data.get("role_title") or "the role"
    interested = _truthy((call.result or {}).get("interested"))

    lines = [
        f"Agent: Hi, am I speaking with {candidate_name}? I'm calling on behalf of the hiring team about {role}.",
        f"{candidate_name}: Yes, speaking.",
        "Agent: Great, thanks for taking the call. Do you have a few minutes to talk about the opportunity?",
        f"{candidate_name}: Sure, go ahead.",
    ]
    if interested is not False:
        lines += [
            f"Agent: What interests you most about {role}?",
            f"{candidate_name}: The scope of the work and the team sound like a strong fit for where I want to grow.",
            "Agent: That's really helpful, thank you. The team will follow up with next steps.",
            f"{candidate_name}: Sounds good, looking forward to it.",
        ]
    else:
        lines += [
            f"Agent: How are you feeling about {role} based on what we've discussed?",
            f"{candidate_name}: I appreciate the call, but I don't think this is the right fit for me right now.",
            "Agent: Understood, thanks for your time today.",
            f"{candidate_name}: Thanks, take care.",
        ]
    return "\n".join(lines)


def _truthy(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "y"):
            return True
        if low in ("false", "no", "n"):
            return False
    return None
