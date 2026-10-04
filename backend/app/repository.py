"""Parameterized core queries against the schema owned by B2; no schema changes."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from .errors import AppError
from .grouping import effective_scores, group_scores
from . import summaries
from .schemas import DIMENSIONS, RatingCreate, TimeOfDay

def _agg(alias: str = "") -> str:
    """SQL for {dimension: [ratings count, sum]}; the raw material of every score computed below."""
    col = f"{alias}." if alias else ""
    return "jsonb_build_object(" + ", ".join(
        f"'{d}', jsonb_build_array(count({col}{d}), coalesce(sum({col}{d}), 0))" for d in DIMENSIONS) + ")"


# Live aggregates, so a newly submitted score appears immediately. Each segment gets its own
# ratings, those of its whole group and the mean of its road type; grouping.effective_scores
# combines them. The materialized segment_stats view stays available to B2's refresh job.
SEGMENT_SELECT = f"""
WITH hw AS (
    SELECT s4.highway, {_agg("r4")} AS agg
    FROM public.ratings r4 JOIN public.segments s4 ON s4.id = r4.segment_id GROUP BY s4.highway
)
SELECT s.id, s.osm_way_id, s.name, s.highway, s.length_m,
       s.surface_osm, s.smoothness_osm, s.maxspeed, s.lit,
       ST_AsGeoJSON(s.geom)::jsonb AS geometry,
       o.agg AS own_agg, o.ratings_count, o.last_rating_at,
       gr.agg AS group_agg, gr.ratings_count AS group_ratings_count,
       hw.agg AS highway_agg,
       CASE WHEN g.id IS NULL THEN NULL ELSE jsonb_build_object(
         'id', g.id, 'name', g.name, 'highway', g.highway, 'length_m', g.length_m,
         'segments_count', g.segments_count, 'from_street', g.from_street, 'to_street', g.to_street,
         'ratings_count', 0) END AS group_info,
       (SELECT count(*) FROM public.obstacles ob WHERE ob.segment_id = s.id
         AND (ob.valid_until IS NULL OR ob.valid_until > now()))::int AS active_obstacles_count
FROM public.segments s
LEFT JOIN public.segment_groups g ON g.id = s.group_id
LEFT JOIN hw ON hw.highway = s.highway
LEFT JOIN LATERAL (
    SELECT {_agg()} AS agg, count(*)::int AS ratings_count, max(created_at) AS last_rating_at
    FROM public.ratings WHERE segment_id = s.id
) o ON true
LEFT JOIN LATERAL (
    SELECT {_agg("r3")} AS agg, count(*)::int AS ratings_count
    FROM public.ratings r3 JOIN public.segments s3 ON s3.id = r3.segment_id
    WHERE s3.group_id = s.group_id
) gr ON true
"""


def enrich_segment(row: dict) -> dict:
    """Turn the raw aggregates of one SEGMENT_SELECT row into the contract's score fields."""
    own, group, highway = row.pop("own_agg"), row.pop("group_agg"), row.pop("highway_agg") or {}
    group_ratings = row.pop("group_ratings_count") or 0
    group_info = row.pop("group_info")
    scores, source, confidence = effective_scores(own, group if group_info else own, highway)
    row["scores"], row["scores_source"], row["confidence"] = scores, source, confidence
    row["scores_own"] = {d: (round(own[d][1] / own[d][0], 2) if own[d][0] else None) for d in DIMENSIONS}
    row["group"] = {**group_info, "ratings_count": group_ratings} if group_info else None
    return row


