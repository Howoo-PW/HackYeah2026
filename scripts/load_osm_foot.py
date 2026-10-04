"""Pedestrians in public.osm_ways: fill foot_dir / foot_speed_kmh and add the pedestrian streets that cars and bikes do not use.

  python scripts/load_osm_foot.py --dry-run     # download (cached), classify, print statistics; the database is only read
  python scripts/load_osm_foot.py               # ... and update public.osm_ways
  python scripts/load_osm_foot.py --from-cache  # never touch Overpass

1. Every way already in osm_ways gets foot_dir / foot_speed_kmh computed from its stored `tags`
   (rules: scripts/osm_access.py, foot_direction). No re-download of the road network.
2. highway=pedestrian ways (streets and squares of the old town...) that are not in osm_ways yet are downloaded
   from Overpass and inserted (cars and bikes usually may not use them; pedestrians may).
Apply the foot migration first, rebuild the graph afterwards: select * from rebuild_routing();
Needs SUPABASE_DB_URL (.env) for loading; pip install "psycopg[binary]".
"""

import argparse
import collections
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import load_osm_routing as base
from _common import ROOT, database_url
from osm_access import FOOT_SPEED_KMH, NONE, foot_direction

CACHE = ROOT / "data" / "osm_cache" / "pedestrian.json"
BBOX = f"{base.MIN_LAT},{base.MIN_LON},{base.MAX_LAT},{base.MAX_LON}"
QUERY = f'[out:json][timeout:180];way["highway"="pedestrian"]({BBOX});out geom;'


def fetch(from_cache: bool) -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))["elements"]
    if from_cache:
        sys.exit(f"missing cache file {CACHE}")
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    last = None
    for attempt in range(6):
        url = base.SERVERS[attempt % len(base.SERVERS)]
        try:
            req = urllib.request.Request(url, body, {"User-Agent": "RateMyRoad/0.1 (hackathon project)"})
            with urllib.request.urlopen(req, timeout=300) as response:
                raw = response.read()
            data = json.loads(raw)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_bytes(raw)
            return data["elements"]
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            last = exc
            wait = 15 + 15 * attempt
            print(f"  {type(exc).__name__} from {url.split('/')[2]}, retry in {wait}s", flush=True)
            time.sleep(wait)
    sys.exit(f"Overpass failed: {last}")


UPDATE = "update public.osm_ways set foot_dir = %s, foot_speed_kmh = %s where way_id = %s"
INSERT = base.INSERT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-cache", action="store_true")
    args = parser.parse_args()

    rows = base.build_rows(fetch(args.from_cache))
    print(f"highway=pedestrian ways usable by someone: {len(rows)}")

    import psycopg

    url = database_url()
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '600s'")
        conn.execute("set local search_path = public, extensions")
        existing = {r[0]: r[1] for r in conn.execute("select way_id, tags from public.osm_ways")}
        new_rows = [r for r in rows if r["way_id"] not in existing]
        print(f"osm_ways: {len(existing)} ways; pedestrian ways not in it yet: {len(new_rows)}")

        updates = []
        for way_id, tags in existing.items():
            direction = foot_direction(tags)
            updates.append((direction, None if direction == NONE else FOOT_SPEED_KMH, way_id))
        new_foot = [r for r in new_rows if r["foot_dir"] != NONE]
        by_dir = collections.Counter(u[0] for u in updates)
        by_highway = collections.Counter(tags.get("highway") for (d, _, w), tags in zip(updates, existing.values()) if d != NONE)
        print(f"existing ways walkable: {sum(v for k, v in by_dir.items() if k != NONE)} of {len(updates)} {dict(by_dir)}")
        print("  by highway:", dict(by_highway.most_common()))
        print(f"new ways walkable: {len(new_foot)} ({sum(r['length_m'] for r in new_foot) / 1000:.1f} km)")

        if args.dry_run:
            conn.rollback()
            print("dry run: database not changed")
            return
        with conn.cursor() as cur:
            for i in range(0, len(updates), base.BATCH):
                cur.executemany(UPDATE, updates[i:i + base.BATCH])
            if new_rows:
                cur.executemany(INSERT, [{**r, "tags": json.dumps(r["tags"], ensure_ascii=False)} for r in new_rows])
        walkable, total = conn.execute("select count(*) filter (where foot_dir <> 'none'), count(*) from public.osm_ways").fetchone()
        conn.commit()
        print(f"committed: osm_ways now {total} ways, {walkable} walkable. Next: select * from rebuild_routing();")


if __name__ == "__main__":
    main()
