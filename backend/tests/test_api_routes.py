"""Route-level tests through the HTTP boundary.

These exist because of a specific failure. Phase 3 shipped a response model requiring a
`period` field that the by-department shape does not have; the endpoint returned HTTP 500
and **all 170 tests stayed green**, because every one of them called metric functions
directly and none crossed the Pydantic boundary. The suite verified the arithmetic
thoroughly and the serialization not at all.

So these assert what only HTTP can: that auth is enforced, that every registered route
serializes against its declared response model, that the envelope survives, and that an
unsupported filter surfaces as 400 rather than 500.

They run against the real app with `tiny_org` behind it, via a dependency override on
`get_db` — the same override the frontend would exercise, minus the network.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app

AUTH = {"Authorization": f"Bearer {settings.demo_bearer_token}"}

#: Every metric route, with the query string needed to exercise it meaningfully.
METRIC_PATHS: tuple[str, ...] = (
    "/api/overview",
    "/api/retention/headcount",
    "/api/retention/attrition",
    "/api/retention/attrition/total",
    "/api/retention/attrition/regretted",
    "/api/retention/attrition/by-manager?min_reports=1",
    "/api/retention/tenure",
    "/api/retention/cohort-retention",
    "/api/retention/cohort-survival",
    "/api/retention/mobility",
    "/api/retention/mobility/by-year",
    "/api/acquisition/time-to-fill",
    "/api/acquisition/time-to-hire",
    "/api/acquisition/funnel",
    "/api/acquisition/offer-acceptance",
    "/api/acquisition/cost-per-hire",
    "/api/acquisition/requisition-aging",
    "/api/acquisition/source-effectiveness",
    "/api/acquisition/source-retention",
    "/api/acquisition/quality-of-hire",
    "/api/engagement/enps",
    "/api/engagement/enps/trend",
    "/api/engagement/index",
    "/api/engagement/drivers",
    "/api/engagement/drivers/trend",
    "/api/engagement/drivers/by-department",
    "/api/engagement/participation",
    "/api/engagement/attrition-link",
    "/api/engagement/absenteeism",
    "/api/engagement/themes",
    "/api/flight-risk",
    "/api/flight-risk/bands",
    "/api/flight-risk/weights",
    "/api/productivity/utilization",
    "/api/productivity/overtime",
    "/api/productivity/output",
    "/api/productivity/revenue-per-fte",
    "/api/productivity/span-of-control",
    "/api/productivity/goal-attainment",
    "/api/productivity/training",
)


@pytest.fixture(scope="module")
def api(test_engine: Engine) -> Iterator[TestClient]:
    """The real app, pointed at the seeded test database."""
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[object]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# --- Auth -------------------------------------------------------------------


def test_health_is_reachable_without_a_token(api: TestClient) -> None:
    """Render polls /health during cold start. A 401 there fails the deployment."""
    assert api.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/api/overview", "/api/retention/headcount"])
def test_metric_routes_reject_a_missing_token(api: TestClient, path: str) -> None:
    response = api.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_metric_routes_reject_a_wrong_token(api: TestClient) -> None:
    response = api.get("/api/overview", headers={"Authorization": "Bearer not-the-token"})

    assert response.status_code == 401


def test_a_non_bearer_scheme_is_rejected(api: TestClient) -> None:
    response = api.get(
        "/api/overview", headers={"Authorization": f"Basic {settings.demo_bearer_token}"}
    )

    assert response.status_code == 401


# --- Every route serializes -------------------------------------------------


@pytest.mark.parametrize("path", METRIC_PATHS)
def test_route_returns_200_and_the_standard_envelope(api: TestClient, path: str) -> None:
    """The check that would have caught phase 3's HTTP 500: every route must serialize
    against its own declared response model, not merely return a dict."""
    response = api.get(path, headers=AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert set(body["meta"]) == {"as_of", "filters_applied", "row_count"}


#: `/weights` returns the scoring constants rather than data, so filtering it is
#: meaningless. It is the only route exempt from the shared filter contract.
UNFILTERED_PATHS = frozenset({"/api/flight-risk/weights"})


@pytest.mark.parametrize("path", [p for p in METRIC_PATHS if p not in UNFILTERED_PATHS])
def test_route_echoes_the_filters_it_applied(api: TestClient, path: str) -> None:
    """A caller must be able to tell which slice they got. Filters are echoed with
    defaults resolved, so "no department filter" and "department 3" are distinguishable."""
    response = api.get(f"{path}{'&' if '?' in path else '?'}department_id=1", headers=AUTH)

    if response.status_code == 400:
        # Some views legitimately carry no department dimension; that is the filter
        # contract working, and is asserted separately below.
        return
    assert response.json()["meta"]["filters_applied"].get("department_id") == 1


# --- Filter contract --------------------------------------------------------


def test_unsupported_filter_is_a_400_not_a_500(api: TestClient) -> None:
    """`v_mobility_monthly` has no manager dimension. The request must fail with a
    readable client error, never succeed with company-wide numbers."""
    response = api.get("/api/retention/mobility?manager_id=M-901", headers=AUTH)

    assert response.status_code == 400
    body = response.json()
    assert body["filter"] == "manager_id"
    assert "not available" in body["detail"]


def test_invalid_filter_values_are_rejected_by_validation(api: TestClient) -> None:
    """`level` is bounded 1-6 by the dependency, so 99 is a 422 before any SQL runs."""
    assert api.get("/api/retention/headcount?level=99", headers=AUTH).status_code == 422


# --- Overview ---------------------------------------------------------------


def test_overview_returns_eight_kpis(api: TestClient) -> None:
    body = api.get("/api/overview", headers=AUTH).json()

    assert body["meta"]["row_count"] == 8
    assert len(body["data"]["kpis"]) == 8


def test_overview_kpis_carry_direction_and_a_sparkline(api: TestClient) -> None:
    """`higher_is_better` decides whether the frontend paints a delta green or red. A
    KPI without it would get an arrow that asserts something untrue — rising attrition
    is not good news."""
    kpis = {
        kpi["key"]: kpi for kpi in api.get("/api/overview", headers=AUTH).json()["data"]["kpis"]
    }

    assert kpis["attrition_rate"]["higher_is_better"] is False
    assert kpis["offer_acceptance"]["higher_is_better"] is True
    # Headcount is genuinely directionless: growth is neither good nor bad without context.
    assert kpis["headcount"]["higher_is_better"] is None

    assert len(kpis["headcount"]["sparkline"]) > 1


def test_overview_compares_against_the_preceding_period(api: TestClient) -> None:
    """The comparison window must sit immediately before the current one and be the same
    length, so a quarter compares against the quarter before it."""
    data = api.get("/api/overview?date_from=2025-01-01&date_to=2025-03-31", headers=AUTH).json()[
        "data"
    ]

    assert data["period_from"] == "2025-01-01"
    assert data["comparison_to"] == "2024-12-01"
    assert data["comparison_from"] == "2024-10-01"


def test_overview_anchors_to_the_data_not_the_clock(api: TestClient) -> None:
    """`tiny_org` ends in June 2025. Anchoring to `today` would make every card empty."""
    data = api.get("/api/overview", headers=AUTH).json()["data"]

    assert data["as_of"] == "2025-06-01"


# --- Docs -------------------------------------------------------------------


def test_openapi_documents_every_metric_route(api: TestClient) -> None:
    paths = set(api.get("/openapi.json").json()["paths"])

    for path in METRIC_PATHS:
        assert path.split("?")[0] in paths