RATING_COLUMNS = "id, segment_id, surface, views, safety, traffic, parking, time_of_day, created_at"
PHOTO_SELECT = "SELECT id, segment_id, storage_path, thumbnail_path, taken_at, status, created_at FROM public.segment_photos"
COMMENT_SELECT = """
SELECT c.id, c.segment_id, c.text, c.status, c.created_at,
       jsonb_build_object('id', p.id, 'display_name', p.display_name) AS author,
       CASE WHEN r.id IS NULL THEN NULL ELSE to_jsonb(r) END AS rating
FROM public.comments c JOIN public.profiles p ON p.id = c.user_id
-- The author's latest rating of the same road, shown as stars next to the comment.
LEFT JOIN LATERAL (
    SELECT id, segment_id, surface, views, safety, traffic, parking, time_of_day, created_at
    FROM public.ratings WHERE user_id = c.user_id AND segment_id = c.segment_id
    ORDER BY created_at DESC LIMIT 1
) r ON true
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
        """Return at most 2000 intersecting features, rejecting oversized results.

        `rated_only` and `min_score` apply to the effective score, so a segment with no ratings of
        its own still passes when its group was rated. They filter after the 2000-feature limit.
        """
        if min_score is not None and dimension not in DIMENSIONS:
            raise AppError(422, "VALIDATION_ERROR", "min_score wymaga dimension")
        rows = self.conn.execute(
            SEGMENT_SELECT + " WHERE s.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"
            " AND ST_Intersects(s.geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326)) ORDER BY s.id LIMIT 2001",
            [*bbox, *bbox]).fetchall()
        if len(rows) > 2000:
            raise AppError(422, "VALIDATION_ERROR", "Przybliż mapę: maksymalnie 2000 odcinków")
        rows = [enrich_segment(row) for row in rows]
        if rated_only:
            rows = [row for row in rows if row["scores_source"] != "none"]
        if min_score is not None:
            rows = [row for row in rows if (row["scores"][dimension] or 0) >= min_score]
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": row["geometry"], "properties": row} for row in rows
        ]}

    def group_map(self, bbox, dimension=None, min_score=None, rated_only=False):
        """Fragments in the viewport for zoomed-out maps (view fragment_map): the whole city is about 5 000."""
        if min_score is not None and dimension not in DIMENSIONS:
            raise AppError(422, "VALIDATION_ERROR", "min_score wymaga dimension")
        conditions = ["geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"]
        params = [*bbox]
        if rated_only:
            conditions.append("source <> 'none'")
        if min_score is not None:
            conditions.append(f"{dimension} >= %s")  # dimension is validated against DIMENSIONS above
            params.append(min_score)
        rows = self.conn.execute(
            "SELECT group_id AS id, name, highway, length_m, segments_count, ratings_count, source AS scores_source, "
            "surface, views, safety, traffic, parking, ST_AsGeoJSON(geom, 5)::jsonb AS geometry "
            "FROM public.fragment_map WHERE " + " AND ".join(conditions) + " ORDER BY group_id LIMIT 6001", params).fetchall()
        if len(rows) > 6000:
            raise AppError(422, "VALIDATION_ERROR", "Przybliż mapę: maksymalnie 6000 fragmentów")
        features = []
        for row in rows:
            geometry = row.pop("geometry")
            row["scores"] = {d: (round(row.pop(d), 2) if row[d] is not None else row.pop(d)) for d in DIMENSIONS}
            features.append({"type": "Feature", "geometry": geometry, "properties": row})
        return {"type": "FeatureCollection", "features": features}

    def nearest(self, lat: float, lon: float):
        """Find a road within 50 metres with geography distances in metres."""
        row = self.conn.execute(
            SEGMENT_SELECT.replace("SELECT s.id", "SELECT ST_Distance(s.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS distance_m, s.id", 1)
            + " WHERE ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 50) ORDER BY distance_m, s.id LIMIT 1",
            (lon, lat, lon, lat),
        ).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Brak odcinka w promieniu 50 m")
        return enrich_segment(row)

    def street(self, segment_id: int):
        """The whole street the road belongs to: every road with the same name that is joined to it end to end.

        Streets are cut into stretches (groups) that also pick up side streets, so the street is followed on the road graph itself:
        from the clicked road to neighbours that have the same name and share an end point, and so on.
        """
        self.require_segment(segment_id)
        row = self.conn.execute("""
            WITH RECURSIVE named AS (
                SELECT id, length_m, ST_SnapToGrid(ST_StartPoint(geom), 0.0000001) AS a, ST_SnapToGrid(ST_EndPoint(geom), 0.0000001) AS b
                FROM public.segments WHERE name = (SELECT name FROM public.segments WHERE id = %(s)s) AND name IS NOT NULL
            ), walk(id) AS (
                SELECT id FROM named WHERE id = %(s)s
                UNION
                SELECT n.id FROM walk w JOIN named m ON m.id = w.id
                JOIN named n ON n.a IN (m.a, m.b) OR n.b IN (m.a, m.b)
            )
            SELECT (SELECT name FROM public.segments WHERE id = %(s)s) AS name,
                   coalesce(array_agg(w.id ORDER BY w.id), ARRAY[%(s)s]) AS segment_ids,
                   coalesce(sum(n.length_m), 0)::float AS length_m
            FROM walk w JOIN named n ON n.id = w.id
        """, {"s": segment_id}).fetchone()
        ids = row["segment_ids"] or [segment_id]
        return {"name": row["name"], "segment_ids": ids, "length_m": row["length_m"] or 0}

    def group(self, group_id: int):
        """A street stretch for highlighting on the map: merged geometry, member ids, group scores."""
        row = self.conn.execute(f"""
            SELECT g.id, g.name, g.highway, g.length_m, g.segments_count, g.from_street, g.to_street,
                   ST_AsGeoJSON(ST_Multi(ST_Collect(s.geom)))::jsonb AS geometry,
                   array_agg(s.id ORDER BY s.id) AS segment_ids,
                   (SELECT {_agg("r")} FROM public.ratings r JOIN public.segments s2 ON s2.id = r.segment_id
                     WHERE s2.group_id = g.id) AS agg,
                   (SELECT count(*)::int FROM public.ratings r JOIN public.segments s2 ON s2.id = r.segment_id
                     WHERE s2.group_id = g.id) AS ratings_count,
                   (SELECT {_agg("r5")} FROM public.ratings r5 JOIN public.segments s5 ON s5.id = r5.segment_id
                     WHERE s5.highway = g.highway) AS highway_agg
            FROM public.segment_groups g JOIN public.segments s ON s.group_id = g.id
            WHERE g.id = %s GROUP BY g.id
        """, (group_id,)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono grupy")
        row["scores"] = group_scores(row.pop("agg"), row.pop("highway_agg") or {})
        return row

    def segment(self, segment_id: int, user_id: UUID | None = None):
        """Read detail, live scores, visible content and the signed-in user's own rating, comment and photo of this road."""
        row = self.conn.execute(SEGMENT_SELECT + " WHERE s.id = %s", (segment_id,)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono odcinka")
        row = enrich_segment(row)
        bands = {band.value: dict.fromkeys(DIMENSIONS) for band in TimeOfDay}
        for band in self.conn.execute("""
            SELECT time_of_day, round(avg(surface), 2) AS surface, round(avg(views), 2) AS views,
                   round(avg(safety), 2) AS safety, round(avg(traffic), 2) AS traffic,
                   round(avg(parking), 2) AS parking
            FROM public.ratings WHERE segment_id = %s GROUP BY time_of_day
        """, (segment_id,)).fetchall():
            bands[band["time_of_day"]] = {key: band[key] for key in DIMENSIONS}
        row["scores_by_time_of_day"] = bands
        row["summary"] = summaries.cached(self.conn, segment_id)  # the summary of the whole street stretch
        # True when a (new) AI summary is due; the route starts it in the background and the page shows "being prepared".
        row["summary_pending"] = summaries.needs_refresh(self.conn, segment_id)
        row["obstacles"] = self.conn.execute("""
            SELECT id, segment_id, type, description, valid_until, reported_by, created_at,
                   jsonb_build_object('lat', ST_Y(geom), 'lon', ST_X(geom)) AS location
            FROM public.obstacles WHERE segment_id = %s AND (valid_until IS NULL OR valid_until > now())
            ORDER BY created_at DESC, id DESC
        """, (segment_id,)).fetchall()
        row["photos_count"] = self.conn.execute("SELECT count(*)::int AS count FROM public.segment_photos WHERE segment_id = %s AND status = 'visible'", (segment_id,)).fetchone()["count"]
        row["my_rating"] = row["my_comment"] = row["my_photo"] = None
        if user_id:
            # One opinion per user and road (a new one replaces the old): the user's latest rating, comment and visible photo.
            row["my_rating"] = self.conn.execute(
                f"SELECT {RATING_COLUMNS} FROM public.ratings WHERE segment_id = %s AND user_id = %s ORDER BY rated_on DESC, created_at DESC LIMIT 1",
                (segment_id, user_id),
            ).fetchone()
            row["my_comment"] = self.conn.execute(
                COMMENT_SELECT + " WHERE c.segment_id = %s AND c.user_id = %s ORDER BY c.created_at DESC, c.id DESC LIMIT 1", (segment_id, user_id)
            ).fetchone()
            row["my_photo"] = self.conn.execute(
                PHOTO_SELECT + " WHERE segment_id = %s AND user_id = %s AND status = 'visible' ORDER BY created_at DESC, id DESC LIMIT 1", (segment_id, user_id)
            ).fetchone()
        return row

    def my_opinions(self, user_id: UUID, limit: int = 100):
        """The user's own ratings and comments (newest first) with the road names, hidden comments included."""
        return self.conn.execute("""
            SELECT 'rating' AS kind, r.id, r.segment_id, s.name AS segment_name, s.group_id, r.created_at, r.time_of_day::text AS time_of_day,
                   r.surface::int, r.views::int, r.safety::int, r.traffic::int, r.parking::int, NULL::text AS text, NULL::text AS status
              FROM public.ratings r JOIN public.segments s ON s.id = r.segment_id WHERE r.user_id = %(u)s
            UNION ALL
            SELECT 'comment', c.id, c.segment_id, s.name, s.group_id, c.created_at, NULL::text,
                   NULL::int, NULL::int, NULL::int, NULL::int, NULL::int, c.text, c.status::text
              FROM public.comments c JOIN public.segments s ON s.id = c.segment_id WHERE c.user_id = %(u)s
            ORDER BY created_at DESC LIMIT %(n)s
        """, {"u": user_id, "n": limit}).fetchall()

    def rate(self, segment_id: int, user_id: UUID, payload: RatingCreate, now: datetime):
        """Atomically replace the same user's rating of this road (whichever day it was made) and report 201 (first) or 200 (replaced)."""
        self.require_segment(segment_id)
        local_date = now.astimezone(ZoneInfo("Europe/Warsaw")).date()
        # Serialize same-user/segment writes, including the first INSERT.
        self.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s), %s)", (str(user_id), segment_id))
        previous = self.conn.execute("SELECT id FROM public.ratings WHERE user_id = %s AND segment_id = %s LIMIT 1", (user_id, segment_id)).fetchone()
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
        # One opinion per user and road: ratings from other days are replaced by this one.
        self.conn.execute("DELETE FROM public.ratings WHERE user_id = %s AND segment_id = %s AND id <> %s", (user_id, segment_id, row["id"]))
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

    def put_comment(self, segment_id: int, user_id: UUID, text: str):
        """Replace the user's comment on this road with `text` (or write the first one); returns the comment and whether it is new.

        Older comments of the same user on the road are removed, so there is one comment per user and road. A comment hidden by
        a moderator stays hidden after an edit.
        """
        self.require_segment(segment_id)
        self.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s), %s)", (str(user_id), segment_id))
        current = self.conn.execute("SELECT id FROM public.comments WHERE segment_id = %s AND user_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (segment_id, user_id)).fetchone()
        if current is None:
            current = self.conn.execute("INSERT INTO public.comments (segment_id, user_id, text) VALUES (%s, %s, %s) RETURNING id", (segment_id, user_id, text)).fetchone()
            created = True
        else:
            self.conn.execute("UPDATE public.comments SET text = %s, created_at = now() WHERE id = %s", (text, current["id"]))
            self.conn.execute("DELETE FROM public.comments WHERE segment_id = %s AND user_id = %s AND id <> %s", (segment_id, user_id, current["id"]))
            created = False
        summaries.invalidate(self.conn, segment_id)  # the cached summary may quote the old text
        return self.conn.execute(COMMENT_SELECT + " WHERE c.id = %s", (current["id"],)).fetchone(), created

    def delete_my_comments(self, segment_id: int, user_id: UUID) -> int:
        """Remove the user's comments on this road (their vectors go with them); returns how many were removed."""
        self.require_segment(segment_id)
        removed = self.conn.execute("DELETE FROM public.comments WHERE segment_id = %s AND user_id = %s", (segment_id, user_id)).rowcount
        if removed:
            summaries.invalidate(self.conn, segment_id)
        return removed

    def delete_my_photos(self, segment_id: int, user_id: UUID, keep: UUID | None = None) -> list[str]:
        """Remove the user's photos on this road except `keep`; returns the storage paths the router must delete."""
        self.require_segment(segment_id)
        rows = self.conn.execute(
            "DELETE FROM public.segment_photos WHERE segment_id = %s AND user_id = %s AND (%s::uuid IS NULL OR id <> %s::uuid) RETURNING storage_path, thumbnail_path",
            (segment_id, user_id, keep, keep),
        ).fetchall()
        if rows:
            summaries.invalidate(self.conn, segment_id)
        return [path for row in rows for path in (row["storage_path"], row["thumbnail_path"])]

    def photos(self, segment_id: int, page: int, page_size: int):
        """Visible photos of a road, newest first, as raw rows (storage paths still in place)."""
        self.require_segment(segment_id)
        total = self.conn.execute("SELECT count(*)::int AS count FROM public.segment_photos WHERE segment_id = %s AND status = 'visible'", (segment_id,)).fetchone()["count"]
        items = self.conn.execute(PHOTO_SELECT + " WHERE segment_id = %s AND status = 'visible' ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                                  (segment_id, page_size, (page - 1) * page_size)).fetchall()
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def add_photo(self, segment_id: int, user_id: UUID, storage_path: str, thumbnail_path: str, taken_at: datetime | None):
        """Insert a photo row for the verified identity; the files are already in storage."""
        self.require_segment(segment_id)
        return self.conn.execute("""
            INSERT INTO public.segment_photos (segment_id, user_id, storage_path, thumbnail_path, taken_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, segment_id, storage_path, thumbnail_path, taken_at, status, created_at
        """, (segment_id, user_id, storage_path, thumbnail_path, taken_at)).fetchone()

    def moderate_photo(self, photo_id: UUID, status: str):
        """Hide or restore a photo after the router has verified administrator access."""
        row = self.conn.execute("UPDATE public.segment_photos SET status = %s WHERE id = %s RETURNING id, segment_id, storage_path, thumbnail_path, taken_at, status, created_at",
                                (status, photo_id)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono zdjęcia")
        # The cached summary may describe a photo that is now hidden.
        summaries.invalidate(self.conn, row["segment_id"])
        return row

    def moderate_comment(self, comment_id: UUID, status: str):
        """Update visibility after the router has verified administrator access."""
        row = self.conn.execute("UPDATE public.comments SET status = %s WHERE id = %s RETURNING id", (status, comment_id)).fetchone()
        if row is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono komentarza")
        # Cached summaries may contain text from a now-hidden comment.
        summaries.invalidate(self.conn, self.conn.execute("SELECT segment_id FROM public.comments WHERE id = %s", (comment_id,)).fetchone()["segment_id"])
        return self.conn.execute(COMMENT_SELECT + " WHERE c.id = %s", (comment_id,)).fetchone()
