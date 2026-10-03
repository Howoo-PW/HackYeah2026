"""Contract and authorization regressions without requiring production credentials."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import httpx
import jwt
from pydantic import SecretStr
import pytest

from app import auth, main
from app.auth import User, optional_user, require_user
from app.config import settings
from app.database import get_repository
from app.errors import AppError
from app.geo import parse_bbox
from app.main import app
from app.rate_limit import RateLimiter
from app.repository import time_of_day

USER = User(UUID("11111111-1111-4111-8111-111111111111"), "test@example.invalid")
NOW = datetime.now(timezone.utc)


class FakeRepository:
    """Contract fixtures; database SQL is separately checked against live Supabase."""

    def __init__(self):
        self.rating = None
        self.owner = None

    def segments(self, *args):
        return {"type": "FeatureCollection", "features": []}

    def nearest(self, *args):
        raise AppError(404, "NOT_FOUND", "Brak odcinka")

    def rate(self, segment_id, user_id, payload, now):
        created = self.rating is None
        self.owner = user_id
        self.rating = {**payload.model_dump(), "id": self.rating["id"] if self.rating else uuid4(),
                       "segment_id": segment_id, "time_of_day": payload.time_of_day or time_of_day(now), "created_at": now}
        return self.rating, created

    def comment(self, segment_id, user_id, text):
        self.owner = user_id
        return {"id": uuid4(), "segment_id": segment_id, "text": text, "status": "visible",
                "created_at": NOW, "author": {"id": user_id, "display_name": "Test"}}

    def comments(self, segment_id, page, page_size):
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

    def moderate_comment(self, comment_id, status):
        return {"id": comment_id, "segment_id": 1, "text": "Test", "status": status,
                "created_at": NOW, "author": {"id": USER.id, "display_name": "Test"}}

    def profile(self, user):
        return {"id": user.id, "email": user.email, "role": user.role, "display_name": "Test", "created_at": NOW}


@pytest.fixture
def client(monkeypatch):
    repo = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    app.state.rate_limiter = RateLimiter()
    monkeypatch.setattr(main, "create_pool", lambda: None)
    with TestClient(app, raise_server_exceptions=False) as client:
        client.repo = repo
        yield client
    app.dependency_overrides.clear()


def login(role="user"):
    app.dependency_overrides[optional_user] = lambda: User(USER.id, USER.email, role)


@pytest.mark.parametrize("path,method,body", [
    ("/me", "get", None), ("/segments/1/ratings", "post", {"surface": 4}),
    ("/segments/1/comments", "post", {"text": "Test"}),
    (f"/admin/comments/{uuid4()}", "patch", {"status": "hidden"}),
])
def test_writes_and_profile_require_auth(client, path, method, body):
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)("/api/v1" + path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("body", [{}, {"surface": 0}, {"surface": 6}, {"surface": 2.5},
                                  {"surface": True}, {"surface": "4"}, {"surface": 4, "user_id": str(uuid4())},
                                  {"surface": 4, "time_of_day": "afternoon"}])
def test_rating_validation(client, body):
    login()
    response = client.post("/api/v1/segments/1/ratings", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_daily_replacement_and_verified_owner(client):
    login()
    first = client.post("/api/v1/segments/1/ratings", json={"surface": 2})
    second = client.post("/api/v1/segments/1/ratings", json={"surface": 5, "time_of_day": "night"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["surface"] == 5
    assert second.json()["views"] is None
    assert second.json()["time_of_day"] == "night"
    assert client.repo.owner == USER.id


@pytest.mark.parametrize("text", ["", "   ", "a" * 1001])
def test_comment_validation(client, text):
    login()
    assert client.post("/api/v1/segments/1/comments", json={"text": text}).status_code == 422


def test_comment_creation_and_pagination(client):
    login()
    response = client.post("/api/v1/segments/1/comments", json={"text": "Nowy asfalt przy moście"})
    assert response.status_code == 201
    assert response.json()["author"]["id"] == str(USER.id)
    assert "user_id" not in response.json()
    assert client.get("/api/v1/segments/1/comments?page=2&page_size=5").json() == {"items": [], "page": 2, "page_size": 5, "total": 0}
    assert client.get("/api/v1/segments/1/comments?page_size=101").status_code == 422


def test_admin_moderation(client):
    login()
    path = f"/api/v1/admin/comments/{uuid4()}"
    assert client.patch(path, json={"status": "hidden"}).status_code == 403
    login("admin")
    assert client.patch(path, json={"status": "hidden"}).json()["status"] == "hidden"


@pytest.mark.parametrize("query,code", [
    ("bbox=broken", "VALIDATION_ERROR"),
    ("bbox=20,50.1,19.9,50.05", "VALIDATION_ERROR"),
    ("bbox=19,50,20,50.1", "OUT_OF_AREA"),
    ("bbox=19.9,50.01,20,50.1&min_score=3", "VALIDATION_ERROR"),
    ("bbox=NaN,50,20,50.1", "VALIDATION_ERROR"),
])
def test_bbox_and_filter_validation(client, query, code):
    response = client.get("/api/v1/segments?" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_public_geojson_and_nearest_precedes_dynamic_id(client):
    assert client.get("/api/v1/segments?bbox=19.792,49.967,20.217,50.126").json() == {"type": "FeatureCollection", "features": []}
    assert client.get("/api/v1/segments/nearest?lat=50.06&lon=19.94").status_code == 404
    assert client.get("/api/v1/segments/nearest?lat=52&lon=19.94").json()["error"]["code"] == "OUT_OF_AREA"


def test_rate_limits(client):
    login()
    for _ in range(10):
        assert client.post("/api/v1/segments/1/comments", json={"text": "Test"}).status_code == 201
    response = client.post("/api/v1/segments/1/comments", json={"text": "Test"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    # Different actions have separate limits.
    assert client.post("/api/v1/segments/1/ratings", json={"surface": 5}).status_code == 201


@pytest.mark.parametrize("database,ai,status,http", [("ok", "ok", "ok", 200), ("ok", "error", "degraded", 200), ("error", "ok", "down", 503), ("not_configured", "ok", "down", 503)])
def test_health(client, monkeypatch, database, ai, status, http):
    monkeypatch.setattr(main, "_check_database", lambda: database)
    monkeypatch.setattr(main, "_check_routing", lambda: "ok")
    async def check_ai():
        return ai
    monkeypatch.setattr(main, "_check_ai", check_ai)
    response = client.get("/api/v1/health")
    assert response.status_code == http
    assert response.json()["status"] == status


def token_claims(**overrides):
    return {"sub": str(USER.id), "email": USER.email, "role": "authenticated", "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1", "iat": NOW, "exp": NOW + timedelta(minutes=5), **overrides}


@pytest.fixture
def signing(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "supabase_url", "https://test.supabase.co")
    monkeypatch.setattr(auth, "jwks_client", lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())))
    return lambda **claims: jwt.encode(token_claims(**claims), private_key, algorithm="ES256", headers={"kid": "test"})


def test_verified_token_ignores_user_metadata(signing):
    assert auth.verify_token(signing(user_metadata={"role": "admin"})).role == "user"
    assert auth.verify_token(signing(app_metadata={"role": "admin"})).role == "admin"


@pytest.mark.parametrize("claims", [{"exp": NOW - timedelta(seconds=1)}, {"aud": "another"},
                                    {"iss": "https://evil.invalid/auth/v1"}, {"sub": "invalid"}, {"role": "service_role"}])
def test_invalid_token_claims(signing, claims):
    with pytest.raises(AppError) as error:
        auth.verify_token(signing(**claims))
    assert error.value.status == 401


def test_tampered_signature(signing):
    token = signing()
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    with pytest.raises(AppError):
        auth.verify_token(tampered)


def test_hs256_is_verified_by_auth_server(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://test.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", SecretStr("test-public-key"))
    token = jwt.encode(token_claims(app_metadata={"role": "admin"}), "test-legacy-key-at-least-32-bytes!", algorithm="HS256")
    class AuthClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, headers):
            assert headers["Authorization"] == f"Bearer {token}"
            return httpx.Response(200, json={"id": str(USER.id), "email": USER.email, "app_metadata": {"role": "user"}})
    monkeypatch.setattr(auth.httpx, "Client", AuthClient)
    assert auth.verify_token(token).role == "user"


@pytest.mark.parametrize("utc,expected", [("2026-10-03T03:59:00+00:00", "night"), ("2026-10-03T04:00:00+00:00", "morning"),
                                         ("2026-10-03T08:00:00+00:00", "day"), ("2026-10-03T14:00:00+00:00", "evening"),
                                         ("2026-10-03T20:00:00+00:00", "night"), ("2026-12-03T05:00:00+00:00", "morning")])
def test_warsaw_time_bands(utc, expected):
    assert time_of_day(datetime.fromisoformat(utc)) == expected


def test_unknown_route_uses_contract_error(client):
    assert client.get("/api/v1/missing").json()["error"]["code"] == "NOT_FOUND"


def test_openapi_has_core_routes(client):
    spec = client.get("/openapi.json").json()
    assert "200" in spec["paths"]["/api/v1/segments/{segment_id}/ratings"]["post"]["responses"]
    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
