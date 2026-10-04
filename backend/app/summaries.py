"""AI summaries of one road piece (the clicked fragment): when to refresh, the call to the AI service and the cache table.

The summary is made from that segment's own comments and photos only (ratings too when SUMMARY_USE_RATINGS is on). It needs at least
5 visible comments or at least one visible photo: a photo alone is enough.
"""

import logging
import threading
import time

import httpx
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError

from . import photos as photo_store
from .config import settings
from .errors import AppError
from .schemas import DIMENSIONS

log = logging.getLogger("summaries")

MIN_COMMENTS = 5  # below this the AI is called only when the road has a photo (contract section 6 asks for 5 comments)
MAX_COMMENTS = 50  # the newest ones are sent
MAX_PHOTOS = 4  # newest photos of the road sent along with the comments
REFRESH_AFTER_NEW = 5  # the cached summary is recalculated after this many new visible comments
AI_TIMEOUT_S = 15
FAILURE_COOLDOWN_S = 300  # after a failed AI call the road is left alone for a while

_lock = threading.Lock()
_in_flight: set[int] = set()
_failed_at: dict[int, float] = {}


def invalidate(conn, segment_id: int) -> None:
    """Drop the road's cached summary (after a comment or photo was hidden, so the text cannot show hidden content)."""
    conn.execute("DELETE FROM public.segment_summaries WHERE segment_id = %s", (segment_id,))


def cached(conn, segment_id: int) -> dict | None:
    """The road's stored summary as the contract's `Summary` (without recalculating), or None."""
    # A stored row is shown only while the road still has material: enough visible comments or a visible photo
    # (so not after moderation hid it all, nor for a stale row).
    row = conn.execute("""
        SELECT summary, comments_count, model, updated_at FROM public.segment_summaries
        WHERE segment_id = %(s)s
          AND ((SELECT count(*) FROM public.comments WHERE segment_id = %(s)s AND status = 'visible') >= %(min)s
               OR EXISTS (SELECT 1 FROM public.segment_photos WHERE segment_id = %(s)s AND status = 'visible'))
    """, {"s": segment_id, "min": MIN_COMMENTS}).fetchone()
    if row is None:
        return None
    return {**row["summary"], "comments_count": row["comments_count"], "model": row["model"], "updated_at": row["updated_at"]}


class AiSummary(BaseModel):
    """What the AI service returns for POST /summarize (contract section 6)."""

    surface: str
    views: str
    safety: str
    traffic: str
    parking: str
    overall: str
    confidence: str
    conflicts: list[str]
    comments_count: int
    model: str


def needs_refresh(conn, segment_id: int) -> bool:
    """True when the road has material (5 visible comments or a photo) and no summary yet, at least 5 new comments since the
    cached one, or a photo added after the cached one was made."""
    row = conn.execute("""
        SELECT (SELECT count(*)::int FROM public.comments WHERE segment_id = %(s)s AND status = 'visible') AS visible,
               (SELECT count(*)::int FROM public.segment_photos WHERE segment_id = %(s)s AND status = 'visible') AS photos,
               (SELECT comments_count FROM public.segment_summaries WHERE segment_id = %(s)s) AS cached,
               EXISTS (SELECT 1 FROM public.segment_photos p JOIN public.segment_summaries m ON m.segment_id = p.segment_id
                        WHERE p.segment_id = %(s)s AND p.status = 'visible' AND p.created_at > m.updated_at) AS newer_photo
    """, {"s": segment_id}).fetchone()
    if row["visible"] < MIN_COMMENTS and row["photos"] == 0:
        return False
    return row["cached"] is None or row["visible"] - row["cached"] >= REFRESH_AFTER_NEW or row["newer_photo"]


