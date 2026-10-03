"""POST /api/v1/route.

Cars and bikes: the own graph (graph.py) finds the route that follows the user's priorities, plus the fastest one.
Pedestrians: alternative routes from the external provider, ranked by how well they match the priorities.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from shapely.geometry import LineString

from ..errors import AppError
from .geo import in_krakow
from .graph import GRAPH_PROFILES, GraphSource, PostgresGraphSource, graph_routes
from .providers import RouteProvider, build_provider
from .schemas import LineString as GeoLineString
from .schemas import RouteOut, RouteRequest, RouteResponse, Scores
from .scoring import coverage, dimension_scores, overall_score, rank
from .segments import InMemorySegmentSource, SegmentSource

MATCH_BUFFER_M = 15.0  # a segment counts as "on the route" within this distance of the route line
MIN_SHARE = 0.5  # ...and only if at least this share of its length lies there (ignores junctions, crossings)
ROUTE_LIMIT_PER_MINUTE = 30  # docs/CONTRACT.md, section 9: POST /route, per IP

router = APIRouter(tags=["routing"])


@lru_cache
def get_provider() -> RouteProvider:
    return build_provider()


@lru_cache
def get_segment_source() -> SegmentSource:
    return InMemorySegmentSource.from_file()


def get_graph_source(request: Request) -> GraphSource:
    """The own graph in Supabase, through the application's connection pool (checked when first used)."""
    return PostgresGraphSource(request.app.state.db_pool)


@router.post("/route", response_model=RouteResponse)
async def route(
    req: RouteRequest,
    request: Request,
    provider: RouteProvider = Depends(get_provider),
    segments: SegmentSource = Depends(get_segment_source),
    graph: GraphSource = Depends(get_graph_source),
) -> RouteResponse:
    """Routes between two points in Kraków, best for the user's weights first (docs/CONTRACT.md, section 5.8)."""
    client_ip = request.client.host if request.client else "unknown"
    await run_in_threadpool(request.app.state.rate_limiter.check, client_ip, "route", ROUTE_LIMIT_PER_MINUTE, 60)

    stops = [("from", req.from_), *((f"via[{i}]", p) for i, p in enumerate(req.via)), ("to", req.to)]
    for name, point in stops:
        if not in_krakow(point.lat, point.lon):
            raise AppError(422, "OUT_OF_AREA", "Point is outside Kraków", {"field": name})

    if req.profile in GRAPH_PROFILES:
        routes = await run_in_threadpool(graph_routes, graph, req.profile, req.from_, req.to, req.weights, req.via)
        return RouteResponse(routes=routes)

    raw_routes = await provider.routes(req.from_, req.to, req.profile, req.via)
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
