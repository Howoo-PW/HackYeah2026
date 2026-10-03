"""Request and response models for the AI service (docs/CONTRACT.md, section 6)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]


class CommentIn(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=1000)
    created_at: datetime


class SummarizeRequest(BaseModel):
    segment_id: int
    language: str = "pl"
    comments: list[CommentIn] = Field(min_length=1, max_length=50)


class SummaryContent(BaseModel):
    """Fields the model generates. The descriptions are sent to the LLM as the output schema."""

    surface: str = Field(description="Road surface condition, or 'brak informacji' if nobody mentioned it")
    views: str = Field(description="Views along the road, or 'brak informacji'")
    safety: str = Field(description="Safety, or 'brak informacji'")
    traffic: str = Field(description="Traffic and road problems, or 'brak informacji'")
    parking: str = Field(description="Parking availability, or 'brak informacji'")
    overall: str = Field(description="One-sentence overall summary")
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
