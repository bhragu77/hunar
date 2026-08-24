import pytest
from sqlmodel import Session, delete

from app.core.db import engine, init_db
from app.core.scheduler import scheduler
from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.campaign import Campaign
from app.providers.factory import get_voice_provider


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    """Create tables once for the session. Requires a reachable Postgres - see README
    (`docker compose up db`) before running pytest natively."""
    init_db()


@pytest.fixture(scope="session", autouse=True)
def _test_scheduler():
    """Start the shared APScheduler instance for the whole test session, mirroring what
    main.py's lifespan does - MockProvider needs a running scheduler to progress calls."""
    if not scheduler.running:
        scheduler.start()
    yield
    # wait=True: let any in-flight mock call simulation finish its webhook POST before the
    # test process's streams get torn down, instead of racing it.
    scheduler.shutdown(wait=True)


@pytest.fixture(autouse=True)
def _reset_provider_cache():
    """MockProvider holds in-memory per-call state, so give each test a fresh instance."""
    get_voice_provider.cache_clear()
    yield
    get_voice_provider.cache_clear()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe voice-core tables before every test. There's no real data yet (dev DB), so this
    is simpler and more debuggable than transaction-rollback fixtures."""
    with Session(engine) as session:
        session.exec(delete(CallEvent))
        session.exec(delete(Call))
        session.exec(delete(Campaign))
        session.commit()
    yield
