"""POST /api/v1/assistant: a request in words becomes a route, a place on the map or a list of streets (docs/ASSISTANT.md).

Not an agent loop: the AI service first reads the request into a plan (route / place / streets), this module then runs the plan with
ordinary code (geocoding, the own routing graph, the database) and gathers facts (ratings in words, comments, summaries, obstacles),
and the AI service writes the reply from those facts only. The model never touches the database or invents streets.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import assistant_facts as facts
from .assistant_data import AssistantData
from .config import settings
from .errors import AppError
from .geocoding import Found, Geocoder, get_geocoder
from .repository import time_of_day as current_time_of_day
from .routing.geo import in_krakow
from .routing.graph import PostgresGraphSource, graph_routes
from .routing.schemas import Point, RouteOut, Scores, Weights

log = logging.getLogger("assistant")

ASSISTANT_LIMIT_PER_MINUTE = 10  # per IP: every request costs two model calls
AI_TIMEOUT_S = 20  # plan and answer are separate calls, each below the AI service's own 12 s limit
MAX_FACTS = 40
HINT = "Opisz trasę (np. „rowerem z Rynku Głównego na Wawel, ładne widoki”), miejsce (np. „pokaż Lokum Salsa”) albo kryterium (np. „najlepsza nawierzchnia na Podgórzu”)."

RouteRunner = Callable[[str, Point, Point, Weights, list[Point], str], Awaitable[list[RouteOut]]]


# ---- request / response ------------------------------------------------------------------------------------------------

class AssistantRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)


class NamedPoint(BaseModel):
    name: str
    lat: float
    lon: float


class AssistantRoute(BaseModel):
    """The interpreted request and the routes for it (same shape as POST /route returns), so the app can show and adjust them."""

    model_config = ConfigDict(populate_by_name=True)

    from_: NamedPoint = Field(alias="from")
    to: NamedPoint
    via: list[NamedPoint] = Field(default_factory=list)
    profile: str
    weights: Weights
    routes: list[RouteOut]


class AssistantPlace(BaseModel):
    name: str
    lat: float
    lon: float
    segment_id: int | None = None


class AssistantStreet(BaseModel):
    """A rated fragment of a street found by a criterion."""

    name: str
    group_id: int
    highway: str | None = None
    length_m: float
    location: NamedPoint
    segment_ids: list[int]
    scores: Scores
    ratings_count: int
    score: float | None = None


class AssistantResponse(BaseModel):
    intent: Literal["route", "place", "streets", "clarify"]
    interpretation: str  # what was understood, in one sentence
    answer: str
    model: str
    route: AssistantRoute | None = None
    place: AssistantPlace | None = None
    streets: list[AssistantStreet] = Field(default_factory=list)


# ---- the AI service ----------------------------------------------------------------------------------------------------

class AiPlan(BaseModel):
    """What the AI service returns for POST /assistant/plan."""

    intent: Literal["route", "place", "streets", "unsupported"]
    restated: str
    from_place: str | None = None
    to_place: str | None = None
    via_places: list[str] = Field(default_factory=list)
    profile: Literal["driving-car", "cycling-regular", "foot-walking"] = "driving-car"
    weights: dict[str, int] = Field(default_factory=dict)
    place_query: str | None = None
    area: str | None = None
    dimension: Literal["surface", "views", "safety", "traffic", "parking"] | None = None
    want: Literal["best", "worst"] = "best"
    count: int = Field(default=3, ge=1, le=5)
    model: str = ""


class AiClient:
    """Calls the AI service (internal key header); any failure becomes a 502 the endpoint turns into a plain message."""

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT_S) as client:
                response = await client.post(f"{settings.ai_service_url}{path}", json=payload, headers={"X-Internal-Key": settings.internal_api_key})
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise AppError(502, "AI_UNAVAILABLE", "Asystent AI jest chwilowo niedostępny") from None

    async def plan(self, query: str) -> AiPlan:
        try:
            return AiPlan(**await self._post("/assistant/plan", {"query": query, "language": "pl"}))
        except ValidationError:
            raise AppError(502, "AI_UNAVAILABLE", "Asystent AI zwrócił nieczytelną odpowiedź") from None

    async def answer(self, query: str, intent: str, fact_lines: list[str]) -> tuple[str, str]:
        out = await self._post("/assistant/answer", {"query": query, "intent": intent, "facts": [f[:700] for f in fact_lines[:MAX_FACTS]], "language": "pl"})
        return str(out["answer"]), str(out.get("model", ""))


@dataclass
class Deps:
    ai: AiClient
    geo: Geocoder
    data: AssistantData
    routes: RouteRunner


# ---- running a plan ----------------------------------------------------------------------------------------------------

def clarify(plan: AiPlan | None, text: str) -> AssistantResponse:
    """No result, only a message: the request was not understood or something in it could not be found."""
    return AssistantResponse(intent="clarify", interpretation=plan.restated if plan else "", answer=text, model=plan.model if plan else "")


async def write_answer(d: Deps, query: str, intent: str, fact_lines: list[str]) -> tuple[str, str]:
    """The model's reply from the facts; without the model the facts themselves are the reply (the result is shown either way)."""
    try:
        return await d.ai.answer(query, intent, fact_lines)
    except AppError:
        log.warning("assistant answer failed; using the facts as the reply")
        return " ".join(fact_lines[:4]), "fallback"