def build_request(conn, segment_id: int) -> dict:
    """Request body for the AI service: the road's newest visible comments (each with its author's own rating) and its average scores."""
    comments = conn.execute("""
        SELECT c.id, c.text, c.created_at,
               CASE WHEN r.id IS NULL THEN NULL ELSE jsonb_build_object('surface', r.surface, 'views', r.views, 'safety', r.safety,
                                                                        'traffic', r.traffic, 'parking', r.parking) END AS rating
        FROM public.comments c
        LEFT JOIN LATERAL (SELECT * FROM public.ratings WHERE user_id = c.user_id AND segment_id = c.segment_id
                           ORDER BY created_at DESC LIMIT 1) r ON true
        WHERE c.status = 'visible' AND c.segment_id = %(s)s
        ORDER BY c.created_at DESC, c.id DESC LIMIT %(n)s
    """, {"s": segment_id, "n": MAX_COMMENTS}).fetchall()
    averages = conn.execute(f"""
        SELECT count(*)::int AS ratings_count, {", ".join(f"round(avg({d})::numeric, 2)::float AS {d}" for d in DIMENSIONS)}
        FROM public.ratings WHERE segment_id = %(s)s
    """, {"s": segment_id}).fetchone()
    photos = conn.execute("""
        SELECT storage_path FROM public.segment_photos
        WHERE status = 'visible' AND segment_id = %(s)s
        ORDER BY created_at DESC, id DESC LIMIT %(n)s
    """, {"s": segment_id, "n": MAX_PHOTOS}).fetchall()
    use_ratings = settings.summary_use_ratings  # off by default: the summary rests on comments and photos
    return {
        "photo_paths": [p["storage_path"] for p in photos],
        "segment_id": segment_id,
        "language": "pl",
        "comments": [{"id": str(c["id"]), "text": c["text"], "created_at": c["created_at"].isoformat(),
                      "rating": c["rating"] if use_ratings else None} for c in comments],
        "ratings_count": averages["ratings_count"] if use_ratings else 0,
        "scores": {d: averages[d] for d in DIMENSIONS} if use_ratings and averages["ratings_count"] else None,
    }


def signed_photo_urls(paths: list[str]) -> list[str]:
    """Signed (one hour) URLs of the photos, in the order given; empty when there are none or storage is unavailable."""
    if not paths:
        return []
    try:
        urls = photo_store.sign(paths)
    except AppError:
        return []  # the summary is still made from comments and ratings
    return [urls[p] for p in paths if p in urls]


def call_ai(payload: dict) -> AiSummary:
    """POST /summarize on the AI service; any failure becomes a 502 so callers can decide whether to show it."""
    try:
        response = httpx.post(f"{settings.ai_service_url}/summarize", json=payload, timeout=AI_TIMEOUT_S,
                              headers={"X-Internal-Key": settings.internal_api_key})
        response.raise_for_status()
        return AiSummary(**response.json())
    except (httpx.HTTPError, ValidationError, ValueError):
        raise AppError(502, "AI_UNAVAILABLE", "Nie udało się przygotować podsumowania") from None


def save(conn, key: int, summary: AiSummary) -> dict:
    """Upsert the cache row under the stretch's `key` and return it in the shape of the contract's `Summary`."""
    content = summary.model_dump(exclude={"comments_count", "model"})
    row = conn.execute("""
        INSERT INTO public.segment_summaries (segment_id, summary, comments_count, model, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (segment_id) DO UPDATE SET summary = excluded.summary, comments_count = excluded.comments_count,
                                               model = excluded.model, updated_at = excluded.updated_at
        RETURNING summary, comments_count, model, updated_at
    """, (key, Jsonb(content), summary.comments_count, summary.model)).fetchone()
    return {**row["summary"], "comments_count": row["comments_count"], "model": row["model"], "updated_at": row["updated_at"]}


def refresh(pool, segment_id: int, force: bool = False) -> dict | None:
    """Recalculate and store the summary of one road; None when it was not needed or the AI failed.

    The database connection is not held during the AI call (up to 15 s). With `force` (admin) the cache is ignored and an AI
    failure raises; otherwise failures are logged, remembered for five minutes and swallowed: reading comments never depends on the AI.
    """
    key = segment_id
    with _lock:
        if key in _in_flight or (not force and time.monotonic() - _failed_at.get(key, -FAILURE_COOLDOWN_S) < FAILURE_COOLDOWN_S):
            return None
        _in_flight.add(key)
    try:
        with pool.connection() as conn:
            if not force and not needs_refresh(conn, key):
                return None
            payload = build_request(conn, key)
        paths = payload.pop("photo_paths")
        if len(payload["comments"]) < MIN_COMMENTS and not paths:
            raise AppError(422, "VALIDATION_ERROR", f"Za mało materiału: minimum {MIN_COMMENTS} komentarzy albo jedno zdjęcie")
        payload["image_urls"] = signed_photo_urls(paths)
        summary = call_ai(payload)
        with pool.connection() as conn:
            return save(conn, key, summary)
    except AppError as exc:
        if force:
            raise
        _failed_at[key] = time.monotonic()
        log.warning("summary refresh for segment %s failed: %s", key, exc.message)
        return None
    except Exception:  # background work must never raise
        _failed_at[key] = time.monotonic()
        log.exception("summary refresh for segment %s failed", key)
        return None
    finally:
        with _lock:
            _in_flight.discard(key)
