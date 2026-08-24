from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, populated from environment variables / .env.

    env_file is a tuple so `cd backend && uvicorn ...` (or pytest) picks up the repo-root
    .env the README tells you to create, while still letting a backend-local .env override it.
    """

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Voice provider
    VOICE_PROVIDER: str = "mock"  # "mock" | "hunar"
    HUNAR_API_KEY: str = "replace-me"
    HUNAR_BASE_URL: str = "https://api.voice.hunar.ai/external/v1"

    # Database
    DATABASE_URL: str = "postgresql://hunar:hunar@localhost:5442/hunar"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Managed Postgres on Render/Railway/Heroku hands out "postgres://" URLs, a scheme
        # SQLAlchemy 1.4+ no longer recognizes (it wants the "postgresql://" scheme, same
        # database, same psycopg2 driver) - normalize it here so a platform-provided
        # DATABASE_URL works without the operator needing to edit it by hand.
        if v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://") :]
        return v

    # CORS - comma-separated list of allowed origins
    BACKEND_CORS_ORIGINS: str = "http://localhost:3010"

    # This backend's own URL. Used so MockProvider can POST a real webhook to itself
    # without needing ngrok or any public endpoint.
    INTERNAL_BASE_URL: str = "http://localhost:8010"

    # Public https base for real Hunar webhooks (ngrok/deploy). Empty in local/mock dev -
    # HunarProvider only attaches callback_config when this is set.
    PUBLIC_BASE_URL: str = ""

    # MockProvider signs its self-sent webhooks with this secret. Added to the webhook
    # receiver's trusted keys only when VOICE_PROVIDER=mock. Dev placeholder - never a real
    # secret, since nothing outside this process ever needs to know it.
    MOCK_WEBHOOK_SECRET: str = "dev-mock-secret"

    # How long (seconds) a simulated mock call takes to progress from NOT_STARTED to COMPLETED.
    MOCK_CALL_DURATION_SECONDS: int = 8

    # Polling reconciler cadence and staleness threshold (fallback path when webhooks don't
    # arrive - see app/services/poller.py).
    POLL_INTERVAL_SECONDS: int = 10
    POLL_STALE_AFTER_SECONDS: int = 20

    # Reject webhook signatures whose timestamp is older than this (replay-attack guard).
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # Post-call pipeline (transcript + AI scorecard) - see app/services/post_call.py.
    # "mock" backends make zero network calls, so the whole Hiring Assistant module demos
    # end-to-end with no external keys of any kind.
    LLM_PROVIDER: str = "mock"  # mock | anthropic | openai
    LLM_MODEL: str = ""  # optional model override; each provider has its own sane default
    TRANSCRIPTION_PROVIDER: str = "mock"  # mock | openai | disabled
    ENABLE_POST_CALL_PIPELINE: bool = True

    # People Search & Reachout (Module 2) - see app/integrations/people_search/. "mock" makes
    # zero network calls, so the whole module demos end-to-end with no external keys.
    PEOPLE_SEARCH_PROVIDER: str = "mock"  # mock | apollo | pdl
    PEOPLE_SEARCH_MAX_RESULTS: int = 25
    AGENT_AUTOCREATE: bool = True  # auto-create the outreach voice agent from the JD via the provider

    # Attendance (Module 3) - see app/services/attendance.py. Supervisor roll-call + missed-
    # call inbound both run on "mock" with zero network calls, so the whole module demos at
    # 1,000-worker/100-location scale with no external keys.
    ATTENDANCE_PRESENT_RATE: float = 0.85  # mock roll-call target present ratio (demo realism)
    ATTENDANCE_MISSED_CALL_RATE: float = 0.4  # fraction auto-marked when simulating the missed-call window

    # If true, seed the Attendance demo dataset (100 locations / ~1,000 workers) on startup if
    # it isn't there yet - idempotent (see attendance.seed_demo), never destructive. Off by
    # default so a local/native/docker-compose run never surprise-seeds your dev DB; the
    # Attendance page's own "Seed demo data" button covers that case instead. Intended for the
    # deployed environment, so a reviewer's first click lands on a populated dashboard with no
    # manual step - see render.yaml.
    DEMO_SEED_ON_START: bool = False

    APOLLO_API_KEY: str = ""
    PDL_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
