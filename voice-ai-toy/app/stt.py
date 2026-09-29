import json
import logging
from collections.abc import AsyncIterator

import websockets

from . import config

logger = logging.getLogger("voice_ai_toy.stt")

DEEPGRAM_STT_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw&sample_rate=8000&channels=1"
    "&model=nova-2&punctuate=true&interim_results=true"
    f"&endpointing={config.DEEPGRAM_STT_ENDPOINTING_MS}"
)


class DeepgramSTT:
    """One persistent streaming connection to Deepgram for the lifetime of a call.

    We feed it raw mu-law audio frames as they arrive from Twilio; Deepgram streams back
    transcripts as the caller speaks. `speech_final` is Deepgram's own endpointing decision
    (driven by DEEPGRAM_STT_ENDPOINTING_MS of trailing silence) that the caller's turn is
    over - that flag, not silence-detection of our own, is what triggers the LLM turn.
    """

    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            DEEPGRAM_STT_URL,
            extra_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
        )

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(chunk)

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
        except websockets.ConnectionClosed:
            pass
        await self._ws.close()

    async def transcripts(self) -> AsyncIterator[tuple[str, bool]]:
        """Yields (transcript, speech_final) for every non-empty result Deepgram sends."""
        assert self._ws is not None
        async for raw in self._ws:
            event = json.loads(raw)
            if event.get("type") != "Results":
                continue
            alternatives = event.get("channel", {}).get("alternatives", [])
            if not alternatives:
                continue
            transcript = alternatives[0].get("transcript", "")
            if not transcript:
                continue
            yield transcript, bool(event.get("speech_final"))
