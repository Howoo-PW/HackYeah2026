"""Build rating fragments (segment_groups) from the segments table.

Reads segments through SUPABASE_DB_URL (read only), merges them into fragments of 300-700 m
(backend/app/grouping.py: cut only at junctions with important roads, shorter pieces merged into
a neighbour) and writes:

  supabase/seed/groups_001.sql          INSERTs into public.segment_groups
  supabase/seed/groups_002.sql, ...     UPDATEs of segments.group_id

The routing graph (routing_edges) is NOT changed: it stays fine-grained so that every junction
can be turned at. Edges reach fragments through segment_id (view routing_edge_group).

  python scripts/build_segment_groups.py            # write the seed
  python scripts/build_segment_groups.py --dry-run  # statistics only
  python scripts/build_segment_groups.py --apply    # write the seed AND replace the fragments in the
                                                    # database (one transaction), then refresh scores

Fragment ids are deterministic for a given segments table; after re-importing OSM (which shifts
segment ids) run this script again.
"""

import argparse
import collections
import os
import statistics
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.grouping import IMPORTANT_HIGHWAYS, SegmentRow, build_fragments  # noqa: E402

SEED_DIR = ROOT / "supabase" / "seed"
UPDATES_PER_FILE = 5000
EPS = 0.000005  # about 0.5 m in degrees

QUERY = """
select id, osm_way_id, name, highway, length_m,
       round(st_x(st_startpoint(geom))::numeric, 7), round(st_y(st_startpoint(geom))::numeric, 7),
       round(st_x(st_endpoint(geom))::numeric, 7), round(st_y(st_endpoint(geom))::numeric, 7)
from public.segments order by id
"""

# An end of one segment lies on the other: end-to-end joins and T-junctions, but not a bridge crossing.
NEIGHBORS = f"""
select a.id, b.id from public.segments a join public.segments b
  on b.id <> a.id and st_dwithin(st_startpoint(a.geom), b.geom, {EPS})
union
select a.id, b.id from public.segments a join public.segments b
  on b.id <> a.id and st_dwithin(st_endpoint(a.geom), b.geom, {EPS})
"""

# Nodes (segment ends) that lie on a segment of an important road.
IMPORTANT_AT = f"""
with nodes as (
  select st_startpoint(geom) p from public.segments union select st_endpoint(geom) from public.segments
)
select round(st_x(n.p)::numeric, 7), round(st_y(n.p)::numeric, 7), array_agg(s.id)
from nodes n join public.segments s
  on s.highway = any(%s) and st_dwithin(n.p, s.geom, {EPS})
group by 1, 2
"""


def sql_str(value: str | None) -> str:
    return "null" if value is None else "'" + value.replace("'", "''") + "'"


def load(conn):
    segments = [
        SegmentRow(r[0], r[1], r[2], r[3], float(r[4]), (float(r[5]), float(r[6])), (float(r[7]), float(r[8])))
        for r in conn.execute(QUERY)
    ]
    neighbors: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in conn.execute(NEIGHBORS):
        neighbors[a].add(b)
        neighbors[b].add(a)
    important_at = {(float(x), float(y)): set(ids) for x, y, ids in conn.execute(IMPORTANT_AT, (sorted(IMPORTANT_HIGHWAYS),))}
    return segments, neighbors, important_at


def report(segments, groups) -> None:
    sizes = [g.length_m for g in groups]
    total_km = sum(s.length_m for s in segments) / 1000
    print(f"segments {len(segments)} -> fragments {len(groups)}")
    print(f"fragment length m: median {statistics.median(sizes):.0f}, mean {statistics.mean(sizes):.0f}, "
          f"max {max(sizes):.0f}, in 300-700 m: {sum(300 <= s <= 700 for s in sizes)}")
    for limit in (100, 300):
        km = sum(s for s in sizes if s < limit) / 1000
        print(f"road length in fragments shorter than {limit} m: {km:.0f} of {total_km:.0f} km ({100 * km / total_km:.1f}%), "
              f"{sum(s < limit for s in sizes)} fragments")
    print(f"fragments made of a single segment: {sum(len(g.segment_ids) == 1 for g in groups)}, "
          f"with a named street: {sum(g.name is not None for g in groups)}")


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
    pairs = sorted((sid, g.id) for g in groups for sid in g.segment_ids)
    for i in range(0, len(pairs), UPDATES_PER_FILE):
        chunk = ",".join(f"({s},{g})" for s, g in pairs[i:i + UPDATES_PER_FILE])
        path = SEED_DIR / f"groups_{i // UPDATES_PER_FILE + 2:03d}.sql"
        path.write_text(
            "update public.segments s set group_id = v.g from (values " + chunk + ") as v(id, g) where s.id = v.id;\n",
            encoding="utf-8", newline="\n")
    print(f"wrote {len(list(SEED_DIR.glob('groups_*.sql')))} files to {SEED_DIR}")


def apply(url: str, groups, n_segments: int) -> None:
    """Replace the fragments in one transaction: old ones deleted, new seed loaded, scores refreshed."""
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '600s'")
        conn.execute("set local search_path = public, extensions")
        conn.execute("update public.segments set group_id = null")
        conn.execute("delete from public.segment_groups")
        for f in sorted(SEED_DIR.glob("groups_*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
        total, grouped = conn.execute("select count(*), count(group_id) from public.segments").fetchone()
        n_groups = conn.execute("select count(*) from public.segment_groups").fetchone()[0]
        empty = conn.execute("select count(*) from public.segment_groups g where not exists "
                             "(select 1 from public.segments s where s.group_id = g.id)").fetchone()[0]
        wrong = conn.execute("select count(*) from public.segment_groups g where g.segments_count <> "
                             "(select count(*) from public.segments s where s.group_id = g.id)").fetchone()[0]
        print(f"in transaction: segments {total}, grouped {grouped}, fragments {n_groups}, empty {empty}, wrong counts {wrong}")
        assert total == grouped == n_segments and n_groups == len(groups) and empty == 0 and wrong == 0, "inconsistent, rolling back"
        for view in ("segment_scores", "fragment_map", "routing_graph"):  # in dependency order
            if conn.execute("select to_regclass(%s)", (f"public.{view}",)).fetchone()[0]:
                conn.execute(f"refresh materialized view public.{view}")  # noqa: S608 (fixed names)
        scored = conn.execute("select count(*) from public.segment_scores").fetchone()[0]
        conn.commit()
        print(f"committed; segment_scores rows: {scored}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set")
    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.execute("set statement_timeout = '300s'")
        segments, neighbors, important_at = load(conn)
    groups = build_fragments(segments, neighbors, important_at)
    assert sorted(s for g in groups for s in g.segment_ids) == [s.id for s in segments], "every segment must be in one fragment"
    report(segments, groups)
    if not args.dry_run:
        write_seed(groups)
        if args.apply:
            apply(url, groups, len(segments))


if __name__ == "__main__":
    main()
