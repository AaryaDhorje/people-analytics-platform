"""Shared pytest fixtures.

The smoke test must pass with no database running, so nothing here connects to
Postgres. Database-backed fixtures arrive in phase 3 alongside
tests/fixtures/tiny_org.py.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """TestClient over the real app, exercising middleware and routing."""
    with TestClient(app) as test_client:
        yield test_client
