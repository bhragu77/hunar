from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, populated from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Voice provider
    VOICE_PROVIDER: str = "mock"  # "mock" | "hunar"
    HUNAR_API_KEY: str = "replace-me"
    HUNAR_BASE_URL: str = "https://api.voice.hunar.ai/external/v1"

    # Database
    DATABASE_URL: str = "postgresql://hunar:hunar@localhost:5432/hunar"

    # CORS - comma-separated list of allowed origins
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    # Public base URL for inbound webhooks (ngrok/deploy). Empty in local dev.
    PUBLIC_BASE_URL: str = ""

    # Phase 4+ integrations - unused in this phase
    APOLLO_API_KEY: str = ""
    PDL_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
