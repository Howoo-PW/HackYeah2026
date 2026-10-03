"""Opt-in checks against the real Supabase database (graph, find_route, snapping, the whole endpoint).

Skipped unless RUN_DB_TESTS=1 and SUPABASE_DB_URL is configured, so the normal suite stays offline:
    RUN_DB_TESTS=1 python -m pytest -c backend/pytest.ini backend/tests/test_graph_db.py
Read-only: nothing is written to the database.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import create_pool
from app.main import app
from app.routing.graph import MAX_SNAP_M, PostgresGraphSource, graph_routes
from app.routing.schemas import Point, Weights

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1" or not settings.supabase_db_url.get_secret_value(),
    reason="set RUN_DB_TESTS=1 and SUPABASE_DB_URL to run against the real database",
)

RYNEK = Point(lat=50.0617, lon=19.9373)
PODGORZE = Point(lat=50.0470, lon=19.9440)
FAR_EAST = Point(lat=50.0900, lon=20.0000)
FAR_WEST = Point(lat=50.0500, lon=19.9000)
LAS_WOLSKI = Point(lat=50.0540, lon=19.8450)  # forest, > 800 m from any road


@pytest.fixture(scope="module")
def source():
    pool = create_pool()
    pool.open(wait=True, timeout=30)
    yield PostgresGraphSource(pool)
    pool.close()


def test_snapping_distance(source):
    assert source.snap_distance("cycling-regular", RYNEK) < MAX_SNAP_M
    assert source.snap_distance("driving-car", LAS_WOLSKI) > MAX_SNAP_M


@pytest.mark.parametrize("profile", ["driving-car", "cycling-regular"])
def test_fastest_route_is_connected_and_plausible(source, profile):
    routes = graph_routes(source, profile, FAR_EAST, FAR_WEST, Weights())
    assert len(routes) == 1
    route = routes[0]
    assert 8_000 < route.distance_m < 20_000 and route.duration_s > 0
    coords = route.geometry.coordinates
    assert len(coords) > 50 and coords[0] != coords[-1]
    assert len({tuple(c) for c in coords}) > len(coords) * 0.9  # no long repeated stretches


def test_traffic_priority_gives_a_calmer_route_for_a_bit_more_time(source):
    routes = graph_routes(source, "driving-car", FAR_EAST, FAR_WEST, Weights(traffic=3))
    assert [r.rank for r in routes] == [1, 2]
    calm, fastest = routes
    assert fastest.duration_s <= calm.duration_s  # rank 2 really is the fastest
    assert calm.duration_s < fastest.duration_s * 2  # ...and the calm one is not absurdly longer
    assert calm.coverage >= 0.0 and 0.0 <= fastest.coverage <= 1.0


def test_changing_the_weights_changes_the_route(source):
    quiet = graph_routes(source, "cycling-regular", FAR_EAST, FAR_WEST, Weights(traffic=3, safety=3))[0]
    fastest = graph_routes(source, "cycling-regular", FAR_EAST, FAR_WEST, Weights())[0]
    assert quiet.geometry.coordinates != fastest.geometry.coordinates


def test_same_point_twice_is_not_found(source):
    from app.errors import AppError

    with pytest.raises(AppError) as err:
        graph_routes(source, "driving-car", RYNEK, RYNEK, Weights())
    assert err.value.status == 404


def test_endpoint_and_health_with_the_real_pool():
    with TestClient(app) as client:
        res = client.post("/api/v1/route", json={
            "from": RYNEK.model_dump(), "to": PODGORZE.model_dump(), "profile": "cycling-regular",
            "weights": {"views": 3},
        })
        assert res.status_code == 200, res.text
        routes = res.json()["routes"]
        assert routes[0]["rank"] == 1 and routes[0]["distance_m"] > 0

        health = client.get("/api/v1/health").json()
        assert health["checks"]["routing"] in ("ok", "not_configured")  # not_configured: no ORS key (pedestrians)
        assert health["checks"]["database"] == "ok"
