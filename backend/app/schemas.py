"""Core request and response models matching docs/CONTRACT.md."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DIMENSIONS = ("surface", "views", "safety", "traffic", "parking")


class Dimension(StrEnum):
    surface = "surface"
    views = "views"
    safety = "safety"
    traffic = "traffic"
    parking = "parking"


class TimeOfDay(StrEnum):
    morning = "morning"
    day = "day"
    evening = "evening"
    night = "night"


class Scores(BaseModel):
    surface: float | None = None
    views: float | None = None
    safety: float | None = None
    traffic: float | None = None
    parking: float | None = None


Score = Annotated[int, Field(strict=True, ge=1, le=5)]


class RatingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surface: Score | None = None
    views: Score | None = None
    safety: Score | None = None
    traffic: Score | None = None
    parking: Score | None = None
    time_of_day: TimeOfDay | None = None

    @model_validator(mode="after")
    def has_score(self):
        """Require at least one non-null rating dimension."""
        if not any(getattr(self, dimension) is not None for dimension in DIMENSIONS):
            raise ValueError("At least one score is required")
        return self


class Rating(Scores):
    id: UUID
    segment_id: int
    surface: int | None = None
    views: int | None = None
    safety: int | None = None
    traffic: int | None = None
    parking: int | None = None
    time_of_day: TimeOfDay
    created_at: datetime


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def non_blank(self):
        """Reject whitespace-only comments."""
        if not self.text.strip():
            raise ValueError("Comment cannot be blank")
        return self


class ContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["visible", "hidden"]


class Author(BaseModel):
    id: UUID
    display_name: str


class Comment(BaseModel):
    id: UUID
    segment_id: int
    author: Author
    text: str
    status: Literal["visible", "hidden"]
    created_at: datetime


class CommentPage(BaseModel):
    items: list[Comment]
    page: int
    page_size: int
    total: int


class Profile(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: Literal["user", "admin"]
    created_at: datetime


class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class SegmentProperties(BaseModel):
    id: int
    osm_way_id: int
    name: str | None
    highway: str
    length_m: float
    scores: Scores
    ratings_count: int
    active_obstacles_count: int


class NearestSegment(SegmentProperties):
    distance_m: float


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: LineString
    properties: SegmentProperties


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class Summary(BaseModel):
    surface: str
    views: str
    safety: str
    traffic: str
    parking: str
    overall: str
    confidence: Literal["low", "medium", "high"]
    conflicts: list[str]
    comments_count: int
    model: str
    updated_at: datetime


class Location(BaseModel):
    lat: float
    lon: float


class Obstacle(BaseModel):
    id: UUID
    segment_id: int | None
    type: Literal["roadwork", "closure", "pothole", "accident", "other"]
    description: str | None
    location: Location
    valid_until: datetime | None
    reported_by: UUID
    created_at: datetime


class SegmentDetail(SegmentProperties):
    geometry: LineString
    surface_osm: str | None
    smoothness_osm: str | None
    maxspeed: int | None
    lit: bool | None
    last_rating_at: datetime | None
    scores_by_time_of_day: dict[TimeOfDay, Scores]
    summary: Summary | None
    obstacles: list[Obstacle]
    photos_count: int
    my_rating: Rating | None
