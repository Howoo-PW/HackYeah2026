"""Request and response models for the AI service (docs/CONTRACT.md, section 6)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

Confidence = Literal["low", "medium", "high"]


class ScoresIn(BaseModel):
    """Scores on the 1-5 scale (5 = best); a dimension nobody rated is null. Averages may be fractional."""

    surface: float | None = Field(default=None, ge=1, le=5)
    views: float | None = Field(default=None, ge=1, le=5)
    safety: float | None = Field(default=None, ge=1, le=5)
    traffic: float | None = Field(default=None, ge=1, le=5)
    parking: float | None = Field(default=None, ge=1, le=5)


class CommentIn(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=1000)
    created_at: datetime
    # Optional extension of the contract: the author's own rating of this road, so the model sees opinion and score together.
    rating: ScoresIn | None = None


def _https(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError("image URLs must be HTTPS")
    return url


class SummarizeRequest(BaseModel):
    segment_id: int
    language: str = "pl"
    # May be empty when photos are attached: a photo alone is enough for a summary.
    comments: list[CommentIn] = Field(default_factory=list, max_length=50)
    # Optional extension of the contract: the road's average scores and how many ratings they come from.
    scores: ScoresIn | None = None
    ratings_count: int = Field(default=0, ge=0)
    # Optional extension of the contract: up to 4 photos of the road (HTTPS URLs the model provider can fetch) to describe the surface.
    image_urls: list[Annotated[str, AfterValidator(_https)]] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def has_material(self):
        """A summary needs something to summarize: at least one comment or one photo."""
        if not self.comments and not self.image_urls:
            raise ValueError("At least one comment or photo is required")
        return self


class SummaryContent(BaseModel):
    """Fields the model generates. The descriptions are sent to the LLM as the output schema."""

    surface: str = Field(description="One short sentence (max 15 words) on the road surface (type and condition, e.g. cracks or potholes visible in the photos or mentioned in comments), or 'brak informacji' only if neither comments nor photos say anything about it")
    views: str = Field(description="One short sentence (max 15 words) on the views from comments or photos, or 'brak informacji' if neither says anything")
    safety: str = Field(description="One short sentence (max 15 words) on safety from comments or photos, or 'brak informacji' if neither says anything")
    traffic: str = Field(description="One short sentence (max 15 words) on traffic and road problems from comments or photos, or 'brak informacji' if neither says anything")
    parking: str = Field(description="One short sentence (max 15 words) on parking from comments or photos, or 'brak informacji' if neither says anything")
    overall: str = Field(description="Exactly one sentence (max 25 words): the overall summary")
    confidence: Confidence = Field(description="How well the comments support the summary")
    conflicts: list[str] = Field(description="Topics where comments contradict each other")


class SummaryOut(SummaryContent):
    comments_count: int
    model: str


class SurfaceRequest(BaseModel):
    segment_id: int
    image_urls: list[str] = Field(min_length=1, max_length=10)


class SurfaceOut(BaseModel):
    surface: str = Field(description="Surface type, e.g. asphalt, cobblestone, gravel, dirt")
    condition: int = Field(ge=1, le=5, description="1 = destroyed, 5 = smooth and new")
    potholes: bool
    cracks: bool
    confidence: Confidence
