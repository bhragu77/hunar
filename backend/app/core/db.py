from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=False)


def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call on every startup.

    Imports app.models first: SQLModel only knows about a table once its class has been
    imported somewhere, and relying on that happening as a side effect of unrelated imports
    elsewhere in the app is exactly the kind of thing that silently no-ops in a standalone
    script or test. Import it explicitly here instead.
    """
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a sync SQLModel session."""
    with Session(engine) as session:
        yield session
