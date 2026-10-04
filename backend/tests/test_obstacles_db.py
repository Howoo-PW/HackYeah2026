"""Opt-in checks of the obstacle SQL and its effect on routes against the real database.

RUN_DB_TESTS=1 python -m pytest -c backend/pytest.ini backend/tests/test_obstacles_db.py
Everything runs in one transaction that is rolled back, so nothing is left in the database.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.database import create_pool
from app.obstacles import ObstacleCreate, ObstacleRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1" or not settings.supabase_db_url.get_secret_value(),
    reason="set RUN_DB_TESTS=1 and SUPABASE_DB_URL to run against the real database",
)

ROUTE = (19.9373, 50.0617, 19.9700, 50.0360)  # Rynek -> Podgorze, a few kilometres by car
BBOX = (19.79, 49.97, 20.21, 50.12)


@pytest.fixture
def conn():
    pool = create_pool()
    pool.open(wait=True, timeout=30)
    with pool.connection() as connection:
        yield connection
        connection.rollback()
    pool.close()


def route(conn, profile="driving-car"):
    return conn.execute("SELECT edge_id, time_s FROM public.find_route(%s, %s, %s, %s, %s) ORDER BY seq",
                        (profile, *ROUTE)).fetchall()


def user_id(conn):
    row = conn.execute("SELECT id FROM public.profiles LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no profile in the database to report as")
    return row["id"]


def middle_of(conn, edge_id):
    row = conn.execute("SELECT ST_Y(p) AS lat, ST_X(p) AS lon FROM "
                       "(SELECT ST_LineInterpolatePoint(geom, 0.5) AS p FROM public.routing_edges WHERE id = %s) x",
                       (edge_id,)).fetchone()
    return {"lat": row["lat"], "lon": row["lon"]}


def report(conn, kind, location, valid_until=None):
    payload = ObstacleCreate(type=kind, location=location, valid_until=valid_until)
    return ObstacleRepository(conn).create(user_id(conn), payload)


def test_repository_creates_lists_and_deletes_an_obstacle(conn):
    repo = ObstacleRepository(conn)
    seg = conn.execute("SELECT id, ST_Y(p) AS lat, ST_X(p) AS lon FROM (SELECT id, ST_LineInterpolatePoint(geom, 0.5) AS p "
                       "FROM public.segments WHERE highway = 'residential' ORDER BY id LIMIT 1) x").fetchone()
    created = report(conn, "pothole", {"lat": seg["lat"], "lon": seg["lon"]})
    assert created["type"] == "pothole" and created["segment_id"] == seg["id"]  # attached to the road it lies on
    assert created["location"] == pytest.approx({"lat": seg["lat"], "lon": seg["lon"]})
    assert created["id"] in [o["id"] for o in repo.active(BBOX)]
    repo.delete(created["id"])
    assert created["id"] not in [o["id"] for o in repo.active(BBOX)]


def test_expired_obstacles_are_not_listed(conn):
    created = report(conn, "roadwork", {"lat": 50.0617, "lon": 19.9373}, datetime.now(timezone.utc) + timedelta(hours=1))
    conn.execute("UPDATE public.obstacles SET valid_until = now() - interval '1 minute' WHERE id = %s", (created["id"],))
    assert created["id"] not in [o["id"] for o in ObstacleRepository(conn).active(BBOX)]


def test_point_far_from_any_road_gets_no_segment(conn):
    created = report(conn, "other", {"lat": 50.0540, "lon": 19.8450})  # forest
    assert created["segment_id"] is None


@pytest.mark.parametrize("profile", ["driving-car", "cycling-regular", "foot-walking"])
def test_a_closure_sends_the_route_around_it_and_removal_restores_it(conn, profile):
    base = route(conn, profile)
    target = base[len(base) // 2]["edge_id"]
    closure = report(conn, "closure", middle_of(conn, target))

    detour = route(conn, profile)
    assert target not in [r["edge_id"] for r in detour]
    assert sum(r["time_s"] for r in detour) >= sum(r["time_s"] for r in base)

    ObstacleRepository(conn).delete(closure["id"])
    assert [r["edge_id"] for r in route(conn, profile)] == [r["edge_id"] for r in base]


def test_expired_closure_does_not_affect_routes(conn):
    base = route(conn)
    created = report(conn, "closure", middle_of(conn, base[len(base) // 2]["edge_id"]),
                      datetime.now(timezone.utc) + timedelta(hours=1))
    conn.execute("UPDATE public.obstacles SET valid_until = now() - interval '1 minute' WHERE id = %s", (created["id"],))
    assert [r["edge_id"] for r in route(conn)] == [r["edge_id"] for r in base]
