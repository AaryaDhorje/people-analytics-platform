"""Shared pytest fixtures.

Two populations of tests live side by side and the split is deliberate:

- **No-DB tests** (health, config, schema metadata, seed definitions) open no
  connection at all, so they run in the edit hook in well under a second.
- **Metric tests** need real SQL, because most of each metric *is* SQL. They run
  against a separate `people_analytics_test` database built from
  `Base.metadata.create_all` plus the real view files, seeded once with `tiny_org`.

The separate database matters for two reasons. The dev database holds 216k generated
rows that metric expectations must never depend on, and a test run must never be able
to mutate it. Because pytest fixtures are lazy, a run touching only no-DB tests never
creates it.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import Base
from app.main import app
from app.models import (  # noqa: F401 - imported so create_all sees every table
    DimEmployee,
)
from app.sql_views import apply_views
from tests.fixtures import tiny_org

TEST_DATABASE_NAME = "people_analytics_test"


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """TestClient over the real app, exercising middleware and routing."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """A freshly built `people_analytics_test`, dropped and recreated per session.

    Recreating rather than truncating means a schema change cannot leave a stale column
    behind and silently invalidate a metric expectation.
    """
    url = make_url(settings.database_url)
    admin_url = url.set(database="postgres")
    test_url = url.set(database=TEST_DATABASE_NAME)

    # CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT. FORCE detaches
    # any connection left over from an interrupted run rather than failing on "database
    # is being accessed by other users".
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE_NAME} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DATABASE_NAME}"))
    admin_engine.dispose()

    engine = create_engine(test_url)
    Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        # The real view files, not a test-only copy. A second definition would let a
        # metric pass its test and be wrong in production.
        apply_views(session)
        _load_tiny_org(session)

    yield engine

    engine.dispose()


def _load_tiny_org(session: Session) -> None:
    """Insert the fixture in foreign-key order."""
    for table_name, rows in tiny_org.all_rows():
        if not rows:
            continue
        table = Base.metadata.tables[table_name]
        session.execute(insert(table), rows)
    session.commit()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """A read-only session over the seeded test database.

    Metric tests only read, so there is nothing to roll back. Anything that writes must
    manage its own transaction explicitly and say so.
    """
    session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
