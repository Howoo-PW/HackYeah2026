"""POST /api/v1/route: alternative routes from the provider, ranked by how well they match the user's priorities."""

from functools import lru_cache

from fastapi import APIRouter, Depends
from shapely.geometry import LineString

from ..errors import AppError
from .geo import in_krakow
from .providers import RouteProvider, build_provider
from .schemas import LineString as GeoLineString
from .schemas import RouteOut, RouteRequest, RouteResponse, Scores
from .scoring import coverage, dimension_scores, overall_score, rank
from .segments import InMemorySegmentSource, SegmentSource

MATCH_BUFFER_M = 15.0  # a segment counts as "on the route" within this distance of the route line
MIN_SHARE = 0.5  # ...and only if at least this share of its length lies there (ignores junctions, crossings)

router = APIRouter(tags=["routing"])


@lru_cache
def get_provider() -> RouteProvider:
    return build_provider()


@lru_cache
def get_segment_source() -> SegmentSource:
    return InMemorySegmentSource.from_file()


@router.post("/route", response_model=RouteResponse)
async def route(
    req: RouteRequest,
    provider: RouteProvider = Depends(get_provider),
    segments: SegmentSource = Depends(get_segment_source),
) -> RouteResponse:
    for name, point in (("from", req.from_), ("to", req.to)):
        if not in_krakow(point.lat, point.lon):
            raise AppError(422, "OUT_OF_AREA", "Point is outside Kraków", {"field": name})

    raw_routes = await provider.routes(req.from_, req.to, req.profile)
    if not raw_routes:
        raise AppError(404, "NOT_FOUND", "No route found")

    routes = []
    for raw in raw_routes:
        line = LineString(raw.coordinates)
        matches = segments.matches(line, MATCH_BUFFER_M, MIN_SHARE)
        scores = dimension_scores(matches)
        routes.append(
            RouteOut(
                rank=0,  # set by rank()
                geometry=GeoLineString(coordinates=raw.coordinates),
                distance_m=raw.distance_m,
                duration_s=raw.duration_s,
                score=overall_score(scores, req.weights),
                scores=Scores(**scores),
                coverage=coverage(matches, raw.distance_m),
                segment_ids=sorted(m.id for m in matches),
            )
        )
    return RouteResponse(routes=rank(routes, req.weights))