def route_error_text(exc: AppError, names: list[str]) -> str:
    """A reply for a route that could not be found (a point far from roads, no path, a profile the graph does not serve)."""
    field = (exc.details or {}).get("field")
    if exc.status == 404 and field:
        which = {"from": names[0], "to": names[-1]}.get(field)
        if which is None and field.startswith("via["):
            which = names[1 + int(field[4:-1])]
        return f"Miejsce „{which}” jest za daleko od drogi dla wybranego środka transportu. Spróbuj podać inne miejsce lub ulicę."
    if exc.status == 422:
        return "Dla tego środka transportu nie wyznaczam jeszcze tras."
    return "Nie udało się wyznaczyć trasy między tymi miejscami."


def named(found: Found) -> NamedPoint:
    return NamedPoint(name=found.name, lat=found.lat, lon=found.lon)


async def do_route(plan: AiPlan, query: str, d: Deps) -> AssistantResponse:
    if not plan.from_place or not plan.to_place:
        return clarify(plan, "Podaj, skąd i dokąd chcesz jechać. " + HINT)
    wanted = [plan.from_place, *plan.via_places[:3], plan.to_place]
    places: list[Found] = []
    for text in wanted:
        found = await d.geo.find(text)
        if found is None or not in_krakow(found.lat, found.lon):
            return clarify(plan, f"Nie znalazłem w Krakowie miejsca „{text}”. Spróbuj podać dokładniejszą nazwę lub ulicę.")
        places.append(found)

    weights = Weights(**{k: v for k, v in plan.weights.items() if k in ("surface", "views", "safety", "traffic")})
    tod = current_time_of_day(datetime.now(timezone.utc)).value
    point = lambda f: Point(lat=f.lat, lon=f.lon)  # noqa: E731
    try:
        routes = await d.routes(plan.profile, point(places[0]), point(places[-1]), weights, [point(p) for p in places[1:-1]], tod)
    except AppError as exc:
        return clarify(plan, route_error_text(exc, [p.name for p in places]))

    main = routes[0]
    fastest = next((r for r in routes if r.rank == 2), None)
    start, end, via = places[0], places[-1], places[1:-1]
    lines = facts.route_facts(main.model_dump(), fastest.model_dump() if fastest else None, plan.profile, weights.model_dump(),
                              start.name, end.name, [p.name for p in via])
    lines += await run_in_threadpool(d.data.segment_facts, main.segment_ids)
    answer, model = await write_answer(d, query, "route", lines)
    return AssistantResponse(
        intent="route", interpretation=plan.restated, answer=answer, model=model or plan.model,
        route=AssistantRoute(**{"from": named(start)}, to=named(end), via=[named(p) for p in via], profile=plan.profile, weights=weights, routes=routes),
    )


async def do_place(plan: AiPlan, query: str, d: Deps) -> AssistantResponse:
    if not plan.place_query:
        return clarify(plan, "Jakie miejsce mam pokazać? " + HINT)
    found = await d.geo.find(plan.place_query)
    if found is None or not in_krakow(found.lat, found.lon):
        return clarify(plan, f"Nie znalazłem w Krakowie miejsca „{plan.place_query}”.")
    segment = await run_in_threadpool(d.data.nearest_segment, found.lat, found.lon)
    lines = [f"Miejsce: {found.name}."]
    if segment:
        ids = await run_in_threadpool(d.data.group_segment_ids, segment["group_id"]) if segment["group_id"] else [segment["id"]]
        lines += await run_in_threadpool(d.data.segment_facts, ids or [segment["id"]], False)
    else:
        lines.append("W pobliżu tego miejsca nie ma drogi, którą oceniali użytkownicy.")
    answer, model = await write_answer(d, query, "place", lines)
    return AssistantResponse(
        intent="place", interpretation=plan.restated, answer=answer, model=model or plan.model,
        place=AssistantPlace(name=found.name, lat=found.lat, lon=found.lon, segment_id=segment["id"] if segment else None),
    )


