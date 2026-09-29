# Voice AI Toy Pipeline

A minimal, from-scratch implementation of the cascaded voice-AI pipeline discussed alongside
the Hunar project: **Twilio (telephony) → Deepgram (streaming STT) → Groq/Llama 3.3 70B (the
"brain") → Deepgram Aura (streaming TTS) → back to the caller**, including barge-in
(interrupting the bot mid-sentence). This is a *learning* project, not a production system -
the point is to see every stage of the pipeline that a managed platform like Hunar normally
hides behind one API key.

## Architecture

```
Caller's phone
     │  PSTN
     ▼
  Twilio  ──────────────────────────────────────────────────────────────┐
     │  wss:// Media Stream (bidirectional, mu-law 8kHz)                 │
     ▼                                                                   │
 FastAPI /media websocket (app/call_session.py)                         │
     │  raw audio frames                            ▲ TTS audio frames  │
     ▼                                               │                   │
 Deepgram streaming STT (app/stt.py)                 │                   │
     │  transcript + speech_final                    │                   │
     ▼                                               │                   │
 Groq / Llama 3.3 70B (app/llm.py)                    │                   │
     │  reply text                                   │                   │
     ▼                                               │                   │
 Deepgram Aura TTS, streamed (app/tts.py) ────────────┘                   │
                                                                          │
     bot audio frames sent back over the SAME websocket ─────────────────┘
```

Everything is deliberately un-abstracted: no voice-AI SDK/framework in between, so each
protocol (Twilio Media Streams, Deepgram's streaming STT/TTS wire format, a plain chat
completion call) is visible in the code.

## What each piece is actually doing

- **`app/call_session.py`** - the orchestrator. One `CallSession` per phone call: reads
  Twilio's websocket events (`start` / `media` / `stop`), forwards raw audio to Deepgram,
  and on `speech_final` runs the LLM → TTS turn. Also owns barge-in: if a new transcript
  starts arriving while the bot's TTS task is still streaming, it cancels that task and
  sends Twilio a `clear` event to flush whatever bot audio was already queued.
- **`app/stt.py`** - one persistent Deepgram streaming websocket per call. We feed it raw
  mu-law bytes as they arrive; Deepgram's own **endpointing** (`speech_final`, tuned by
  `DEEPGRAM_STT_ENDPOINTING_MS`) decides when the caller's turn is over - not a fixed timer
  we write ourselves.
- **`app/llm.py`** - a single OpenAI-compatible chat completion call to Groq, serving the
  open-source Llama 3.3 70B model. The system prompt keeps replies short because they're
  read aloud, not displayed.
- **`app/tts.py`** - streams Deepgram Aura's audio response and re-chunks it into
  20ms/160-byte mu-law frames matching Twilio's native telephony format exactly, so there's
  no resampling step anywhere in the pipeline. It yields frames as they arrive rather than
  waiting for the whole sentence, which is what lets playback start before synthesis has
  finished - the same streaming principle that makes STT and the LLM call fast.
- **`app/main.py`** - two routes: `POST /twilio/voice` (returns the TwiML that tells Twilio
  to open the Media Stream) and `WS /media` (where all the actual audio flows).

## Prerequisites

- Python 3.11
- A Twilio account with a phone number (trial account works for outbound-to-verified-numbers
  or inbound testing)
- A free Deepgram API key: https://console.deepgram.com (covers both STT and TTS here)
- A free Groq API key: https://console.groq.com
- [ngrok](https://ngrok.com) (or any tunnel) to expose your local server to Twilio

## Setup

```bash
cd voice-ai-toy
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `DEEPGRAM_API_KEY`, `GROQ_API_KEY` - from the consoles above
- `PUBLIC_BASE_URL` - fill this in *after* starting ngrok (next step), then restart the app

Start the server:

```bash
uvicorn app.main:app --port 8000
```

In another terminal, tunnel it:

```bash
ngrok http 8000
```

Copy the `https://...ngrok-free.app` URL ngrok prints into `PUBLIC_BASE_URL` in `.env`, then
restart `uvicorn` so it picks up the new value.

In the Twilio console, open your phone number's configuration and set **"A call comes
in" → Webhook → `https://<your-ngrok-url>/twilio/voice` → HTTP POST**. Save.

Call the Twilio number. You should hear the greeting, then be able to talk back and forth
with the bot. Try talking over it mid-reply to see the barge-in (`clear` event) kick in.

## Things to actually observe while testing this

- **Where the latency lives.** Watch the `uvicorn` logs (`Caller: ...` / `Agent: ...`) and
  time the gap between them - that's your STT-endpointing + LLM + first-TTS-frame latency
  budget in practice, the exact thing the "basics of voice AI" discussion covered.
- **`DEEPGRAM_STT_ENDPOINTING_MS`** - lower it and the bot replies faster but starts cutting
  you off mid-sentence; raise it and replies get safer but slower. This is the classic
  endpointing tradeoff.
- **Barge-in** - interrupt the bot while it's talking. `_clear_playback()` cancels the
  in-flight TTS task and tells Twilio to flush its outbound audio buffer immediately.
- **What's *not* here** - no noise suppression, no multi-language handling, no interruption
  based on semantic content (only on "caller made a sound"), no retries/reconnect logic for
  dropped websockets, no Twilio request-signature verification. All of that is exactly the
  kind of hardening that a managed platform like Hunar has already built.

## Known limitations (by design - this is a toy)

- No Twilio webhook signature validation - anyone who discovers the ngrok URL could POST to
  `/twilio/voice`. Do not point a production number at this.
- No auth/rate limiting on the FastAPI app at all.
- No reconnect handling if the Deepgram websocket drops mid-call.
- No persistence - conversation history lives only in memory for the life of the call.
- ngrok's free tier URL changes every restart - remember to update `PUBLIC_BASE_URL` and the
  Twilio webhook each time.
