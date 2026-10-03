"""Parameterized core queries against the schema owned by B2; no schema changes."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from .errors import AppError
from .schemas import DIMENSIONS, RatingCreate, TimeOfDay

# Aggregate live ratings so a newly submitted score appears immediately. The
# materialized segment_stats view remains available to routing and B2's refresh job.
SEGMENT_SELECT = """
SELECT s.id, s.osm_way_id, s.name, s.highway, s.length_m,
       s.surface_osm, s.smoothness_osm, s.maxspeed, s.lit,
       ST_AsGeoJSON(s.geom)::jsonb AS geometry,
       jsonb_build_object('surface', r.surface, 'views', r.views,
         'safety', r.safety, 'traffic', r.traffic, 'parking', r.parking) AS scores,
       r.ratings_count, r.last_rating_at,
       (SELECT count(*) FROM public.obstacles o WHERE o.segment_id = s.id
         AND (o.valid_until IS NULL OR o.valid_until > now()))::int AS active_obstacles_count
FROM public.segments s
LEFT JOIN LATERAL (
    SELECT round(avg(surface), 2) AS surface, round(avg(views), 2) AS views,
           round(avg(safety), 2) AS safety, round(avg(traffic), 2) AS traffic,
           round(avg(parking), 2) AS parking, count(*)::int AS ratings_count,
           max(created_at) AS last_rating_at
    FROM public.ratings WHERE segment_id = s.id
) r ON true
"""

RATING_COLUMNS = "id, segment_id, surface, views, safety, traffic, parking, time_of_day, created_at"
COMMENT_SELECT = """
SELECT c.id, c.segment_id, c.text, c.status, c.created_at,
       jsonb_build_object('id', p.id, 'display_name', p.display_name) AS author
FROM public.comments c JOIN public.profiles p ON p.id = c.user_id
"""


def time_of_day(now: datetime) -> TimeOfDay:
    """Assign the contract's time band using Warsaw local time, including DST."""
    hour = now.astimezone(ZoneInfo("Europe/Warsaw")).hour
    if 6 <= hour < 10:
        return TimeOfDay.morning
    if 10 <= hour < 16:
        return TimeOfDay.day
    if 16 <= hour < 22:
        return TimeOfDay.evening
    return TimeOfDay.night


