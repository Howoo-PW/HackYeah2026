"""Download the OSM routing network for cars and bikes and load it into public.osm_ways.

  python scripts/load_osm_routing.py --dry-run      # download (cached), classify, print statistics
  python scripts/load_osm_routing.py                # ... and replace the contents of public.osm_ways
  python scripts/load_osm_routing.py --from-cache   # never touch Overpass, use data/osm_cache only

Overpass is queried in 8 tiles, one request at a time with pauses, and every tile is cached in
data/osm_cache/ (git-ignored), so a rerun costs nothing. Tag interpretation lives in
scripts/osm_access.py. Apply the osm_ways migration first. Needs SUPABASE_DB_URL for loading.
"""

import argparse
import collections
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from _common import ROOT, database_url
from osm_access import NONE, classify

CACHE = ROOT / "data" / "osm_cache"
MIN_LAT, MIN_LON, MAX_LAT, MAX_LON = 49.967, 19.792, 50.126, 20.217  # same area as the segments import
LAT_TILES, LON_TILES = 2, 4
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
PAUSE_S = 10
BATCH = 2000

ROADS = "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified|residential|living_street|service|cycleway|path|track"


def tiles():
    dlat, dlon = (MAX_LAT - MIN_LAT) / LAT_TILES, (MAX_LON - MIN_LON) / LON_TILES
    for i in range(LAT_TILES):
        for j in range(LON_TILES):
            s, w = MIN_LAT + i * dlat, MIN_LON + j * dlon
            yield i * LON_TILES + j, f"{s:.5f},{w:.5f},{s + dlat:.5f},{w + dlon:.5f}"


def query(bbox: str) -> str:
    return (
        "[out:json][timeout:180];(\n"
        f'  way["highway"~"^({ROADS})$"]({bbox});\n'
        f'  way["highway"~"^(footway|pedestrian)$"]["bicycle"~"^(yes|designated|permissive)$"]({bbox});\n'
        f'  way["highway"="pedestrian"]({bbox});\n'  # pedestrian streets are roads for walkers
        ");out geom;"
    )


def fetch_tile(index: int, bbox: str, from_cache: bool) -> list[dict]:
    path = CACHE / f"tile_{index}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["elements"]
    if from_cache:
        sys.exit(f"missing cache file {path}")
    body = urllib.parse.urlencode({"data": query(bbox)}).encode()
    last = None
    for attempt in range(8):
        url = SERVERS[attempt % len(SERVERS)]
        try:
            req = urllib.request.Request(url, body, {"User-Agent": "RateMyRoad/0.1 (hackathon project)"})
            with urllib.request.urlopen(req, timeout=300) as response:
                raw = response.read()
            data = json.loads(raw)
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return data["elements"]
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            last = exc
            wait = 15 + 15 * attempt
            print(f"  tile {index}: {type(exc).__name__} from {url.split('/')[2]}, retry in {wait}s", flush=True)
            time.sleep(wait)
    sys.exit(f"tile {index} failed: {last}")


def length_m(coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        dx = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
        total += 6371000 * math.hypot(dx, math.radians(lat2 - lat1))
    return total


def build_rows(elements: list[dict]) -> list[dict]:
    rows = {}
    for el in elements:
        if el.get("type") != "way" or el["id"] in rows:
            continue
        tags, nodes, geometry = el.get("tags", {}), el.get("nodes", []), el.get("geometry", [])
        if "highway" not in tags or len(nodes) < 2 or len(nodes) != len(geometry) or any(g is None for g in geometry):
            continue
        attrs = classify(tags)
        if attrs is None:
            continue
        coords = [(g["lon"], g["lat"]) for g in geometry]
        rows[el["id"]] = {
            "way_id": el["id"], **attrs, "node_ids": nodes, "tags": tags,
            "wkt": "LINESTRING(" + ",".join(f"{x:.7f} {y:.7f}" for x, y in coords) + ")",
            "length_m": round(length_m(coords), 1),
        }
    return list(rows.values())


def report(rows: list[dict]) -> None:
    print(f"ways usable by cars, bikes or pedestrians: {len(rows)}")
    for mode, key in (("car", "car_dir"), ("bike", "bike_dir"), ("foot", "foot_dir")):
        used = [r for r in rows if r[key] != NONE]
        dirs = collections.Counter(r[key] for r in used)
        km = sum(r["length_m"] for r in used) / 1000
        print(f"  {mode}: {len(used)} ways, {km:.0f} km, directions {dict(dirs)}")
    by_hw = collections.Counter(r["highway"] for r in rows)
    print("  by highway:", dict(by_hw.most_common()))
    print(f"  bridges {sum(r['bridge'] for r in rows)}, tunnels {sum(r['tunnel'] for r in rows)}, "
          f"with maxspeed {sum(r['maxspeed'] is not None for r in rows)}, with surface {sum(r['surface'] is not None for r in rows)}")


INSERT = """
insert into public.osm_ways (way_id, highway, name, oneway, junction, car_dir, bike_dir, foot_dir, car_speed_kmh,
  bike_speed_kmh, foot_speed_kmh, maxspeed, surface, smoothness, lit, bridge, tunnel, layer, node_ids, geom, length_m, tags)
values (%(way_id)s, %(highway)s, %(name)s, %(oneway)s, %(junction)s, %(car_dir)s, %(bike_dir)s, %(foot_dir)s, %(car_speed_kmh)s,
  %(bike_speed_kmh)s, %(foot_speed_kmh)s, %(maxspeed)s, %(surface)s, %(smoothness)s, %(lit)s, %(bridge)s, %(tunnel)s, %(layer)s,
  %(node_ids)s, extensions.ST_SetSRID(extensions.ST_GeomFromText(%(wkt)s), 4326), %(length_m)s, %(tags)s::jsonb)
"""


def load(rows: list[dict]) -> None:
    import psycopg

    url = database_url()
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '600s'")
        conn.execute("set local search_path = public, extensions")
        conn.execute("truncate public.osm_ways")
        for i in range(0, len(rows), BATCH):
            chunk = [{**r, "tags": json.dumps(r["tags"], ensure_ascii=False)} for r in rows[i:i + BATCH]]
            with conn.cursor() as cur:
                cur.executemany(INSERT, chunk)
            print(f"  loaded {min(i + BATCH, len(rows))}/{len(rows)}", flush=True)
        count = conn.execute("select count(*) from public.osm_ways").fetchone()[0]
        assert count == len(rows), f"expected {len(rows)} rows, found {count}"
        matched = conn.execute(
            "select count(*), count(distinct s.osm_way_id) from public.segments s join public.osm_ways w on w.way_id = s.osm_way_id").fetchone()
        total = conn.execute("select count(*), count(distinct osm_way_id) from public.segments").fetchone()
        print(f"committed {count} ways; segments matched to osm_ways: {matched[0]}/{total[0]} "
              f"(ways {matched[1]}/{total[1]})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-cache", action="store_true")
    args = parser.parse_args()
    elements = []
    for index, bbox in tiles():
        cached = (CACHE / f"tile_{index}.json").exists()
        print(f"tile {index + 1}/{LAT_TILES * LON_TILES} {bbox}{' (cache)' if cached else ''}", flush=True)
        elements += fetch_tile(index, bbox, args.from_cache)
        if not cached and not args.from_cache:
            time.sleep(PAUSE_S)
    rows = build_rows(elements)
    report(rows)
    if not args.dry_run:
        load(rows)


if __name__ == "__main__":
    main()
