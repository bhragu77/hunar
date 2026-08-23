from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=False)


def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call on every startup."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a sync SQLModel session."""
    with Session(engine) as session:
        yield session
