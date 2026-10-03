"""Build segment groups from the segments table and write them as seed SQL.

Reads segments through SUPABASE_DB_URL (read only), merges consecutive pieces of one street
into groups of about 500 m (backend/app/grouping.py) and writes:

  supabase/seed/groups_001.sql          INSERTs into public.segment_groups
  supabase/seed/groups_002.sql, ...     UPDATEs of segments.group_id

Apply the migration that creates segment_groups first. Group ids are deterministic for a given
segments table; after re-importing OSM (which shifts segment ids) truncate segment_groups and
run this script again.

  python scripts/build_segment_groups.py            # write the seed
  python scripts/build_segment_groups.py --dry-run  # statistics only
"""

import argparse
import os
import statistics
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.grouping import SegmentRow, build_groups  # noqa: E402

SEED_DIR = ROOT / "supabase" / "seed"
UPDATES_PER_FILE = 5000

QUERY = """
select id, osm_way_id, name, highway, length_m,
       round(st_x(st_startpoint(geom))::numeric, 7), round(st_y(st_startpoint(geom))::numeric, 7),
       round(st_x(st_endpoint(geom))::numeric, 7), round(st_y(st_endpoint(geom))::numeric, 7)
from public.segments order by id
"""


def sql_str(value: str | None) -> str:
    return "null" if value is None else "'" + value.replace("'", "''") + "'"


def load_segments(url: str) -> list[SegmentRow]:
    with psycopg.connect(url, connect_timeout=15) as conn:
        return [
            SegmentRow(r[0], r[1], r[2], r[3], float(r[4]), (float(r[5]), float(r[6])), (float(r[7]), float(r[8])))
            for r in conn.execute(QUERY)
        ]


def report(segments, groups) -> None:
    sizes = [g.length_m for g in groups]
    singles = sum(1 for g in groups if len(g.segment_ids) == 1)
    print(f"segments {len(segments)} -> groups {len(groups)}")
    print(f"group length m: median {statistics.median(sizes):.0f}, mean {statistics.mean(sizes):.0f}, "
          f"<100 m {sum(s < 100 for s in sizes)}, >=500 m {sum(s >= 500 for s in sizes)}, max {max(sizes):.0f}")
    print(f"groups made of a single segment: {singles}")
    total_km = sum(s.length_m for s in segments) / 1000
    short_km = sum(g.length_m for g in groups if g.length_m < 100) / 1000
    print(f"road length in groups shorter than 100 m: {short_km:.0f} of {total_km:.0f} km ({100 * short_km / total_km:.0f}%)")
    print(f"segments shorter than 100 m: {sum(s.length_m < 100 for s in segments)} -> now in groups "
          f"shorter than 100 m: {sum(len(g.segment_ids) for g in groups if g.length_m < 100)}")


def write_seed(groups) -> None:
    for old in SEED_DIR.glob("groups_*.sql"):
        old.unlink()
    rows = ",\n".join(
        f"({g.id}, {sql_str(g.name)}, {sql_str(g.highway)}, {g.length_m}, {len(g.segment_ids)}, "
        f"{sql_str(g.from_street)}, {sql_str(g.to_street)})"
        for g in groups
    )
    (SEED_DIR / "groups_001.sql").write_text(
        "insert into public.segment_groups (id, name, highway, length_m, segments_count, from_street, to_street) values\n"
        + rows + "\non conflict (id) do nothing;\n", encoding="utf-8", newline="\n")
    pairs = [(sid, g.id) for g in groups for sid in g.segment_ids]
    pairs.sort()
    for i in range(0, len(pairs), UPDATES_PER_FILE):
        chunk = ",".join(f"({s},{g})" for s, g in pairs[i:i + UPDATES_PER_FILE])
        path = SEED_DIR / f"groups_{i // UPDATES_PER_FILE + 2:03d}.sql"
        path.write_text(
            "update public.segments s set group_id = v.g from (values " + chunk + ") as v(id, g) where s.id = v.id;\n",
            encoding="utf-8", newline="\n")
    print(f"wrote {len(list(SEED_DIR.glob('groups_*.sql')))} files to {SEED_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set")
    segments = load_segments(url)
    groups = build_groups(segments)
    assert sorted(s for g in groups for s in g.segment_ids) == [s.id for s in segments], "every segment must be in one group"
    report(segments, groups)
    if not args.dry_run:
        write_seed(groups)


if __name__ == "__main__":
    main()
