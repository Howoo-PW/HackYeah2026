"""Group fields in the segment API: row enrichment, response shapes, filters. No database needed."""

import copy

from fastapi.testclient import TestClient
import pytest

from app import main
from app.database import get_repository
from app.errors import AppError
from app.main import app
from app.repository import Repository, enrich_segment

DIMS = ("surface", "views", "safety", "traffic", "parking")


def agg(**counts_sums):
    return {d: list(counts_sums.get(d, (0, 0))) for d in DIMS}


def raw_row(own=None, group=None, highway=None, with_group=True, seg_id=1):
    """One SEGMENT_SELECT row as psycopg returns it."""
    return {
        "id": seg_id, "osm_way_id": 10, "name": "Długa", "highway": "residential", "length_m": 60.0,
        "surface_osm": None, "smoothness_osm": None, "maxspeed": None, "lit": None,
        "geometry": {"type": "LineString", "coordinates": [[19.9, 50.0], [19.91, 50.0]]},
        "own_agg": own or agg(), "ratings_count": sum(v[0] for v in (own or {}).values() if v) and 1 or 0,
        "last_rating_at": None, "group_agg": group or agg(), "group_ratings_count": 3,
        "highway_agg": highway or agg(),
        "group_info": {"id": 7, "name": "Długa", "highway": "residential", "length_m": 480.0, "segments_count": 6,
                       "from_street": "Basztowa", "to_street": "Pędzichów", "ratings_count": 0} if with_group else None,
        "active_obstacles_count": 0,
    }


def test_unrated_segment_in_a_rated_group_gets_an_estimated_score():
    row = enrich_segment(raw_row(group=agg(surface=(3, 12.0)), highway=agg(surface=(30, 90.0))))
    assert row["scores_source"] == "group"
    assert row["scores"]["surface"] == pytest.approx((12.0 + 3 * 3.0) / 6, abs=0.01)
    assert row["scores_own"] == dict.fromkeys(DIMS)
    assert row["group"]["ratings_count"] == 3 and row["group"]["from_street"] == "Basztowa"
    assert "own_agg" not in row and "group_info" not in row


def test_segment_without_a_group_still_scores_from_its_own_ratings():
    own = agg(safety=(2, 8.0))
    row = enrich_segment(raw_row(own=own, group=own, with_group=False))
    assert row["scores_source"] == "own" and row["group"] is None
    assert row["scores_own"]["safety"] == 4.0


def test_completely_unrated_segment_has_no_score():
    row = enrich_segment(raw_row())
    assert row["scores_source"] == "none" and row["confidence"] == "none"
    assert all(v is None for v in row["scores"].values())


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *args, **kwargs):
        return self

    def fetchall(self):
        return copy.deepcopy(self.rows)  # a real query returns fresh rows every time


def test_filters_use_the_effective_score():
    rated = raw_row(group=agg(surface=(3, 15.0)), seg_id=1)     # estimated 5-ish
    poor = raw_row(group=agg(surface=(3, 3.0)), seg_id=2)       # estimated 1-ish
    none = raw_row(seg_id=3)
    repo = Repository(FakeConn([rated, poor, none]))
    bbox = (19.9, 50.0, 19.95, 50.05)
    assert len(repo.segments(bbox)["features"]) == 3
    assert [f["properties"]["id"] for f in repo.segments(bbox, rated_only=True)["features"]] == [1, 2]
    assert [f["properties"]["id"] for f in repo.segments(bbox, "surface", 4)["features"]] == [1]
    with pytest.raises(AppError):
        repo.segments(bbox, None, 4)


class FakeGroupRepository:
    def segments(self, *args):
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "LineString", "coordinates": [[19.9, 50.0], [19.91, 50.0]]},
            "properties": enrich_segment(raw_row(group=agg(surface=(3, 12.0))))}]}

    def group(self, group_id):
        if group_id != 7:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono grupy")
        return {"id": 7, "name": "Długa", "highway": "residential", "length_m": 480.0, "segments_count": 2,
                "from_street": "Basztowa", "to_street": None, "ratings_count": 3,
                "scores": {"surface": 4.0, "views": None, "safety": None, "traffic": None, "parking": None},
                "geometry": {"type": "MultiLineString", "coordinates": [[[19.9, 50.0], [19.91, 50.0]], [[19.91, 50.0], [19.92, 50.0]]]},
                "segment_ids": [1, 2]}


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_repository] = lambda: FakeGroupRepository()
    monkeypatch.setattr(main, "create_pool", lambda: None)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.pop(get_repository, None)


def test_segments_response_exposes_group_and_score_source(client):
    props = client.get("/api/v1/segments?bbox=19.8,50.0,19.95,50.1").json()["features"][0]["properties"]
    assert props["scores_source"] == "group" and props["confidence"] in ("low", "medium", "high")
    assert props["group"]["id"] == 7 and props["group"]["segments_count"] == 6
    assert set(props["scores_own"]) == set(DIMS) and props["ratings_count"] == 0


def test_group_endpoint_returns_merged_geometry_and_members(client):
    body = client.get("/api/v1/groups/7").json()
    assert body["geometry"]["type"] == "MultiLineString" and len(body["geometry"]["coordinates"]) == 2
    assert body["segment_ids"] == [1, 2] and body["from_street"] == "Basztowa" and body["to_street"] is None


def test_unknown_group_is_not_found_in_contract_format(client):
    response = client.get("/api/v1/groups/99")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/api/v1/groups/0").status_code == 422
