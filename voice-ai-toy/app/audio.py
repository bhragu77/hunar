SAMPLE_RATE = 8000
FRAME_MS = 20
# 8-bit mu-law @ 8kHz mono, 20ms/frame -> 160 samples -> 160 bytes. This is Twilio's native
# telephony format, so STT/TTS are both asked to speak it directly - no resampling anywhere
# in the pipeline.
FRAME_BYTES = int(SAMPLE_RATE * FRAME_MS / 1000)
