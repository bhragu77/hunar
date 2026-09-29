import httpx

from . import config

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a friendly, concise voice assistant on a phone call. Keep replies to 1-2 short "
    "sentences - you are being read aloud by text-to-speech, so avoid lists, markdown, or "
    "anything that doesn't sound natural spoken out loud."
)


async def get_reply(history: list[dict[str, str]]) -> str:
    """`history` is [{"role": "user"|"assistant", "content": str}, ...], oldest first."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            json={"model": config.GROQ_MODEL, "messages": messages, "temperature": 0.6},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
