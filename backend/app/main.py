import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.db import init_db
from app.core.logging import configure_logging
from app.core.runtime_state import get_voice_provider_name
from app.core.scheduler import scheduler
from app.schemas.health import HealthResponse
from app.services.poller import poll_stale_calls

configure_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up - initializing database")
    init_db()

    if settings.DEMO_SEED_ON_START:
        _seed_demo_data_if_enabled()

    scheduler.add_job(
        poll_stale_calls,
        trigger="interval",
        seconds=settings.POLL_INTERVAL_SECONDS,
        id="poll_stale_calls",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started (poll interval=%ss)", settings.POLL_INTERVAL_SECONDS)

    yield

    scheduler.shutdown(wait=False)
    logger.info("Background scheduler stopped")


def _seed_demo_data_if_enabled() -> None:
    """Best-effort, idempotent Attendance demo seed - see settings.DEMO_SEED_ON_START. Never
    blocks startup: a failure here (e.g. a cold DB not quite ready) just leaves the empty-state
    "Seed demo data" button as the fallback."""
    from sqlmodel import Session

    from app.core.db import engine
    from app.services.attendance import seed_demo

    try:
        with Session(engine) as session:
            result = seed_demo(session)
        logger.info("Demo seed on startup: %s", result)
    except Exception:
        logger.exception("Demo seed on startup failed - continuing without it")


def create_app() -> FastAPI:
    app = FastAPI(title="Hunar API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", provider=get_voice_provider_name())

    return app


app = create_app()
