"""Smoke test: the app boots, routes are registered, and the envelope holds.

This is the one test phase 0 ships. It deliberately covers the response *shape*
as well as the status code, because every metric endpoint added later depends on
that envelope being enforced from the first commit.
"""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"


def test_health_uses_the_standard_envelope(client: TestClient) -> None:
    body = client.get("/health").json()

    assert set(body) == {"data", "meta"}
    assert set(body["meta"]) == {"as_of", "filters_applied", "row_count"}
    assert body["meta"]["row_count"] == 1


def test_health_does_not_require_the_database(client: TestClient) -> None:
    """Render polls /health on a cold start, before any connection is warm."""
    assert client.get("/health").status_code == 200


def test_root_points_at_the_docs(client: TestClient) -> None:
    body = client.get("/").json()

    assert body["docs"] == "/docs"
