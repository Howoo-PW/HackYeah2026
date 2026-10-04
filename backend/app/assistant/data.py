"""Database reads for the assistant: what the data says about a route, a place or the best streets. Read-only.

Uses the views the map already uses: segment_scores (effective scores per segment) and fragment_map (one row per fragment).
"""

import json

from . import facts

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
AREA_SQL = " AND geom && ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n_)s, 4326)"
# with the real outline of a district: a fragment counts when its representative point lies inside it
OUTLINE_SQL = " AND ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(%(outline)s), 4326), ST_ClosestPoint(geom, ST_Centroid(geom)))"


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

    def comments_by_meaning(self, vector_text: str, bbox: tuple[float, float, float, float] | None, outline: dict | None,
                            count: int, min_similarity: float) -> list[dict]:
        """Fragments whose visible comments are closest in meaning to the query vector (pgvector text form), best first.

        One row per fragment: its scores, location and up to three of its best-matching comments. Inside a box and/or an outline when given.
        """
        area = (" AND s.geom && ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n_)s, 4326)" if bbox else "") + \
               (" AND ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(%(outline)s), 4326), ST_Centroid(s.geom))" if outline else "")
        params: dict = {"q": vector_text, "min": min_similarity, "n": count}
        if bbox:
            params |= {"w": bbox[0], "s": bbox[1], "e": bbox[2], "n_": bbox[3]}
        if outline:
            params["outline"] = json.dumps(outline)
        sql = f"""
            WITH hits AS (
                SELECT s.group_id, c.text, 1 - (e.embedding <=> %(q)s::extensions.vector) AS sim
                FROM public.comment_embeddings e
                JOIN public.comments c ON c.id = e.comment_id AND c.status = 'visible'
                JOIN public.segments s ON s.id = c.segment_id
                WHERE s.group_id IS NOT NULL{area}
                ORDER BY e.embedding <=> %(q)s::extensions.vector LIMIT 200
            ), best AS (
                SELECT group_id, max(sim) AS sim, count(*) AS hits,
                       (array_agg(text ORDER BY sim DESC))[1:3] AS texts
                FROM hits WHERE sim >= %(min)s GROUP BY group_id
            )
            SELECT f.group_id, f.name, f.highway, f.length_m::float AS length_m, f.ratings_count AS ratings,
                   f.surface::float, f.views::float, f.safety::float, f.traffic::float, f.parking::float,
                   ST_Y(ST_ClosestPoint(f.geom, ST_Centroid(f.geom))) AS lat, ST_X(ST_ClosestPoint(f.geom, ST_Centroid(f.geom))) AS lon,
                   b.sim::float AS similarity, b.texts
            FROM best b JOIN public.fragment_map f ON f.group_id = b.group_id
            WHERE f.name IS NOT NULL
            ORDER BY b.sim DESC, b.hits DESC LIMIT %(n)s
        """
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def river_points(self) -> list[tuple[str, float, float]]:
        """Points along the embankment paths ("Bulwar ...", not on bridges): name, lat, lon. Three per way, so a long bank is covered."""
        with self.pool.connection() as conn:
            rows = conn.execute("""
                SELECT w.name, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon
                FROM public.osm_ways w
                CROSS JOIN LATERAL (SELECT ST_LineInterpolatePoint(w.geom, f) AS geom FROM unnest(ARRAY[0.2, 0.5, 0.8]) AS f) p
                WHERE w.name ILIKE 'Bulwar %%' AND coalesce(w.bridge, 'no') = 'no'
            """).fetchall()
        return [(r["name"], r["lat"], r["lon"]) for r in rows]

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

    def top_fragments(self, dimension: str, want: str, bbox: tuple[float, float, float, float] | None, count: int,
                      outline: dict | None = None) -> list[dict]:
        """Fragments with the best (or worst) score for one dimension, optionally inside a box (west, south, east, north)
        and, when `outline` (GeoJSON) is given, only those lying inside that area.

        Fragments rated by at least two people come first; when there are too few of them, those with a single rating fill up.
        """
        if dimension not in facts.DIMENSIONS:
            raise ValueError(dimension)
        area = (AREA_SQL if bbox else "") + (OUTLINE_SQL if outline else "")
        sql = RANK_SQL.format(dim=dimension, order="DESC" if want == "best" else "ASC", area=area)
        params = {"n": count}
        if bbox:
            params |= {"w": bbox[0], "s": bbox[1], "e": bbox[2], "n_": bbox[3]}
        if outline:
            params["outline"] = json.dumps(outline)
        with self.pool.connection() as conn:
            rows = conn.execute(sql, {**params, "min": 2}).fetchall()
            if len(rows) < count:
                rows = conn.execute(sql, {**params, "min": 1}).fetchall()
        return rows
