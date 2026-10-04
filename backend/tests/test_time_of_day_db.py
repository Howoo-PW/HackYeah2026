"""Opt-in checks of the time-of-day scores and their effect on routes against the real database.

RUN_DB_TESTS=1 python -m pytest -c backend/pytest.ini backend/tests/test_time_of_day_db.py
Everything runs in one transaction that is rolled back, so nothing is left in the database.
"""

import os

import pytest

from app.config import settings
from app.database import create_pool

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1" or not settings.supabase_db_url.get_secret_value(),
    reason="set RUN_DB_TESTS=1 and SUPABASE_DB_URL to run against the real database",
)

FAR_EAST = (20.0, 50.09)
FAR_WEST = (19.9, 50.05)
ALL_THREE = dict(w_surface=3, w_views=3, w_safety=3, w_traffic=3, w_parking=3)


@pytest.fixture
def conn():
    pool = create_pool()
    pool.open(wait=True, timeout=30)
    with pool.connection() as connection:
        yield connection
        connection.rollback()
    pool.close()


def route(conn, profile="driving-car", tod=None):
    return conn.execute(
        "SELECT edge_id, segment_id, time_s FROM public.find_route(%s, %s, %s, %s, %s, 3, 3, 3, 3, 3, null, %s) ORDER BY seq",
        (profile, *FAR_EAST, *FAR_WEST, tod)).fetchall()


def test_blend_pulls_the_band_average_toward_the_all_day_score(conn):
    def blend(n, band, base):
        return conn.execute("SELECT public.blend_score(%s, %s::real, %s::real) AS v", (n, band, base)).fetchone()["v"]

    assert blend(3, 1, 5) == pytest.approx(3.0)       # (3*1 + 3*5) / 6
    assert blend(9, 1, 5) == pytest.approx(2.0)       # (9*1 + 3*5) / 12: more band ratings, more weight
    assert blend(0, 1, 5) == pytest.approx(5.0)       # no ratings in the band: all-day score
    assert blend(4, None, 5) == pytest.approx(5.0)    # nobody rated this dimension in the band
    assert blend(4, 2, None) == pytest.approx(2.0)    # no all-day score: the band's own


def test_scores_for_a_time_of_day_use_the_band_ratings(conn):
    row = conn.execute("""
        SELECT t.segment_id, t.time_of_day, t.ratings_count, t.surface AS band, s.surface AS base
        FROM public.segment_stats_by_time t JOIN public.segment_scores s USING (segment_id)
        WHERE t.surface IS NOT NULL AND s.surface IS NOT NULL AND abs(t.surface - s.surface) > 0.3
        LIMIT 1""").fetchone()
    if row is None:
        pytest.skip("no segment whose band average differs from its all-day score")
    in_band = conn.execute("SELECT surface FROM public.segment_scores_for_time(%s::public.time_of_day) WHERE segment_id = %s",
                           (row["time_of_day"], row["segment_id"])).fetchone()["surface"]
    all_day = conn.execute("SELECT surface FROM public.segment_scores_for_time(null) WHERE segment_id = %s",
                           (row["segment_id"],)).fetchone()["surface"]
    expected = (row["ratings_count"] * row["band"] + 3 * row["base"]) / (row["ratings_count"] + 3)
    assert in_band == pytest.approx(expected, abs=0.01)
    assert all_day == pytest.approx(row["base"], abs=0.01)
    assert abs(in_band - row["base"]) > 0.01  # the band really changes the score, and only part of the way


@pytest.mark.parametrize("profile,tod", [
    ("driving-car", None), ("driving-car", "morning"), ("driving-car", "day"), ("driving-car", "evening"),
    ("cycling-regular", "night"), ("foot-walking", "night"),  # every band once, every profile once
])
def test_routes_exist_for_every_time_of_day_and_profile(conn, profile, tod):
    assert len(route(conn, profile, tod)) > 20


def test_unknown_time_of_day_is_refused(conn):
    import psycopg

    with pytest.raises(psycopg.errors.InvalidParameterValue):
        route(conn, "driving-car", "afternoon")


def test_night_ratings_change_only_the_night_route(conn):
    import psycopg

    day_before = [r["edge_id"] for r in route(conn, "driving-car", "day")]
    users = [r["id"] for r in conn.execute("SELECT id FROM public.profiles LIMIT 8").fetchall()]
    if len(users) < 5:
        pytest.skip("not enough profiles to rate as")
    # the longest edges of the route that lie on a segment: the ones a detour pays off for most
    candidates = sorted(
        {(r["edge_id"], r["segment_id"]) for r in route(conn, "driving-car", "day") if r["segment_id"] is not None},
        key=lambda c: -conn.execute("SELECT length_m FROM public.routing_edges WHERE id = %s", (c[0],)).fetchone()["length_m"])[:6]
    if not candidates:
        pytest.skip("the route has no edge on a rated segment")

    avoided = []
    for edge_id, segment_id in candidates:
        outcome = {}
        with conn.transaction():  # a savepoint: every candidate starts from the real data
            for user in users:  # five or more users say: terrible at night on this segment
                conn.execute("INSERT INTO public.ratings (segment_id, user_id, surface, views, safety, traffic, parking, time_of_day) "
                             "VALUES (%s, %s, 1, 1, 1, 1, 1, 'night') ON CONFLICT (user_id, segment_id, rated_on) DO NOTHING",
                             (segment_id, user))
            conn.execute("REFRESH MATERIALIZED VIEW public.segment_stats_by_time")
            outcome["night"] = [r["edge_id"] for r in route(conn, "driving-car", "night")]
            outcome["day"] = [r["edge_id"] for r in route(conn, "driving-car", "day")]
            raise psycopg.Rollback
        assert outcome["day"] == day_before  # night ratings never touch the day route
        if edge_id not in outcome["night"]:
            avoided.append(edge_id)
    assert avoided, "none of the longest rated edges was avoided at night"