class Repository:
    """Request-scoped transactional access to core data."""

    def __init__(self, conn):
        self.conn = conn

    def require_segment(self, segment_id: int) -> None:
        """Raise NOT_FOUND rather than leaking a foreign key violation."""
        if not self.conn.execute("SELECT id FROM public.segments WHERE id = %s", (segment_id,)).fetchone():
            raise AppError(404, "NOT_FOUND", "Nie znaleziono odcinka")

    def profile(self, user):
        """Return a verified user's profile without accepting client-supplied roles."""
        row = self.conn.execute("SELECT id, display_name, created_at FROM public.profiles WHERE id = %s", (user.id,)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono profilu")
        return {**row, "email": user.email, "role": user.role}

    def segments(self, bbox, dimension=None, min_score=None, rated_only=False):
        """Return at most 2000 intersecting features, rejecting oversized results."""
        conditions = ["s.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)",
                      "ST_Intersects(s.geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"]
        params = [*bbox, *bbox]
        if rated_only:
            conditions.append("r.ratings_count > 0")
        if min_score is not None:
            # Only enum-controlled identifiers enter the SQL, never raw input.
            if dimension not in DIMENSIONS:
                raise AppError(422, "VALIDATION_ERROR", "min_score wymaga dimension")
            conditions.append(f"r.{dimension} >= %s")
            params.append(min_score)
        rows = self.conn.execute(SEGMENT_SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY s.id LIMIT 2001", params).fetchall()
        if len(rows) > 2000:
            raise AppError(422, "VALIDATION_ERROR", "Przybliż mapę: maksymalnie 2000 odcinków")
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": row["geometry"], "properties": row} for row in rows
        ]}

    def nearest(self, lat: float, lon: float):
        """Find a road within 50 metres with geography distances in metres."""
        row = self.conn.execute(
            SEGMENT_SELECT.replace("SELECT s.id", "SELECT ST_Distance(s.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS distance_m, s.id", 1)
            + " WHERE ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 50) ORDER BY distance_m, s.id LIMIT 1",
            (lon, lat, lon, lat),
        ).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Brak odcinka w promieniu 50 m")
        return row

    def segment(self, segment_id: int, user_id: UUID | None = None):
        """Read detail, live scores, visible content and today's own rating."""
        row = self.conn.execute(SEGMENT_SELECT + " WHERE s.id = %s", (segment_id,)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono odcinka")
        bands = {band.value: dict.fromkeys(DIMENSIONS) for band in TimeOfDay}
        for band in self.conn.execute("""
            SELECT time_of_day, round(avg(surface), 2) AS surface, round(avg(views), 2) AS views,
                   round(avg(safety), 2) AS safety, round(avg(traffic), 2) AS traffic,
                   round(avg(parking), 2) AS parking
            FROM public.ratings WHERE segment_id = %s GROUP BY time_of_day
        """, (segment_id,)).fetchall():
            bands[band["time_of_day"]] = {key: band[key] for key in DIMENSIONS}
        row["scores_by_time_of_day"] = bands
        cached = self.conn.execute("SELECT summary, comments_count, model, updated_at FROM public.segment_summaries WHERE segment_id = %s", (segment_id,)).fetchone()
        row["summary"] = ({**cached["summary"], "comments_count": cached["comments_count"],
                           "model": cached["model"], "updated_at": cached["updated_at"]} if cached else None)
        row["obstacles"] = self.conn.execute("""
            SELECT id, segment_id, type, description, valid_until, reported_by, created_at,
                   jsonb_build_object('lat', ST_Y(geom), 'lon', ST_X(geom)) AS location
            FROM public.obstacles WHERE segment_id = %s AND (valid_until IS NULL OR valid_until > now())
            ORDER BY created_at DESC, id DESC
        """, (segment_id,)).fetchall()
        row["photos_count"] = self.conn.execute("SELECT count(*)::int AS count FROM public.segment_photos WHERE segment_id = %s AND status = 'visible'", (segment_id,)).fetchone()["count"]
        row["my_rating"] = None
        if user_id:
            row["my_rating"] = self.conn.execute(
                f"SELECT {RATING_COLUMNS} FROM public.ratings WHERE segment_id = %s AND user_id = %s AND rated_on = (now() AT TIME ZONE 'Europe/Warsaw')::date",
                (segment_id, user_id),
            ).fetchone()
        return row

    def rate(self, segment_id: int, user_id: UUID, payload: RatingCreate, now: datetime):
        """Atomically replace the same user's daily rating and report 201 or 200."""
        self.require_segment(segment_id)
        local_date = now.astimezone(ZoneInfo("Europe/Warsaw")).date()
        # Serialize same-user/segment writes, including the first INSERT.
        self.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s), %s)", (str(user_id), segment_id))
        previous = self.conn.execute("SELECT id FROM public.ratings WHERE user_id = %s AND segment_id = %s AND rated_on = %s", (user_id, segment_id, local_date)).fetchone()
        row = self.conn.execute(f"""
            INSERT INTO public.ratings (user_id, segment_id, rated_on, surface, views, safety, traffic, parking, time_of_day, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, segment_id, rated_on) DO UPDATE SET
                surface = excluded.surface, views = excluded.views, safety = excluded.safety,
                traffic = excluded.traffic, parking = excluded.parking,
                time_of_day = excluded.time_of_day, created_at = excluded.created_at
            RETURNING {RATING_COLUMNS}
        """, (user_id, segment_id, local_date, *(getattr(payload, key) for key in DIMENSIONS),
                (payload.time_of_day or time_of_day(now)).value, now)).fetchone()
        return row, previous is None

    def comments(self, segment_id: int, page: int, page_size: int):
        """List visible comments only, with stable ordering and an accurate total."""
        self.require_segment(segment_id)
        total = self.conn.execute("SELECT count(*)::int AS count FROM public.comments WHERE segment_id = %s AND status = 'visible'", (segment_id,)).fetchone()["count"]
        items = self.conn.execute(COMMENT_SELECT + " WHERE c.segment_id = %s AND c.status = 'visible' ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s", (segment_id, page_size, (page - 1) * page_size)).fetchall()
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def comment(self, segment_id: int, user_id: UUID, text: str):
        """Insert a comment authored by the verified identity, never a request ID."""
        self.require_segment(segment_id)
        row = self.conn.execute("INSERT INTO public.comments (segment_id, user_id, text) VALUES (%s, %s, %s) RETURNING id", (segment_id, user_id, text)).fetchone()
        return self.conn.execute(COMMENT_SELECT + " WHERE c.id = %s", (row["id"],)).fetchone()

    def moderate_comment(self, comment_id: UUID, status: str):
        """Update visibility after the router has verified administrator access."""
        row = self.conn.execute("UPDATE public.comments SET status = %s WHERE id = %s RETURNING id", (status, comment_id)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono komentarza")
        # Cached summaries may contain text from a now-hidden comment.
        self.conn.execute("DELETE FROM public.segment_summaries WHERE segment_id = (SELECT segment_id FROM public.comments WHERE id = %s)", (comment_id,))
        return self.conn.execute(COMMENT_SELECT + " WHERE c.id = %s", (comment_id,)).fetchone()
