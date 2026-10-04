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
    assert source.snap("cycling-regular", RYNEK).distance_m < MAX_SNAP_M
    assert source.snap("driving-car", LAS_WOLSKI).distance_m > MAX_SNAP_M


def test_route_through_a_via_stop_passes_near_it(source):
    via = Point(lat=50.0900, lon=19.9500)
    direct = graph_routes(source, "cycling-regular", FAR_EAST, FAR_WEST, Weights())[0]
    detour = graph_routes(source, "cycling-regular", FAR_EAST, FAR_WEST, Weights(), via=[via])[0]
    assert detour.distance_m > direct.distance_m  # the stop is off the direct way
    nearest = min(((lon - via.lon) * 71_000) ** 2 + ((lat - via.lat) * 111_000) ** 2
                  for lon, lat in detour.geometry.coordinates)
    assert nearest ** 0.5 < MAX_SNAP_M


WAWEL = Point(lat=50.0540, lon=19.9353)


def test_pedestrians_reach_the_old_town_where_cars_cannot(source):
    foot, car = source.snap("foot-walking", RYNEK), source.snap("driving-car", RYNEK)
    assert foot.distance_m < 100 < car.distance_m  # pedestrian streets belong to the foot network only


def test_walk_from_the_market_square_to_wawel(source):
    route = graph_routes(source, "foot-walking", RYNEK, WAWEL, Weights())[0]
    assert 1_000 < route.distance_m < 2_500  # straight line is ~0.9 km
    assert 10 * 60 < route.duration_s < 30 * 60  # walking pace, ~5 km/h
    assert route.geometry.coordinates[0] != route.geometry.coordinates[-1]


def test_walking_priorities_change_the_route_and_rank_the_fastest_second(source):
    routes = graph_routes(source, "foot-walking", FAR_EAST, FAR_WEST, Weights(traffic=3))
    assert [r.rank for r in routes] == [1, 2]
    calm, fastest = routes
    assert calm.geometry.coordinates != fastest.geometry.coordinates
    assert fastest.duration_s <= calm.duration_s < fastest.duration_s * 2  # a calmer walk, not an absurd detour


@pytest.mark.parametrize("profile", ["driving-car", "cycling-regular", "foot-walking"])
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


def test_endpoint_and_health_with_the_real_pool():
    with TestClient(app) as client:
        res = client.post("/api/v1/route", json={
            "from": RYNEK.model_dump(), "to": PODGORZE.model_dump(), "profile": "cycling-regular",
            "weights": {"views": 3},
        })
        assert res.status_code == 200, res.text
        routes = res.json()["routes"]
        assert routes[0]["rank"] == 1 and routes[0]["distance_m"] > 0

        frontend = client.post("/api/v1/route", json={  # the request shape the frontend sends, with a via stop
            "from": {"lat": 50.06686331811255, "lon": 19.93412799209031},
            "to": {"lat": 50.06705043002839, "lon": 19.930265608621056},
            "via": [{"lat": 50.06549504004241, "lon": 19.93070285958069}],
            "profile": "driving-car",
            "weights": {"surface": 2, "views": 0, "safety": 0, "traffic": 0, "parking": 0},
        })
        assert frontend.status_code == 200, frontend.text
        assert frontend.json()["routes"][0]["rank"] == 1

        walk = client.post("/api/v1/route", json={
            "from": RYNEK.model_dump(), "to": WAWEL.model_dump(), "profile": "foot-walking", "weights": {"traffic": 2},
        })
        assert walk.status_code == 200, walk.text
        assert walk.json()["routes"][0]["rank"] == 1

        health = client.get("/api/v1/health").json()
        assert health["checks"]["routing"] == "ok"  # the graph is built for cars, bikes and pedestrians
        assert health["checks"]["database"] == "ok"
