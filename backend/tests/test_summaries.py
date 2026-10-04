"""AI summary refresh rules and failure handling, with a fake database and a stubbed AI call."""

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from app import summaries
from app.errors import AppError

AI_RESULT = summaries.AiSummary(surface="a", views="b", safety="c", traffic="d", parking="e", overall="f",
                                confidence="high", conflicts=[], comments_count=6, model="m")


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    """Answers the three queries the module makes, keyed by a word in the SQL."""

    def __init__(self, visible, cached, comments=0, newer_photo=False, photos=0, photo_paths=None):
        self.visible, self.cached, self.comments, self.newer_photo, self.photos, self.saved = visible, cached, comments, newer_photo, photos, None
        self.photo_paths = ["1/a.jpg"] if photo_paths is None else photo_paths

    def execute(self, sql, params=None):
        if "AS visible" in sql:
            return FakeResult([{"visible": self.visible, "cached": self.cached, "newer_photo": self.newer_photo, "photos": self.photos}])
        if "FROM public.comments c" in sql:
            now = datetime(2026, 10, 4, tzinfo=timezone.utc)
            return FakeResult([{"id": i, "text": f"opinia {i}", "created_at": now, "rating": None} for i in range(self.comments)])
        if "FROM public.segment_photos" in sql and "storage_path" in sql:
            return FakeResult([{"storage_path": p} for p in self.photo_paths])
        if "avg(" in sql:
            return FakeResult([{"ratings_count": 4, "surface": None, "views": None, "safety": None, "traffic": None, "parking": None}])
        self.saved = params
        return FakeResult([{"summary": {"overall": "f"}, "comments_count": 6, "model": "m", "updated_at": datetime(2026, 10, 4, tzinfo=timezone.utc)}])


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


@pytest.fixture(autouse=True)
def reset_state():
    summaries._in_flight.clear()
    summaries._failed_at.clear()


@pytest.mark.parametrize("visible,cached,expected", [
    (4, None, False),   # too few comments
    (5, None, True),    # first summary
    (9, 5, False),      # only 4 new comments
    (10, 5, True),      # 5 new comments
    (5, 5, False),
])
def test_needs_refresh(visible, cached, expected):
    assert summaries.needs_refresh(FakeConn(visible, cached), 1) is expected


def test_a_photo_alone_is_enough_for_a_summary():
    assert summaries.needs_refresh(FakeConn(0, None, photos=1), 1) is True
    assert summaries.needs_refresh(FakeConn(2, None, photos=1), 1) is True
    assert summaries.needs_refresh(FakeConn(2, None, photos=0), 1) is False


def test_a_photo_added_after_the_summary_makes_it_due_again():
    assert summaries.needs_refresh(FakeConn(6, 6, newer_photo=True), 1) is True
    assert summaries.needs_refresh(FakeConn(3, 3, newer_photo=True, photos=0), 1) is False  # no material at all


def test_refresh_sends_the_photos_to_the_ai(monkeypatch):
    sent = {}
    monkeypatch.setattr(summaries.photo_store, "sign", lambda paths: {p: "https://signed/" + p for p in paths})
    monkeypatch.setattr(summaries, "call_ai", lambda payload: sent.update(payload) or AI_RESULT)
    summaries.refresh(FakePool(FakeConn(6, None, comments=6)), 1)
    assert sent["image_urls"] == ["https://signed/1/a.jpg"] and "photo_paths" not in sent


def test_refresh_works_without_photos_when_storage_is_down(monkeypatch):
    def broken(paths):
        raise AppError(503, "STORAGE_UNAVAILABLE", "x")

    sent = {}
    monkeypatch.setattr(summaries.photo_store, "sign", broken)
    monkeypatch.setattr(summaries, "call_ai", lambda payload: sent.update(payload) or AI_RESULT)
    assert summaries.refresh(FakePool(FakeConn(6, None, comments=6)), 1) is not None
    assert sent["image_urls"] == []


def test_ratings_stay_out_of_the_request_unless_switched_on(monkeypatch):
    conn = FakeConn(6, None, comments=2)
    monkeypatch.setattr(summaries.settings, "summary_use_ratings", False)
    off = summaries.build_request(conn, 1)
    assert off["scores"] is None and off["ratings_count"] == 0 and all(c["rating"] is None for c in off["comments"])
    monkeypatch.setattr(summaries.settings, "summary_use_ratings", True)
    on = summaries.build_request(conn, 1)
    assert on["ratings_count"] == 4 and on["scores"] is not None


def test_refresh_with_only_a_photo_calls_the_ai(monkeypatch):
    sent = {}
    monkeypatch.setattr(summaries.photo_store, "sign", lambda paths: {p: "https://signed/" + p for p in paths})
    monkeypatch.setattr(summaries, "call_ai", lambda payload: sent.update(payload) or AI_RESULT)
    assert summaries.refresh(FakePool(FakeConn(0, None, comments=0, photos=1)), 1) is not None
    assert sent["comments"] == [] and sent["image_urls"] == ["https://signed/1/a.jpg"]


def test_refresh_saves_the_ai_summary(monkeypatch):
    conn = FakeConn(6, None, comments=6)
    monkeypatch.setattr(summaries.photo_store, "sign", lambda paths: {})
    monkeypatch.setattr(summaries, "call_ai", lambda payload: AI_RESULT)
    saved = summaries.refresh(FakePool(conn), 1)
    assert saved["overall"] == "f" and saved["model"] == "m"
    assert conn.saved[0] == 1 and 1 not in summaries._in_flight


def test_ai_failure_is_swallowed_and_remembered(monkeypatch):
    calls = []

    def failing(payload):
        calls.append(1)
        raise AppError(502, "AI_UNAVAILABLE", "x")

    monkeypatch.setattr(summaries.photo_store, "sign", lambda paths: {})
    monkeypatch.setattr(summaries, "call_ai", failing)
    pool = FakePool(FakeConn(6, None, comments=6))
    assert summaries.refresh(pool, 1) is None
    assert summaries.refresh(pool, 1) is None  # cooldown: the AI is not called again
    assert len(calls) == 1


def test_forced_refresh_raises_when_the_ai_fails(monkeypatch):
    def failing(payload):
        raise AppError(502, "AI_UNAVAILABLE", "x")

    monkeypatch.setattr(summaries.photo_store, "sign", lambda paths: {})
    monkeypatch.setattr(summaries, "call_ai", failing)
    with pytest.raises(AppError) as exc:
        summaries.refresh(FakePool(FakeConn(6, None, comments=6)), 1, force=True)
    assert exc.value.status == 502


def test_forced_refresh_needs_five_comments_or_a_photo():
    with pytest.raises(AppError) as exc:
        summaries.refresh(FakePool(FakeConn(3, None, comments=3, photo_paths=[])), 1, force=True)
    assert exc.value.status == 422
