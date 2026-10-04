"""Own routing graph (Supabase pgRouting, docs/ROUTING_GRAPH.md): routes for cars, bikes and pedestrians that
follow the priorities the user picked (weights 0-3 for surface, views, safety, traffic, parking).

The database does the search (`public.find_route`); this module snaps the points, asks for the
user's route and for the fastest one, and turns the edges into the `POST /route` response.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from psycopg_pool import ConnectionPool

from ..errors import AppError
from .schemas import DIMENSIONS, Point, Profile, RouteOut, Scores, Weights
from .scoring import overall_score

GRAPH_PROFILES: tuple[str, ...] = ("driving-car", "cycling-regular", "foot-walking")
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


@dataclass(frozen=True)
class Snap:
    """The node of the road network a point is attached to."""

    node_id: int
    distance_m: float


class GraphSource(Protocol):
    """Where routes come from. The PostgreSQL one is below; tests plug in a fake."""

    def snap(self, profile: str, point: Point) -> Snap | None:
        """Nearest node of the profile's road network and its distance (None: no network)."""
        ...

    def find(self, profile: str, legs: list[tuple[Point, Point]], variants: list[Weights]) -> list[list[EdgeStep]]:
        """One route per entry of `variants`, cheapest for those weights, driving all `legs` in order.

        A variant that has no route (any leg unreachable) comes back as an empty list.
        """
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

    def snap(self, profile: str, point: Point) -> Snap | None:
        with self._require_pool().connection() as conn:
            row = conn.execute("select node_id, distance_m from public.routing_snap(%s, %s, %s)",
                               (profile, point.lon, point.lat)).fetchone()
        return Snap(int(row["node_id"]), float(row["distance_m"])) if row else None

    def find(self, profile: str, legs: list[tuple[Point, Point]], variants: list[Weights]) -> list[list[EdgeStep]]:
        with self._require_pool().connection() as conn:
            found = []
            for weights in variants:
                rows: list[dict] = []
                for start, end in legs:
                    params = {"profile": profile, "from_lon": start.lon, "from_lat": start.lat,
                              "to_lon": end.lon, "to_lat": end.lat, **weights.model_dump()}
                    leg_rows = conn.execute(_FIND_SQL, params).fetchall()
                    if not leg_rows:  # a leg without a route means no route for this variant
                        rows = []
                        break
                    rows.extend(leg_rows)
                found.append(rows)
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


def graph_routes(source: GraphSource, profile: Profile, start: Point, end: Point, weights: Weights,
                 via: Sequence[Point] = ()) -> list[RouteOut]:
    """Routes for a car, bike or foot profile from the own graph, from `start` through the `via` stops (in order) to `end`.

    Without weights: the fastest route only. With weights: rank 1 is the best route for those priorities and
    rank 2 the fastest one (when it differs), so the user sees what the better route costs in time.
    Each stretch between two stops is searched separately and the stretches are joined.
    """
    if profile not in GRAPH_PROFILES:
        raise AppError(422, "VALIDATION_ERROR", "Profile is not served by the own graph", {"field": "profile"})

    stops = [("from", start), *((f"via[{i}]", p) for i, p in enumerate(via)), ("to", end)]
    snaps = []
    for name, point in stops:
        snap = source.snap(profile, point)
        if snap is None or snap.distance_m > MAX_SNAP_M:
            raise AppError(404, "NOT_FOUND", "No route found: a point is not near a road for this profile",
                           {"profile": profile, "field": name})
        snaps.append(snap)
    # stops that snap to the same node (a via on top of the previous stop) need no stretch of their own
    legs = [(stops[i][1], stops[i + 1][1]) for i in range(len(stops) - 1) if snaps[i].node_id != snaps[i + 1].node_id]
    if not legs:
        raise AppError(404, "NOT_FOUND", "No route found: start and destination are the same place", {"profile": profile})

    fastest = Weights()
    variants = [weights, fastest] if weights != fastest else [fastest]
    paths = source.find(profile, legs, variants)
    if not all(paths):
        raise AppError(404, "NOT_FOUND", "No route found", {"profile": profile})
    if len(paths) == 2 and [s.edge_id for s in paths[0]] == [s.edge_id for s in paths[1]]:
        paths = paths[:1]
    return [build_route(steps, weights).model_copy(update={"rank": i}) for i, steps in enumerate(paths, start=1)]
