import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from . import config  # noqa: F401 (import validates required env vars are set)
from .call_session import CallSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_ai_toy")

app = FastAPI(title="Voice AI Toy Pipeline")


@app.post("/twilio/voice")
async def twilio_voice(request: Request) -> Response:
    """Twilio hits this webhook the moment the number is called. We reply with TwiML that
    opens a bidirectional Media Stream back to us - from here on, all audio flows over the
    WebSocket below instead of further TwiML."""
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}/media" />
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/media")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    session = CallSession(websocket)
    try:
        await session.run()
    except WebSocketDisconnect:
        logger.info("Twilio disconnected the media stream")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
