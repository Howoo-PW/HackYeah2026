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


class GroupRef(BaseModel):
    """The street stretch (about 500 m) a segment belongs to; users rate and see it as one unit."""

    id: int
    name: str | None
    highway: str
    length_m: float
    segments_count: int
    from_street: str | None
    to_street: str | None
    ratings_count: int


class MultiLineString(BaseModel):
    type: Literal["MultiLineString"] = "MultiLineString"
    coordinates: list[list[list[float]]]


class GroupDetail(GroupRef):
    scores: Scores
    geometry: MultiLineString
    segment_ids: list[int]


class GroupMapProperties(BaseModel):
    """One fragment for a zoomed-out map; `scores` has the same shape as on a segment so the layer is shared."""

    id: int
    kind: Literal["group"] = "group"
    name: str | None
    highway: str
    length_m: float
    segments_count: int
    ratings_count: int
    scores: Scores
    scores_source: Literal["own", "group", "none"]


class GroupMapFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: MultiLineString
    properties: GroupMapProperties


class GroupMapCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GroupMapFeature]


class SegmentProperties(BaseModel):
    id: int
    osm_way_id: int
    name: str | None
    highway: str
    length_m: float
    scores: Scores                      # effective: own ratings, else estimated from the group
    scores_own: Scores = Scores()       # plain averages of this segment's own ratings
    scores_source: Literal["own", "group", "none"] = "none"
    confidence: Literal["none", "low", "medium", "high"] = "none"
    group: GroupRef | None = None
    ratings_count: int                  # own ratings only
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
