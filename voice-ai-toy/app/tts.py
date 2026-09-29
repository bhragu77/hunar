from collections.abc import AsyncIterator

import httpx

from . import config
from .audio import FRAME_BYTES

DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"


async def synthesize_frames(text: str) -> AsyncIterator[bytes]:
    """Streams TTS audio from Deepgram Aura and yields it pre-chunked into FRAME_BYTES-sized
    mu-law frames, ready to drop straight into Twilio media events - no resampling needed
    since we ask Deepgram for the exact encoding/sample rate the phone network already uses.
    Yielding frames as they arrive (rather than waiting for the full response) is what lets
    playback start before the whole sentence has finished synthesizing.
    """
    params = {
        "model": config.DEEPGRAM_TTS_MODEL,
        "encoding": "mulaw",
        "sample_rate": "8000",
        "container": "none",
    }
    async with httpx.AsyncClient(timeout=30.0) as client, client.stream(
        "POST",
        DEEPGRAM_TTS_URL,
        params=params,
        headers={
            "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"text": text},
    ) as response:
        response.raise_for_status()
        buffer = b""
        async for chunk in response.aiter_bytes():
            buffer += chunk
            while len(buffer) >= FRAME_BYTES:
                yield buffer[:FRAME_BYTES]
                buffer = buffer[FRAME_BYTES:]
        if buffer:
            yield buffer  # trailing partial frame
