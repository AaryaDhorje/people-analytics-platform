"""Database engine, session factory, and the declarative base.

SQLAlchemy 2.0 style throughout: `DeclarativeBase`, `Mapped`, `mapped_column`.
No Query API, no `declarative_base()`.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Neon closes idle connections; without this the first query after
    # an idle period fails instead of transparently reconnecting.
    pool_size=5,
    max_overflow=5,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every ORM model in app/models/."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
