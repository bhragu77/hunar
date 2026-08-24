import os
from urllib.parse import urlsplit, urlunsplit

# Tests must NEVER touch the same database as a live/dev backend - the table-wipe fixture
# below would destroy real data. Point at a "_test"-suffixed database, and force it before
# any `app.*` module (which reads DATABASE_URL at import time) gets imported below.
_RAW_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hunar:hunar@localhost:5442/hunar")


def _as_test_database_url(url: str) -> str:
    parts = urlsplit(url)
    db_name = parts.path.lstrip("/")
    if not db_name.endswith("_test"):
        db_name = f"{db_name}_test"
    return urlunsplit(parts._replace(path=f"/{db_name}"))


_TEST_DATABASE_URL = _as_test_database_url(_RAW_DATABASE_URL)
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL


def _ensure_test_database_exists() -> None:
    """Postgres can't create a database via a connection to one that doesn't exist yet, so
    connect to the admin `postgres` database first and create it if needed."""
    import psycopg2

    parts = urlsplit(_TEST_DATABASE_URL)
    db_name = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()


_ensure_test_database_exists()

import pytest  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import engine, init_db  # noqa: E402
from app.core.scheduler import scheduler, wait_until_idle  # noqa: E402
from app.models.attendance_record import AttendanceRecord  # noqa: E402
from app.models.call import Call  # noqa: E402
from app.models.call_event import CallEvent  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.models.location import Location  # noqa: E402
from app.models.sourced_candidate import SourcedCandidate  # noqa: E402
from app.models.worker import Worker  # noqa: E402
from app.providers.factory import get_voice_provider  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _force_mock_provider():
    """Tests must never depend on ambient provider settings in .env - if VOICE_PROVIDER,
    LLM_PROVIDER, or TRANSCRIPTION_PROVIDER are set to a real backend for manual
    verification, a test could otherwise make a REAL (possibly paid) request to a real API.
    Force "mock" for all three, for the whole test session, regardless of what's configured.
    """
    settings.VOICE_PROVIDER = "mock"
    settings.LLM_PROVIDER = "mock"
    settings.TRANSCRIPTION_PROVIDER = "mock"
    settings.PEOPLE_SEARCH_PROVIDER = "mock"
    get_voice_provider.cache_clear()  # in case anything already cached a real provider


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    """Create tables once for the session, in the isolated _test database (see top of this
    file) - never the live/dev one."""
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
    """Wipe voice-core tables before every test. Safe: this only ever runs against the
    isolated _test database set up above, never the live/dev one.

    Drains the scheduler first: a previous test's mock call simulation (or its post-call
    pipeline job) can still be running in a background thread well after that test's own
    assertions passed - see app/core/scheduler.py::wait_until_idle. Without this, a stray
    background job's DB write (or self-signed webhook POST) could land after these deletes,
    racing the next test in a way that's flaky rather than deterministic.
    """
    wait_until_idle()
    with Session(engine) as session:
        session.exec(delete(AttendanceRecord))
        session.exec(delete(SourcedCandidate))
        session.exec(delete(CallEvent))
        session.exec(delete(Call))
        session.exec(delete(Campaign))
        session.exec(delete(Worker))
        session.exec(delete(Location))
        session.commit()
    yield
