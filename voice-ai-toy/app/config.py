import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name} (see .env.example)")
    return value


DEEPGRAM_API_KEY = _require("DEEPGRAM_API_KEY")
GROQ_API_KEY = _require("GROQ_API_KEY")
PUBLIC_BASE_URL = _require("PUBLIC_BASE_URL").rstrip("/")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
DEEPGRAM_TTS_MODEL = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-asteria-en")
DEEPGRAM_STT_ENDPOINTING_MS = int(os.environ.get("DEEPGRAM_STT_ENDPOINTING_MS", "300"))
