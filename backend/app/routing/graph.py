"""Own routing graph (Supabase pgRouting, docs/ROUTING_GRAPH.md): routes for cars and bikes that follow the
priorities the user picked (weights 0-3 for surface, views, safety, traffic, parking).

The database does the search (`public.find_route`); this module snaps the points, asks for the
user's route and for the fastest one, and turns the edges into the `POST /route` response.
Pedestrians stay with the external engine (see router.py).
"""

from dataclasses import dataclass
from typing import Protocol

from psycopg_pool import ConnectionPool

from ..errors import AppError
from .schemas import DIMENSIONS, Point, Profile, RouteOut, Scores, Weights
from .scoring import overall_score

GRAPH_PROFILES: tuple[str, ...] = ("driving-car", "cycling-regular")
MAX_SNAP_M = 600.0  # a point farther than this from a road of the profile is refused (Old Town squares are ~500 m)


@dataclass(frozen=True)
class EdgeStep:
    """One edge of a found route, in travel order."""

    edge_id: int
    segment_id: int | None  # rated segment this edge was matched to
    length_m: float
    time_s: float
    rated: bool  # the matched segment has a score
    scores: dict[str, float | None]  # that segment's own scores; None = nobody rated the dimension
    coordinates: list[list[float]]  # [lon, lat] along the direction of travel


class GraphSource(Protocol):
    """Where routes come from. The PostgreSQL one is below; tests plug in a fake."""

    def snap_distance(self, profile: str, point: Point) -> float | None:
        """Metres from `point` to the nearest node of the profile's road network (None: no network)."""
        ...

    def find(self, profile: str, start: Point, end: Point, variants: list[Weights]) -> list[list[EdgeStep]]:
        """One route per entry of `variants` (empty list = no route), cheapest for those weights."""
        ...


_FIND_SQL = """
select seq, edge_id, segment_id, length_m, time_s, rated, st_asgeojson(geom, 6)::json as geometry
from public.find_route(%(profile)s, %(from_lon)s, %(from_lat)s, %(to_lon)s, %(to_lat)s,
  %(surface)s::integer, %(views)s::integer, %(safety)s::integer, %(traffic)s::integer, %(parking)s::integer)
order by seq
"""
_SCORES_SQL = """
select segment_id, surface, views, safety, traffic, parking
from public.segment_scores where segment_id = any(%s::integer[])
"""


class PostgresGraphSource:
    """Reads routes from `public.find_route` through the shared, bounded connection pool."""

    def __init__(self, pool: ConnectionPool | None):
        self._pool = pool

    def _require_pool(self) -> ConnectionPool:
        if self._pool is None:
            raise AppError(500, "INTERNAL_ERROR", "Brak konfiguracji bazy danych")
        return self._pool

    def snap_distance(self, profile: str, point: Point) -> float | None:
        with self._require_pool().connection() as conn:
            row = conn.execute("select distance_m from public.routing_snap(%s, %s, %s)",
                               (profile, point.lon, point.lat)).fetchone()
        return float(row["distance_m"]) if row else None

    def find(self, profile: str, start: Point, end: Point, variants: list[Weights]) -> list[list[EdgeStep]]:
        with self._require_pool().connection() as conn:
            found = []
            for weights in variants:
                params = {"profile": profile, "from_lon": start.lon, "from_lat": start.lat,
                          "to_lon": end.lon, "to_lat": end.lat, **weights.model_dump()}
                found.append(conn.execute(_FIND_SQL, params).fetchall())
            segment_ids = sorted({r["segment_id"] for rows in found for r in rows if r["segment_id"] is not None})
            scores = {r["segment_id"]: r for r in conn.execute(_SCORES_SQL, (segment_ids,)).fetchall()} if segment_ids else {}

        empty = {d: None for d in DIMENSIONS}
        return [
            [
                EdgeStep(
                    edge_id=r["edge_id"], segment_id=r["segment_id"], length_m=r["length_m"], time_s=r["time_s"],
                    rated=r["rated"],
                    scores={d: scores[r["segment_id"]][d] for d in DIMENSIONS} if r["segment_id"] in scores else empty,
                    coordinates=r["geometry"]["coordinates"],
                )
                for r in rows
            ]
            for rows in found
        ]


def stitch(steps: list[EdgeStep]) -> list[list[float]]:
    """Join the edge geometries into one line; the shared point of two consecutive edges is kept once."""
    line: list[list[float]] = []
    for step in steps:
        coords = step.coordinates
        line.extend(coords[1:] if line and line[-1] == coords[0] else coords)
    return line


def step_scores(steps: list[EdgeStep]) -> dict[str, float | None]:
    """Per dimension, the mean of the rated edges' scores weighted by edge length (None: no ratings on the route)."""
    result: dict[str, float | None] = {}
    for dim in DIMENSIONS:
        rated = [(s.length_m, s.scores[dim]) for s in steps if s.scores.get(dim) is not None]
        total = sum(length for length, _ in rated)
        result[dim] = round(sum(length * score for length, score in rated) / total, 2) if total else None
    return result


def build_route(steps: list[EdgeStep], weights: Weights) -> RouteOut:
    """Turn the edges of one route into the contract's RouteOut (`rank` is set by the caller).

    `weights` are the user's priorities: they decide the overall `score` (the same for every returned route,
    so the routes can be compared). `coverage` is the share of the length lying on rated segments.
    """
    distance = sum(s.length_m for s in steps)
    scores = step_scores(steps)
    rated_length = sum(s.length_m for s in steps if s.rated)
    return RouteOut(
        rank=0,
        geometry={"coordinates": stitch(steps)},
        distance_m=round(distance, 1),
        duration_s=round(sum(s.time_s for s in steps), 1),
        score=overall_score(scores, weights),
        scores=Scores(**scores),
        coverage=round(min(1.0, rated_length / distance), 2) if distance > 0 else 0.0,
        segment_ids=sorted({s.segment_id for s in steps if s.segment_id is not None}),
    )


def graph_routes(source: GraphSource, profile: Profile, start: Point, end: Point, weights: Weights) -> list[RouteOut]:
    """Routes for a car or bike profile from the own graph.

    Without weights: the fastest route only. With weights: rank 1 is the best route for those priorities and
    rank 2 the fastest one (when it differs), so the user sees what the better route costs in time.
    """
    if profile not in GRAPH_PROFILES:
        raise AppError(422, "VALIDATION_ERROR", "Profile is not served by the own graph", {"field": "profile"})
    for name, point in (("from", start), ("to", end)):
        distance = source.snap_distance(profile, point)
        if distance is None or distance > MAX_SNAP_M:
            raise AppError(404, "NOT_FOUND", "No route found: a point is not near a road for this profile",
                           {"profile": profile, "field": name})

    fastest = Weights()
    variants = [weights, fastest] if weights != fastest else [fastest]
    paths = source.find(profile, start, end, variants)
    if not all(paths):
        raise AppError(404, "NOT_FOUND", "No route found", {"profile": profile})
    if len(paths) == 2 and [s.edge_id for s in paths[0]] == [s.edge_id for s in paths[1]]:
        paths = paths[:1]
    return [build_route(steps, weights).model_copy(update={"rank": i}) for i, steps in enumerate(paths, start=1)]
