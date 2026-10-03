#!/usr/bin/env python3
"""Download Krakow roads and parking from OpenStreetMap (Overpass) and write seed SQL.

Standard library only. Output goes to supabase/seed/:
  segments_001.sql, segments_002.sql, ...  (multi-row INSERTs into public.segments)
  parking.sql                               (INSERT into public.parking_spots)
  finalize.sql                              (resets the segments id sequence)

Roads: highway = primary, secondary, tertiary, unclassified, residential, cycleway.
Long ways are split into pieces of at most MAX_SEGMENT_M metres.
Segment ids are assigned deterministically (sorted by osm_way_id, then part), so
re-importing newer OSM data shifts ids: truncate segments (cascade) before reloading.

parking_spots.osm_id: OSM node id as is, OSM way id stored as a negative number.

Usage:
  python scripts/import_osm.py            # download (cached) and generate
  python scripts/import_osm.py --refresh  # ignore the cache
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "scripts" / ".cache"
SEED_DIR = ROOT / "supabase" / "seed"

# Krakow bbox from CONTRACT.md: minLon,minLat,maxLon,maxLat
MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = 19.792, 49.967, 20.217, 50.126
OVERPASS_BBOX = f"{MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON}"  # S,W,N,E

HIGHWAYS = ("primary", "secondary", "tertiary", "unclassified", "residential", "cycleway")
MAX_SEGMENT_M = 300.0
MIN_SEGMENT_M = 5.0
ROWS_PER_FILE = 2000

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "RateMyRoad-hackathon/0.1 (OSM seed import)"


def overpass(query: str, cache_name: str, refresh: bool) -> dict:
    """Run an Overpass query, caching the raw JSON under scripts/.cache/."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists() and not refresh:
        print(f"using cache {cache_file.name}")
        return json.loads(cache_file.read_text(encoding="utf-8"))

    data = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for attempt in range(3):
        for url in OVERPASS_URLS:
            try:
                print(f"POST {url} (attempt {attempt + 1})")
                req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    body = resp.read()
                result = json.loads(body)
                cache_file.write_text(json.dumps(result), encoding="utf-8")
                return result
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                print(f"  failed: {exc}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"Overpass unavailable: {last_error}")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in metres between two (lon, lat) points."""
    r = 6371008.8
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def in_bbox(p: tuple[float, float]) -> bool:
    return MIN_LON <= p[0] <= MAX_LON and MIN_LAT <= p[1] <= MAX_LAT


def split_line(points: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Split a polyline into near-equal pieces of at most MAX_SEGMENT_M metres."""
    dists = [haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(dists)
    if total <= MAX_SEGMENT_M:
        return [points]

    n = math.ceil(total / MAX_SEGMENT_M)
    target = total / n
    pieces: list[list[tuple[float, float]]] = []
    current = [points[0]]
    acc = 0.0  # length of the current piece so far
    for i, d in enumerate(dists):
        start, end = points[i], points[i + 1]
        remaining = d
        pos = 0.0  # distance already consumed on this edge
        while len(pieces) < n - 1 and acc + remaining >= target - 1e-9:
            need = target - acc
            frac = (pos + need) / d if d else 1.0
            cut = (start[0] + (end[0] - start[0]) * frac, start[1] + (end[1] - start[1]) * frac)
            current.append(cut)
            pieces.append(current)
            current = [cut]
            pos += need
            remaining -= need
            acc = 0.0
        current.append(end)
        acc += remaining
    pieces.append(current)
    return pieces


def line_length_m(points: list[tuple[float, float]]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def sql_str(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def sql_int(value: int | None) -> str:
    return "null" if value is None else str(value)


def sql_bool(value: bool | None) -> str:
    return "null" if value is None else ("true" if value else "false")


def parse_maxspeed(raw: str | None) -> int | None:
    """Plain km/h values only ("50"); mph, "walk", "none" etc. become null."""
    if raw and raw.strip().isdigit():
        return int(raw.strip())
    return None


def parse_yes_no(raw: str | None) -> bool | None:
    if raw == "yes":
        return True
    if raw == "no":
        return False
    return None


def parse_int(raw: str | None) -> int | None:
    if raw and raw.strip().isdigit():
        return int(raw.strip())
    return None


def wkt_line(points: list[tuple[float, float]]) -> str:
    coords = ", ".join(f"{lon:.7f} {lat:.7f}" for lon, lat in points)
    return f"SRID=4326;LINESTRING({coords})"


def build_segments(osm: dict) -> list[str]:
    """Return one SQL value tuple per segment, ids assigned in deterministic order."""
    ways = sorted((e for e in osm["elements"] if e["type"] == "way" and e.get("geometry")), key=lambda e: e["id"])
    rows: list[str] = []
    next_id = 1
    for way in ways:
        tags = way.get("tags", {})
        highway = tags.get("highway")
        if highway not in HIGHWAYS:
            continue
        points = [(n["lon"], n["lat"]) for n in way["geometry"] if n]
        if len(points) < 2:
            continue
        for piece in split_line(points):
            length = line_length_m(piece)
            mid = piece[len(piece) // 2]
            if length < MIN_SEGMENT_M or not in_bbox(mid):
                continue
            rows.append(
                "({id}, {way}, {name}, {hw}, {surf}, {smooth}, {speed}, {lit}, "
                "{geom}::extensions.geometry, {length:.1f})".format(
                    id=next_id,
                    way=way["id"],
                    name=sql_str(tags.get("name")),
                    hw=sql_str(highway),
                    surf=sql_str(tags.get("surface")),
                    smooth=sql_str(tags.get("smoothness")),
                    speed=sql_int(parse_maxspeed(tags.get("maxspeed"))),
                    lit=sql_bool(parse_yes_no(tags.get("lit"))),
                    geom=sql_str(wkt_line(piece)),
                    length=length,
                )
            )
            next_id += 1
    return rows


def build_parking(osm: dict) -> list[str]:
    rows: list[str] = []
    seen: set[int] = set()
    for e in osm["elements"]:
        tags = e.get("tags", {})
        if tags.get("access") in ("private", "no"):
            continue
        if e["type"] == "node":
            lon, lat, osm_id = e["lon"], e["lat"], e["id"]
        elif e["type"] == "way" and "center" in e:
            lon, lat, osm_id = e["center"]["lon"], e["center"]["lat"], -e["id"]
        else:
            continue
        if osm_id in seen or not in_bbox((lon, lat)):
            continue
        seen.add(osm_id)
        rows.append(
            "({osm_id}, {name}, {cap}, {fee}, 'SRID=4326;POINT({lon:.7f} {lat:.7f})'::extensions.geometry)".format(
                osm_id=osm_id,
                name=sql_str(tags.get("name")),
                cap=sql_int(parse_int(tags.get("capacity"))),
                fee=sql_bool(parse_yes_no(tags.get("fee"))),
                lon=lon,
                lat=lat,
            )
        )
    return rows


SEGMENTS_HEAD = (
    "insert into public.segments "
    "(id, osm_way_id, name, highway, surface_osm, smoothness_osm, maxspeed, lit, geom, length_m) values\n"
)


def write_seed(segments: list[str], parking: list[str]) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for old in SEED_DIR.glob("segments_*.sql"):
        old.unlink()

    for i in range(0, len(segments), ROWS_PER_FILE):
        chunk = segments[i : i + ROWS_PER_FILE]
        path = SEED_DIR / f"segments_{i // ROWS_PER_FILE + 1:03d}.sql"
        path.write_text(SEGMENTS_HEAD + ",\n".join(chunk) + "\non conflict (id) do nothing;\n", encoding="utf-8")

    (SEED_DIR / "parking.sql").write_text(
        "insert into public.parking_spots (osm_id, name, capacity, fee, geom) values\n"
        + ",\n".join(parking)
        + "\non conflict (osm_id) do nothing;\n",
        encoding="utf-8",
    )
    (SEED_DIR / "finalize.sql").write_text(
        "select setval(pg_get_serial_sequence('public.segments', 'id'), (select max(id) from public.segments));\n"
        "select setval(pg_get_serial_sequence('public.parking_spots', 'id'), "
        "coalesce((select max(id) from public.parking_spots), 1));\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="ignore cached Overpass responses")
    args = parser.parse_args()

    highway_re = "|".join(HIGHWAYS)
    roads = overpass(
        f'[out:json][timeout:240];way["highway"~"^({highway_re})$"]({OVERPASS_BBOX});out geom tags;',
        "roads.json",
        args.refresh,
    )
    parking = overpass(
        f'[out:json][timeout:120];nwr["amenity"="parking"]({OVERPASS_BBOX});out center tags;',
        "parking.json",
        args.refresh,
    )

    segments = build_segments(roads)
    spots = build_parking(parking)
    write_seed(segments, spots)
    print(f"segments: {len(segments)}, parking spots: {len(spots)} -> {SEED_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
