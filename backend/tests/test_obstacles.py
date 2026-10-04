"""Obstacle endpoints (docs/CONTRACT.md 5.5, 5.9) with a fake repository, plus the repository's SQL parameters."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import User, optional_user
from app.errors import AppError
from app.main import app
from app.obstacles import REPORT_LIMIT_PER_HOUR, ObstacleRepository, get_obstacle_repository

client = TestClient(app)
USER = User(UUID("11111111-1111-4111-8111-111111111111"), "test@example.invalid")
BBOX = "19.9,50.0,20.0,50.1"
NOW = datetime.now(timezone.utc)
FUTURE = (NOW + timedelta(days=7)).isoformat()


def stored(payload=None, user_id=USER.id):
    """A row as the database returns it."""
    return {"id": uuid4(), "segment_id": 1042, "type": payload.type if payload else "roadwork",
            "description": payload.description if payload else "Remont",
            "valid_until": payload.valid_until if payload else None, "reported_by": user_id, "created_at": NOW,
            "location": {"lat": payload.location.lat, "lon": payload.location.lon} if payload else {"lat": 50.05, "lon": 19.94}}


class FakeRepository:
    def __init__(self):
        self.created, self.deleted, self.bbox, self.owner = [], [], None, None
        self.missing = False

    def active(self, bbox):
        self.bbox = bbox
        return [stored()]

    def create(self, user_id, payload):
        self.owner = user_id
        self.created.append(payload)
        return stored(payload, user_id)

    def delete(self, obstacle_id):
        if self.missing:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono przeszkody")
        self.deleted.append(obstacle_id)


@pytest.fixture
def repo():
    fake = FakeRepository()
    app.dependency_overrides[get_obstacle_repository] = lambda: fake
    return fake


def login(role="user"):
    app.dependency_overrides[optional_user] = lambda: User(USER.id, USER.email, role)


BODY = {"type": "roadwork", "description": "Remont nawierzchni, ruch wahadłowy",
        "location": {"lat": 50.0547, "lon": 19.9356}, "valid_until": FUTURE}


# --- listing ---------------------------------------------------------------------------------------------------

def test_listing_is_public_and_returns_the_contract_shape(repo):
    res = client.get(f"/api/v1/obstacles?bbox={BBOX}")
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert set(item) == {"id", "segment_id", "type", "description", "location", "valid_until", "reported_by", "created_at"}
    assert item["location"] == {"lat": 50.05, "lon": 19.94}
    assert repo.bbox == (19.9, 50.0, 20.0, 50.1)


@pytest.mark.parametrize("bbox", ["", "1,2,3", "a,b,c,d", "20.0,50.0,19.9,50.1", "0,0,1,1"])
def test_listing_rejects_a_bad_bbox(repo, bbox):
    assert client.get("/api/v1/obstacles", params={"bbox": bbox}).status_code == 422


# --- reporting -------------------------------------------------------------------------------------------------

def test_reporting_requires_login(repo):
    res = client.post("/api/v1/obstacles", json=BODY)
    assert res.status_code == 401 and res.json()["error"]["code"] == "UNAUTHORIZED"
    assert repo.created == []


def test_report_is_created_for_the_verified_user(repo):
    login()
    res = client.post("/api/v1/obstacles", json=BODY)
    assert res.status_code == 201
    assert res.json()["type"] == "roadwork" and res.json()["reported_by"] == str(USER.id)
    assert repo.owner == USER.id and len(repo.created) == 1


def test_reporter_cannot_be_chosen_by_the_client(repo):
    login()
    res = client.post("/api/v1/obstacles", json={**BODY, "reported_by": str(uuid4())})
    assert res.status_code == 422 and repo.created == []


def test_valid_until_and_description_are_optional(repo):
    login()
    res = client.post("/api/v1/obstacles", json={"type": "pothole", "location": BODY["location"]})
    assert res.status_code == 201
    assert repo.created[0].valid_until is None and repo.created[0].description is None


def test_blank_description_becomes_null_and_text_is_trimmed(repo):
    login()
    client.post("/api/v1/obstacles", json={**BODY, "description": "   "})
    client.post("/api/v1/obstacles", json={**BODY, "description": "  dziura  "})
    assert [p.description for p in repo.created] == [None, "dziura"]


def test_time_without_a_zone_is_read_as_utc(repo):
    login()
    naive = (NOW + timedelta(days=1)).replace(tzinfo=None).isoformat()
    assert client.post("/api/v1/obstacles", json={**BODY, "valid_until": naive}).status_code == 201
    assert repo.created[0].valid_until.tzinfo is not None


@pytest.mark.parametrize("change", [
    {"type": "flood"}, {"description": "x" * 501},
    {"valid_until": (NOW - timedelta(hours=1)).isoformat()}, {"location": {"lat": 50.05}},
])
def test_report_validation(repo, change):
    login()
    res = client.post("/api/v1/obstacles", json={**BODY, **change})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert repo.created == []


def test_report_outside_the_service_area_is_rejected(repo):
    login()
    res = client.post("/api/v1/obstacles", json={**BODY, "location": {"lat": 52.23, "lon": 21.01}})
    assert res.status_code == 422 and res.json()["error"]["code"] == "OUT_OF_AREA"
    assert repo.created == []


def test_report_limit_is_10_per_hour_per_user(repo):
    login()
    assert all(client.post("/api/v1/obstacles", json=BODY).status_code == 201 for _ in range(REPORT_LIMIT_PER_HOUR))
    res = client.post("/api/v1/obstacles", json=BODY)
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"


# --- removal (administrators) ------------------------------------------------------------------------------------

def test_removal_requires_login_and_admin_role(repo):
    target = uuid4()
    assert client.delete(f"/api/v1/admin/obstacles/{target}").status_code == 401
    login("user")
    res = client.delete(f"/api/v1/admin/obstacles/{target}")
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"
    assert repo.deleted == []


def test_admin_removes_an_obstacle(repo):
    login("admin")
    target = uuid4()
    res = client.delete(f"/api/v1/admin/obstacles/{target}")
    assert res.status_code == 204 and res.content == b""
    assert repo.deleted == [target]


def test_removing_an_unknown_obstacle_is_not_found(repo):
    login("admin")
    repo.missing = True
    res = client.delete(f"/api/v1/admin/obstacles/{uuid4()}")
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


# --- repository (the SQL itself is checked against the real database in test_obstacles_db.py) ---------------------

class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, rows=()):
        self.rows, self.executed = list(rows), []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeResult(self.rows)


def test_repository_delete_reports_a_missing_obstacle():
    with pytest.raises(AppError) as err:
        ObstacleRepository(FakeConnection([])).delete(uuid4())
    assert (err.value.status, err.value.code) == (404, "NOT_FOUND")
    ObstacleRepository(FakeConnection([{"id": 1}])).delete(uuid4())  # an existing row: no error
