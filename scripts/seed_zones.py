"""Seed synthetic demo ratings in three concentric zones around the Main Square (Rynek).

  python scripts/seed_zones.py --dry-run   # plan and statistics only
  python scripts/seed_zones.py --apply     # replace this seed's ratings in the database (one transaction)
  python scripts/seed_zones.py --remove    # delete this seed's ratings

Zones (distance of the segment centre from Rynek) and what a rater there tends to say
(scale 1-5, 5 = best; for traffic 5 = free-flowing, for parking 5 = easy):

  centre      < 1.5 km   heavy traffic, nice views, hardly any parking, good surface
  donut       1.5-4 km   medium traffic, ugly, parking OK, very good surface
  obwarzanek  > 4 km     average to poor surface, plenty of parking, average to weak views

Safety was not specified; it is set plausibly and can be changed below. Every row is tagged with
ratings.seed_tag so it can be told apart from real ratings; running --apply again replaces the previous
batch. Existing ratings are never touched. Rows are deterministic (fixed random seed).
"""

import argparse
import datetime as dt
import math
import os
import random
import statistics
import sys
from zoneinfo import ZoneInfo

import psycopg

TAG = "zones-2026-10"
SEED = 20261005
CENTER = (19.9373, 50.0617)  # Rynek, lon/lat
DIMS = ("surface", "views", "safety", "traffic", "parking")
WARSAW = ZoneInfo("Europe/Warsaw")

# zone -> (upper edge in km, mean per dimension, how much one segment's character varies per dimension)
ZONES = {
    "centre": (1.5, {"surface": 4.2, "views": 4.4, "safety": 3.4, "traffic": 1.7, "parking": 1.6},
               {"surface": 0.4, "views": 0.4, "safety": 0.4, "traffic": 0.4, "parking": 0.4}),
    "donut": (4.0, {"surface": 4.6, "views": 1.8, "safety": 3.6, "traffic": 3.0, "parking": 3.8},
              {"surface": 0.3, "views": 0.4, "safety": 0.4, "traffic": 0.5, "parking": 0.5}),
    "obwarzanek": (math.inf, {"surface": 2.3, "views": 2.4, "safety": 2.9, "traffic": 3.6, "parking": 4.6},
                   {"surface": 0.75, "views": 0.55, "safety": 0.5, "traffic": 0.6, "parking": 0.4}),
}
ZONE_ORDER = list(ZONES)
BLEND_KM = 0.35        # zone means are blended over +-this distance so borders are not razor sharp
RATER_SD = 0.55        # disagreement between raters of the same segment
SEGMENTS_PER_FRAGMENT = 2
RATINGS_PER_SEGMENT = (3, 6)
# time of day -> (local hours, per-dimension shift): at night views and safety drop, traffic and parking ease
BANDS = {
    "morning": ((6, 10), {"traffic": -0.3}),
    "day": ((10, 16), {}),
    "evening": ((16, 22), {"traffic": -0.4, "parking": -0.3}),
    "night": ((22, 30), {"views": -0.8, "safety": -0.6, "traffic": 1.2, "parking": 1.0}),
}
BAND_WEIGHTS = {"morning": 3, "day": 4, "evening": 4, "night": 2}


def distance_km(lon, lat):
    dx = math.radians(lon - CENTER[0]) * math.cos(math.radians((lat + CENTER[1]) / 2))
    return 6371.0 * math.hypot(dx, math.radians(lat - CENTER[1]))


def zone_of(km):
    return next(z for z in ZONE_ORDER if km < ZONES[z][0])


def zone_means(km):
    """Zone means for a distance, blended with the neighbouring zone near a border."""
    means = dict(ZONES[zone_of(km)][1])
    sds = dict(ZONES[zone_of(km)][2])
    for inner, outer in zip(ZONE_ORDER, ZONE_ORDER[1:]):
        edge = ZONES[inner][0]
        if abs(km - edge) < BLEND_KM:
            t = (km - edge + BLEND_KM) / (2 * BLEND_KM)  # 0 inside .. 1 outside
            t = t * t * (3 - 2 * t)
            for d in DIMS:
                means[d] = ZONES[inner][1][d] * (1 - t) + ZONES[outer][1][d] * t
                sds[d] = ZONES[inner][2][d] * (1 - t) + ZONES[outer][2][d] * t
    return means, sds


def clip(x):
    return max(1, min(5, int(round(x))))


