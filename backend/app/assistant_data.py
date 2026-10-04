"""Database reads for the assistant: what the data says about a route, a place or the best streets. Read-only.

Uses the views the map already uses: segment_scores (effective scores per segment) and fragment_map (one row per fragment).
"""

from . import assistant_facts as facts

MAX_STREETS = 4  # streets described per answer, longest first
MAX_COMMENTS = 3
GROUP_IDS_LIMIT = 60

# One street = all road pieces of that name; scores are length-weighted means of the pieces that have a score.
STREETS_SQL = """
SELECT coalesce(s.name, 'bez nazwy') AS name, sum(s.length_m)::float AS length_m, array_agg(s.id ORDER BY s.id) AS ids,
       sum(coalesce(ss.ratings_count, 0))::int AS ratings,
""" + ",\n".join(
    f"       round((sum(ss.{d} * s.length_m) FILTER (WHERE ss.{d} IS NOT NULL)"
    f" / NULLIF(sum(s.length_m) FILTER (WHERE ss.{d} IS NOT NULL), 0))::numeric, 2)::float AS {d}"
    for d in facts.DIMENSIONS
) + """
FROM public.segments s LEFT JOIN public.segment_scores ss ON ss.segment_id = s.id
WHERE s.id = ANY(%(ids)s)
GROUP BY 1 ORDER BY length_m DESC LIMIT %(n)s
"""

# Ranking of fragments by one dimension (column names come from the fixed list below, never from user text).
RANK_SQL = """
SELECT group_id, name, highway, length_m::float AS length_m, ratings_count AS ratings,
       surface::float, views::float, safety::float, traffic::float, parking::float,
       ST_Y(ST_ClosestPoint(geom, ST_Centroid(geom))) AS lat, ST_X(ST_ClosestPoint(geom, ST_Centroid(geom))) AS lon
FROM public.fragment_map
WHERE name IS NOT NULL AND {dim} IS NOT NULL AND ratings_count >= %(min)s{area}
ORDER BY {dim} {order}, ratings_count DESC, group_id LIMIT %(n)s
"""
AREA_SQL = " AND ST_Intersects(geom, ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n_)s, 4326))"


class AssistantData:
    """Reads through the application's connection pool (one short connection per call)."""

    def __init__(self, pool):
        self.pool = pool

    def nearest_segment(self, lat: float, lon: float, max_m: float = 80) -> dict | None:
        """The road piece closest to a point within `max_m` metres, or None."""
        with self.pool.connection() as conn:
            return conn.execute("""
                SELECT s.id, s.name, s.group_id FROM public.segments s
                WHERE ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(m)s)
                ORDER BY s.geom::geography <-> ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, s.id LIMIT 1
            """, {"lat": lat, "lon": lon, "m": max_m}).fetchone()

    def group_segment_ids(self, group_id: int) -> list[int]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id FROM public.segments WHERE group_id = %s ORDER BY id LIMIT %s", (group_id, GROUP_IDS_LIMIT)).fetchall()
        return [r["id"] for r in rows]

    def segment_facts(self, segment_ids: list[int], on_route: bool = True) -> list[str]:
        """Sentences about the streets those road pieces form: scores in words, the newest comments, the AI summary, obstacles.

        `on_route`: the pieces are a route (lengths are phrased as parts of it) rather than a place or a fragment.
        """
        if not segment_ids:
            return []
        with self.pool.connection() as conn:
            streets = conn.execute(STREETS_SQL, {"ids": segment_ids, "n": MAX_STREETS}).fetchall()
            comments = conn.execute("""
                SELECT c.created_at::date AS day, c.text FROM public.comments c
                WHERE c.segment_id = ANY(%s) AND c.status = 'visible' ORDER BY c.created_at DESC LIMIT %s
            """, (segment_ids, MAX_COMMENTS)).fetchall()
            summary = conn.execute(
                "SELECT summary->>'overall' AS overall FROM public.segment_summaries WHERE segment_id = ANY(%s) ORDER BY updated_at DESC LIMIT 1",
                (segment_ids,)).fetchone()
            obstacles = conn.execute("""
                SELECT type::text AS kind, description, valid_until FROM public.obstacles
                WHERE segment_id = ANY(%s) AND (valid_until IS NULL OR valid_until > now()) ORDER BY created_at DESC LIMIT 5
            """, (segment_ids,)).fetchall()
        named = [s for s in streets if s["name"] != facts.UNNAMED]
        lines = [facts.street_fact(s, on_route) for s in (named or streets)]  # nameless pieces only when there is nothing else
        if summary and summary["overall"]:
            lines.append(facts.summary_fact(summary["overall"]))
        lines += [facts.comment_fact(c["day"], c["text"]) for c in comments]
        lines += [facts.obstacle_fact(o["kind"], o["description"], o["valid_until"]) for o in obstacles]
        return lines

    def top_fragments(self, dimension: str, want: str, bbox: tuple[float, float, float, float] | None, count: int) -> list[dict]:
        """Fragments with the best (or worst) score for one dimension, optionally inside a box (west, south, east, north).

        Fragments rated by at least two people come first; when there are too few of them, those with a single rating fill up.
        """
        if dimension not in facts.DIMENSIONS:
            raise ValueError(dimension)
        sql = RANK_SQL.format(dim=dimension, order="DESC" if want == "best" else "ASC", area=AREA_SQL if bbox else "")
        params = {"n": count}
        if bbox:
            params |= {"w": bbox[0], "s": bbox[1], "e": bbox[2], "n_": bbox[3]}
        with self.pool.connection() as conn:
            rows = conn.execute(sql, {**params, "min": 2}).fetchall()
            if len(rows) < count:
                rows = conn.execute(sql, {**params, "min": 1}).fetchall()
        return rows
