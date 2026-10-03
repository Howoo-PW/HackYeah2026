"""Request and response models for POST /route (docs/CONTRACT.md, section 5.8)."""

from typing import Literal

from pydantic import BaseModel, Field

Profile = Literal["driving-car", "cycling-regular", "foot-walking"]
DIMENSIONS = ("surface", "views", "safety", "traffic", "parking")


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Weights(BaseModel):
    surface: int = Field(default=0, ge=0, le=3)
    views: int = Field(default=0, ge=0, le=3)
    safety: int = Field(default=0, ge=0, le=3)
    traffic: int = Field(default=0, ge=0, le=3)
    parking: int = Field(default=0, ge=0, le=3)


MAX_VIA = 5  # intermediate stops; every leg is a separate search, so the number is bounded


class RouteRequest(BaseModel):
    from_: Point = Field(alias="from")
    to: Point
    via: list[Point] = Field(default_factory=list, max_length=MAX_VIA)  # stops between from and to, in order
    profile: Profile = "driving-car"
    weights: Weights = Weights()


class Scores(BaseModel):
    surface: float | None = None
    views: float | None = None
    safety: float | None = None
    traffic: float | None = None
    parking: float | None = None


class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]  # [lon, lat]


class RouteOut(BaseModel):
    rank: int
    geometry: LineString
    distance_m: float
    duration_s: float
    score: float | None  # None when no rated segment lies on the route
    scores: Scores
    coverage: float  # share of the route length (0-1) that lies on rated segments
    segment_ids: list[int]


class RouteResponse(BaseModel):
    routes: list[RouteOut]