def plan(segments, user_ids, taken=frozenset()):
    """Rows to insert. `taken` holds (user, segment) pairs that already have a real rating: skipped."""
    rng = random.Random(SEED)
    by_fragment: dict[int, list[tuple]] = {}
    for sid, gid, lon, lat in segments:
        by_fragment.setdefault(gid if gid is not None else -sid, []).append((sid, lon, lat))
    today = dt.date(2026, 10, 5)
    rows = []
    for gid in sorted(by_fragment):
        members = sorted(by_fragment[gid])
        for sid, lon, lat in rng.sample(members, min(SEGMENTS_PER_FRAGMENT, len(members))):
            means, sds = zone_means(distance_km(lon, lat))
            character = {d: rng.gauss(0, sds[d]) for d in DIMS}  # what this particular road is like
            free = [u for u in user_ids if (u, sid) not in taken]
            for user in rng.sample(free, min(len(free), rng.randint(*RATINGS_PER_SEGMENT))):
                band = rng.choices(list(BAND_WEIGHTS), weights=list(BAND_WEIGHTS.values()))[0]
                (h0, h1), shift = BANDS[band]
                day = today - dt.timedelta(days=rng.randint(0, 30))
                local = dt.datetime.combine(day, dt.time(0), WARSAW) + dt.timedelta(hours=rng.uniform(h0, h1))
                rated_on = local.date() if local.hour >= 0 else day
                dims = list(DIMS) if rng.random() < 0.7 else rng.sample(DIMS, rng.randint(2, 4))
                row = {d: clip(means[d] + character[d] + shift.get(d, 0) + rng.gauss(0, RATER_SD)) if d in dims else None for d in DIMS}
                rows.append({"segment_id": sid, "user_id": user, **row, "time_of_day": band,
                             "rated_on": local.astimezone(WARSAW).date(), "created_at": local, "seed_tag": TAG,
                             "zone": zone_of(distance_km(lon, lat))})
    return rows


def report_plan(rows):
    print(f"planned ratings: {len(rows)} on {len({r['segment_id'] for r in rows})} segments")
    for zone in ZONE_ORDER:
        part = [r for r in rows if r["zone"] == zone]
        avg = {d: statistics.mean(r[d] for r in part if r[d] is not None) for d in DIMS}
        print(f"  {zone:11s} {len(part):6d} ratings  " + "  ".join(f"{d} {avg[d]:.2f}" for d in DIMS))


INSERT = """
insert into public.ratings (segment_id, user_id, surface, views, safety, traffic, parking, time_of_day, rated_on, created_at, seed_tag)
values (%(segment_id)s, %(user_id)s, %(surface)s, %(views)s, %(safety)s, %(traffic)s, %(parking)s,
        %(time_of_day)s::public.time_of_day, %(rated_on)s, %(created_at)s, %(seed_tag)s)
"""

ZONE_SQL = """
case when st_distance(st_centroid(s.geom)::geography, st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326)::geography) < 1500 then 'centre'
     when st_distance(st_centroid(s.geom)::geography, st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326)::geography) < 4000 then 'donut'
     else 'obwarzanek' end
"""


def refresh(conn):
    for view in ("segment_stats", "segment_stats_by_time", "segment_scores", "routing_graph"):
        if conn.execute("select to_regclass(%s)", (f"public.{view}",)).fetchone()[0]:
            conn.execute(f"refresh materialized view public.{view}")  # noqa: S608 (fixed names)


def db_report(conn):
    print("in the database (this seed only):")
    for zone, n, *avg in conn.execute(f"""
        select {ZONE_SQL} z, count(*), avg(surface), avg(views), avg(safety), avg(traffic), avg(parking)
        from public.ratings r join public.segments s on s.id = r.segment_id
        where r.seed_tag = %(tag)s group by 1 order by 1""", {"lon": CENTER[0], "lat": CENTER[1], "tag": TAG}):
        print(f"  {zone:11s} {n:6d} ratings  " + "  ".join(f"{d} {float(v):.2f}" for d, v in zip(DIMS, avg)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set")
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '600s'")
        conn.execute("set local search_path = public, extensions")
        if args.remove:
            n = conn.execute("delete from public.ratings where seed_tag = %s", (TAG,)).rowcount
            refresh(conn)
            conn.commit()
            print(f"removed {n} seeded ratings and refreshed the score views")
            return
        segments = conn.execute("select id, group_id, st_x(st_centroid(geom)), st_y(st_centroid(geom)) from public.segments order by id").fetchall()
        users = [r[0] for r in conn.execute("select id from public.profiles order by id")]
        taken = {(r[0], r[1]) for r in conn.execute("select user_id, segment_id from public.ratings where seed_tag is null")}
        rows = plan(segments, users, taken)
        report_plan(rows)
        if not args.apply:
            return
        before = conn.execute("select count(*) from public.ratings where seed_tag is null").fetchone()[0]
        conn.execute("delete from public.ratings where seed_tag = %s", (TAG,))
        with conn.cursor() as cur:
            cur.executemany(INSERT, rows)
        after = conn.execute("select count(*) from public.ratings where seed_tag is null").fetchone()[0]
        total = conn.execute("select count(*) from public.ratings where seed_tag = %s", (TAG,)).fetchone()[0]
        assert before == after, "real ratings must not change"
        assert total == len(rows), f"expected {len(rows)} seeded rows, found {total}"
        refresh(conn)
        db_report(conn)
        conn.commit()
        print(f"committed: {total} seeded ratings, {after} existing ratings untouched")


if __name__ == "__main__":
    main()
