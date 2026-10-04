"""POST /api/v1/route: routes for cars, bikes and pedestrians from the own graph (graph.py).

For the user's priorities (weights) the best route comes first, followed by the fastest one when it differs.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from ..errors import AppError
from .geo import in_krakow
from .graph import GraphSource, PostgresGraphSource, graph_routes
from .schemas import RouteRequest, RouteResponse

ROUTE_LIMIT_PER_MINUTE = 30  # docs/CONTRACT.md, section 9: POST /route, per IP

router = APIRouter(tags=["routing"])


def get_graph_source(request: Request) -> GraphSource:
    """The own graph in Supabase, through the application's connection pool (checked when first used)."""
    return PostgresGraphSource(request.app.state.db_pool)


@router.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest, request: Request, graph: GraphSource = Depends(get_graph_source)) -> RouteResponse:
    """Routes between two points in the service area, best for the user's weights first (docs/CONTRACT.md, section 5.8)."""
    client_ip = request.client.host if request.client else "unknown"
    await run_in_threadpool(request.app.state.rate_limiter.check, client_ip, "route", ROUTE_LIMIT_PER_MINUTE, 60)

    stops = [("from", req.from_), *((f"via[{i}]", p) for i, p in enumerate(req.via)), ("to", req.to)]
    for name, point in stops:
        if not in_krakow(point.lat, point.lon):
            raise AppError(422, "OUT_OF_AREA", "Point is outside the service area", {"field": name})

    routes = await run_in_threadpool(graph_routes, graph, req.profile, req.from_, req.to, req.weights, req.via)
    return RouteResponse(routes=routes)
