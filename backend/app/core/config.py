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

    # Phase 4+ integrations - unused in this phase
    APOLLO_API_KEY: str = ""
    PDL_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
