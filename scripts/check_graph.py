"""Connectivity check of the road graph (read only, via SUPABASE_DB_URL).

  python scripts/check_graph.py                       # graph implied by public.segments endpoints
  python scripts/check_graph.py --edges routing_edges # a built edge table with source/target columns
  python scripts/check_graph.py --osm-ways car        # network in public.osm_ways joined by OSM node ids (car|bike)

Prints the connected components and the share of the largest one. Router tests should expect
one dominant component; many small ones mean missing junction nodes. In the segments mode it also
counts dead ends that sit on the interior of another segment (T-junctions without a node) and
how much connectivity adding them would give: the measure of what the noding step must fix.

Needs: pip install "psycopg[binary]" shapely
"""

import argparse
import collections
import re
import sys

import psycopg
from _common import database_url

NODE_EPS = 0.000003  # about 0.3 m in degrees


class DSU:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def report(title, dsu, edge_ends):
    comp = collections.Counter(dsu.find(a) for a, _ in edge_ends)
    sizes = sorted(comp.values(), reverse=True)
    total = sum(sizes)
    small = [s for s in sizes if s < 10]
    print(f"{title}: {total} edges, {len(sizes)} components, largest {sizes[0]} = {100 * sizes[0] / total:.1f}%, "
          f"{len(small)} components under 10 edges covering {sum(small)} edges")
    return sizes


def from_edges(conn, table):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
        sys.exit("bad table name")
    rows = conn.execute(f"select source, target from public.{table}").fetchall()  # noqa: S608 (validated)
    dsu = DSU()
    for a, b in rows:
        dsu.union(a, b)
    report(f"public.{table}", dsu, rows)


def from_osm_ways(conn, mode):
    """Undirected connectivity of the ways a profile may use: consecutive OSM nodes are linked.

    Directions are ignored here (one-way streets can make a node reachable but not leavable), so
    this is the upper bound a directed router can reach. Components are measured in km of way length.
    """
    column = {"car": "car_dir", "bike": "bike_dir"}[mode]
    rows = conn.execute(f"select way_id, node_ids, length_m from public.osm_ways where {column} <> 'none'").fetchall()  # noqa: S608
    dsu = DSU()
    for _way, nodes, _length in rows:
        for a, b in zip(nodes, nodes[1:]):
            dsu.union(a, b)
    comp_ways, comp_km = collections.Counter(), collections.Counter()
    for _way, nodes, length in rows:
        root = dsu.find(nodes[0])
        comp_ways[root] += 1
        comp_km[root] += length / 1000
    ways = sorted(comp_ways.values(), reverse=True)
    km = sorted(comp_km.values(), reverse=True)
    total_km = sum(km)
    small = [k for k in km if k < 1]
    print(f"{mode}: {len(rows)} ways, {total_km:.0f} km, {len(ways)} components; largest {ways[0]} ways = "
          f"{km[0]:.0f} km = {100 * km[0] / total_km:.1f}% of the length; "
          f"{len(small)} components under 1 km covering {sum(small):.0f} km")
    return rows


def from_segments(conn):
    from shapely import wkt
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    rows = conn.execute("select id, st_astext(geom) from public.segments").fetchall()
    geoms = {r[0]: wkt.loads(r[1]) for r in rows}

    def key(p):
        return (round(p[0], 7), round(p[1], 7))

    ends = {i: (key(g.coords[0]), key(g.coords[-1])) for i, g in geoms.items()}
    dsu, degree = DSU(), collections.Counter()
    for a, b in ends.values():
        dsu.union(a, b)
        degree[a] += 1
        degree[b] += 1
    report("segments as they are", dsu, list(ends.values()))

    tree, ids = STRtree(list(geoms.values())), list(geoms)
    dangling = [n for n, d in degree.items() if d == 1]
    missing = 0
    for n in dangling:
        pt = Point(n)
        for idx in tree.query(pt.buffer(NODE_EPS)):
            j = ids[idx]
            g = geoms[j]
            if g.distance(pt) < NODE_EPS and ends[j][0] != n and ends[j][1] != n:
                missing += 1
                dsu.union(n, ends[j][0])
                dsu.union(ends[j][1], ends[j][0])
                break
    print(f"dead ends {len(dangling)}, of which on the interior of another segment: {missing}")
    report("after adding those junction nodes", dsu, list(ends.values()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges", help="edge table in public with integer source/target columns")
    parser.add_argument("--osm-ways", choices=["car", "bike"], help="connectivity of the osm_ways network for a profile")
    args = parser.parse_args()
    url = database_url()
    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.read_only = True
        if args.osm_ways:
            from_osm_ways(conn, args.osm_ways)
        elif args.edges:
            from_edges(conn, args.edges)
        else:
            from_segments(conn)


if __name__ == "__main__":
    main()
