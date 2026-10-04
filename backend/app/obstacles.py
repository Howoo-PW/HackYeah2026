"""Road obstacles (roadworks, closures, potholes...): docs/CONTRACT.md, sections 5.5 and 5.9.

Reported by signed-in users, listed publicly while active (`valid_until` empty or in the future), removed by
administrators. Active obstacles also change routes: see docs/ROUTING_GRAPH.md (closures block an edge,
the others slow it down).
"""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import User, require_admin, require_user
from .database import connection
from .errors import AppError
from .geo import parse_bbox, validate_point
from .schemas import Location, Obstacle

router = APIRouter()

REPORT_LIMIT_PER_HOUR = 10  # docs/CONTRACT.md, section 9
SEGMENT_RADIUS_M = 50  # the obstacle is attached to the nearest segment within this distance
LIST_LIMIT = 1000

_COLUMNS = """id, segment_id, type, description, valid_until, reported_by, created_at,
              jsonb_build_object('lat', ST_Y(geom), 'lon', ST_X(geom)) AS location"""


class ObstacleCreate(BaseModel):
    """Body of POST /obstacles."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["roadwork", "closure", "pothole", "accident", "other"]
    description: str | None = Field(default=None, max_length=500)
    location: Location
    valid_until: datetime | None = None  # None: until an administrator removes it

    @field_validator("description")
    @classmethod
    def blank_description_is_none(cls, value: str | None) -> str | None:
        """Trim the text; an empty one means no description."""
        return (value.strip() or None) if value else None

    @field_validator("valid_until")
    @classmethod
    def must_be_future(cls, value: datetime | None) -> datetime | None:
        """A time without a zone is read as UTC (the contract's format); it must still lie ahead."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError("valid_until must be in the future")
        return value


class ObstacleList(BaseModel):
    items: list[Obstacle]


class ObstacleRepository:
    """Request-scoped access to the `obstacles` table (one transaction per request)."""

    def __init__(self, conn):
        self.conn = conn

    def active(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        """Active obstacles inside the box, newest first (at most LIST_LIMIT)."""
        return self.conn.execute(
            f"""SELECT {_COLUMNS} FROM public.obstacles
                WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  AND (valid_until IS NULL OR valid_until > now())
                ORDER BY created_at DESC, id DESC LIMIT %s""",
            (*bbox, LIST_LIMIT)).fetchall()

    def create(self, user_id: UUID, payload: ObstacleCreate) -> dict:
        """Insert an obstacle reported by the verified user; the nearest segment (<= 50 m) is attached."""
        return self.conn.execute(
            f"""WITH p AS (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) AS geom)
                INSERT INTO public.obstacles (segment_id, type, description, geom, reported_by, valid_until)
                SELECT (SELECT s.id FROM public.segments s
                        WHERE ST_DWithin(s.geom::geography, p.geom::geography, %(radius)s)
                        ORDER BY ST_Distance(s.geom::geography, p.geom::geography), s.id LIMIT 1),
                       %(type)s::public.obstacle_type, %(description)s::text, p.geom, %(user)s::uuid,
                       %(valid_until)s::timestamptz
                FROM p
                RETURNING {_COLUMNS}""",
            {"lon": payload.location.lon, "lat": payload.location.lat, "radius": SEGMENT_RADIUS_M,
             "type": payload.type, "description": payload.description, "user": user_id,
             "valid_until": payload.valid_until}).fetchone()

    def delete(self, obstacle_id: UUID) -> None:
        """Remove an obstacle; the router has already verified administrator access."""
        if self.conn.execute("DELETE FROM public.obstacles WHERE id = %s RETURNING id", (obstacle_id,)).fetchone() is None:
            raise AppError(404, "NOT_FOUND", "Nie znaleziono przeszkody")


def get_obstacle_repository(request: Request):
    """Provide one request-scoped repository and transaction (committed before the response is sent)."""
    with connection(request) as conn:
        yield ObstacleRepository(conn)


RepositoryDep = Annotated[ObstacleRepository, Depends(get_obstacle_repository, scope="function")]


@router.get("/obstacles", response_model=ObstacleList, tags=["obstacles"])
def list_obstacles(repo: RepositoryDep, bbox: str):
    """Active obstacles in a bounding box (minLon,minLat,maxLon,maxLat)."""
    return {"items": repo.active(parse_bbox(bbox))}


@router.post("/obstacles", response_model=Obstacle, status_code=201, tags=["obstacles"])
def report_obstacle(payload: ObstacleCreate, user: Annotated[User, Depends(require_user)],
                    repo: RepositoryDep, request: Request):
    """Report an obstacle under the 10-per-hour user limit; the location must lie in the service area."""
    validate_point(payload.location.lat, payload.location.lon)
    request.app.state.rate_limiter.check(str(user.id), "obstacles", REPORT_LIMIT_PER_HOUR)
    return repo.create(user.id, payload)


@router.delete("/admin/obstacles/{obstacle_id}", status_code=204, response_class=Response, tags=["admin"])
def remove_obstacle(obstacle_id: UUID, admin: Annotated[User, Depends(require_admin)], repo: RepositoryDep):
    """Allow only an administrator to remove an obstacle."""
    repo.delete(obstacle_id)
    return Response(status_code=204)
