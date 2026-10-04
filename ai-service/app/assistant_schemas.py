"""Assistant: a natural-language request becomes a plan, and facts from the database become an answer (docs/ASSISTANT.md)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Profile = Literal["driving-car", "cycling-regular", "foot-walking"]
Dimension = Literal["surface", "views", "safety", "traffic", "parking"]


class AssistantRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    language: str = "pl"


class PlanWeights(BaseModel):
    """How much each road-quality dimension matters for a route: 0 = not at all ... 3 = very much (contract 5.8)."""

    surface: int = Field(default=0, ge=0, le=3, description="Smooth surface, no potholes")
    views: int = Field(default=0, ge=0, le=3, description="Nice views, scenery")
    safety: int = Field(default=0, ge=0, le=3, description="Safe, well lit")
    traffic: int = Field(default=0, ge=0, le=3, description="Calm: little traffic, no jams")


class AssistantPlan(BaseModel):
    """What the user wants, in a form the backend can execute. The descriptions are sent to the LLM as the output schema."""

    intent: Literal["route", "place", "streets", "unsupported"] = Field(
        description="route = get from one place to another; place = show one specific place or street; "
        "streets = find streets that are best/worst by a criterion; unsupported = not about roads or places in Krakow"
    )
    restated: str = Field(description="One short sentence in Polish saying what the user wants, in your own words")
    from_place: str | None = Field(default=None, description="route: where it starts, as a searchable place name in nominative case (e.g. 'Rynek Główny'), else null")
    to_place: str | None = Field(default=None, description="route: where it ends, as a searchable place name in nominative case, else null")
    via_places: list[str] = Field(default_factory=list, max_length=3, description="route: concrete streets/places the route must pass through, in order, only when the user names them ('przez Planty', 'przez ulicę X'); empty for 'along the Vistula' (use along_river)")
    along_river: bool = Field(default=False, description="route: true when the route should follow the Vistula / the river bank ('wzdłuż Wisły', 'nad rzeką', 'bulwarami'); the app picks the points on the bank itself")
    profile: Profile = Field(default="driving-car", description="driving-car (default), cycling-regular for a bike, foot-walking for walking")
    weights: PlanWeights = Field(default_factory=PlanWeights, description="route: what matters to the user; all zeros = simply the fastest route")
    place_query: str | None = Field(default=None, description="place: the place or street to show, in nominative case, else null")
    area: str | None = Field(default=None, description="streets: a district or area of Krakow to look in (e.g. 'Kazimierz'), null = the whole city")
    dimension: Dimension | None = Field(default=None, description="streets: the criterion (surface, views, safety, traffic = calm, parking), else null")
    topic: str | None = Field(default=None, description="streets: when no single criterion fits and the user describes the kind of road in words ('spokojna droga nad wodą', 'klimatyczne uliczki', 'ścieżka wśród zieleni'), that description in Polish; dimension is then null; else null")
    want: Literal["best", "worst"] = Field(default="best", description="streets: the best or the worst ones")
    count: int = Field(default=3, ge=1, le=5, description="streets: how many to find")


class PlanOut(AssistantPlan):
    model: str


class AnswerRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    intent: Literal["route", "place", "streets"]
    # Plain sentences built by the backend from the database (route, ratings in words, comments, obstacles).
    facts: list[Annotated[str, Field(max_length=700)]] = Field(min_length=1, max_length=40)
    language: str = "pl"


class AnswerContent(BaseModel):
    answer: str = Field(description="2 to 5 sentences in Polish answering the user, using only the facts")


class AnswerOut(AnswerContent):
    model: str


EMBED_DIMENSIONS = 1536


class EmbedRequest(BaseModel):
    texts: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=64)


class EmbedOut(BaseModel):
    vectors: list[list[float]]
    model: str