async def do_streets(plan: AiPlan, query: str, d: Deps) -> AssistantResponse:
    if plan.dimension is None:
        return clarify(plan, "Według jakiego kryterium mam szukać: nawierzchni, widoków, bezpieczeństwa czy ruchu? " + HINT)
    bbox, outline = None, None
    if plan.area:
        area = await d.geo.find(plan.area, area=True)
        if area is None:
            return clarify(plan, f"Nie znalazłem w Krakowie okolicy „{plan.area}”.")
        pad = 0.012
        bbox = area.bbox or (area.lon - pad, area.lat - pad * 0.7, area.lon + pad, area.lat + pad * 0.7)
        outline = area.outline  # the district's real shape when OpenStreetMap has one, else the box above
    rows = await run_in_threadpool(d.data.top_fragments, plan.dimension, plan.want, bbox, plan.count, outline)
    where = f" w okolicy „{plan.area}”" if plan.area else ""
    if not rows:
        return clarify(plan, f"Nie mam jeszcze wystarczająco ocen, żeby wskazać takie ulice{where}.")

    streets, lines = [], [
        f"Kryterium: {facts.LABELS[plan.dimension]}; szukano {'najlepszych' if plan.want == 'best' else 'najgorszych'} fragmentów ulic{where}.",
    ]
    for row in rows:
        ids = await run_in_threadpool(d.data.group_segment_ids, row["group_id"])
        scores = {k: row[k] for k in facts.DIMENSIONS}
        present = [v for v in scores.values() if v is not None]
        streets.append(AssistantStreet(
            name=row["name"], group_id=row["group_id"], highway=row["highway"], length_m=row["length_m"],
            location=NamedPoint(name=row["name"], lat=row["lat"], lon=row["lon"]), segment_ids=ids,
            scores=Scores(**scores), ratings_count=row["ratings"], score=round(sum(present) / len(present), 2) if present else None,
        ))
        lines.append(facts.street_fact({**scores, "name": row["name"], "length_m": row["length_m"], "ratings": row["ratings"]}, on_route=False))
    lines += await run_in_threadpool(d.data.segment_facts, streets[0].segment_ids, False)  # the top street's comments, summary, obstacles
    answer, model = await write_answer(d, query, "streets", lines)
    return AssistantResponse(intent="streets", interpretation=plan.restated, answer=answer, model=model or plan.model, streets=streets)


async def handle(query: str, d: Deps) -> AssistantResponse:
    """Run the whole pipeline for one request."""
    plan = await d.ai.plan(query)
    if plan.intent == "unsupported":
        return clarify(plan, f"{plan.restated} {HINT}".strip())
    run = {"route": do_route, "place": do_place, "streets": do_streets}[plan.intent]
    return await run(plan, query, d)


# ---- endpoint ----------------------------------------------------------------------------------------------------------

router = APIRouter(tags=["assistant"])


def get_deps(request: Request, geo: Geocoder = Depends(get_geocoder)) -> Deps:
    pool = request.app.state.db_pool
    if pool is None:
        raise AppError(500, "INTERNAL_ERROR", "Brak konfiguracji bazy danych")
    source = PostgresGraphSource(pool)

    async def run_routes(profile, start, end, weights, via, tod):
        return await run_in_threadpool(graph_routes, source, profile, start, end, weights, via, tod)

    return Deps(ai=AiClient(), geo=geo, data=AssistantData(pool), routes=run_routes)


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(req: AssistantRequest, request: Request, deps: Deps = Depends(get_deps)) -> AssistantResponse:
    """Understand a request in words and answer with a route, a place or streets, using ratings, comments and obstacles."""
    client_ip = request.client.host if request.client else "unknown"
    await run_in_threadpool(request.app.state.rate_limiter.check, client_ip, "assistant", ASSISTANT_LIMIT_PER_MINUTE, 60)
    return await handle(req.query.strip(), deps)
