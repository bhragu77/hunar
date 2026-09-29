import asyncio
import base64
import json
import logging

from fastapi import WebSocket

from . import llm
from .stt import DeepgramSTT
from .tts import synthesize_frames

logger = logging.getLogger("voice_ai_toy.session")

GREETING = "Hi Gangula Reddy, this is a toy voice assistant. Go ahead and ask me something."


class CallSession:
    """One instance per phone call. Owns the Twilio websocket, the Deepgram STT connection,
    the conversation history, and whichever TTS-playback task is currently running - so a
    new user utterance can cancel it (barge-in)."""

    def __init__(self, twilio_ws: WebSocket) -> None:
        self.twilio_ws = twilio_ws
        self.stream_sid: str | None = None
        self.stt = DeepgramSTT()
        self.history: list[dict[str, str]] = []
        self._speaking_task: asyncio.Task | None = None

    async def run(self) -> None:
        await self.stt.connect()
        reader_task = asyncio.create_task(self._read_transcripts())
        try:
            await self._read_twilio_events()
        finally:
            reader_task.cancel()
            await self.stt.close()

    async def _read_twilio_events(self) -> None:
        while True:
            raw = await self.twilio_ws.receive_text()
            event = json.loads(raw)
            kind = event.get("event")

            if kind == "start":
                self.stream_sid = event["start"]["streamSid"]
                logger.info("Call started: %s", self.stream_sid)
                await self._speak(GREETING)

            elif kind == "media":
                payload = base64.b64decode(event["media"]["payload"])
                await self.stt.send_audio(payload)

            elif kind == "stop":
                logger.info("Call ended: %s", self.stream_sid)
                return

    async def _read_transcripts(self) -> None:
        async for transcript, speech_final in self.stt.transcripts():
            if self._speaking_task and not self._speaking_task.done():
                # Caller started talking while the bot was mid-reply: barge-in.
                await self._clear_playback()

            if speech_final:
                await self._handle_user_turn(transcript)

    async def _handle_user_turn(self, transcript: str) -> None:
        logger.info("Caller: %s", transcript)
        self.history.append({"role": "user", "content": transcript})
        reply = await llm.get_reply(self.history)
        self.history.append({"role": "assistant", "content": reply})
        logger.info("Agent: %s", reply)
        await self._speak(reply)

    async def _speak(self, text: str) -> None:
        self._speaking_task = asyncio.create_task(self._stream_tts(text))

    async def _stream_tts(self, text: str) -> None:
        try:
            async for frame in synthesize_frames(text):
                await self._send_media(frame)
        except asyncio.CancelledError:
            pass

    async def _send_media(self, frame: bytes) -> None:
        await self.twilio_ws.send_text(json.dumps({
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": base64.b64encode(frame).decode()},
        }))

    async def _clear_playback(self) -> None:
        if self._speaking_task:
            self._speaking_task.cancel()
        await self.twilio_ws.send_text(json.dumps({
            "event": "clear",
            "streamSid": self.stream_sid,
        }))
