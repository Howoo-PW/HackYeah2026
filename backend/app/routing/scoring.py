"""Route scoring: length-weighted segment averages, then a user-weighted overall score."""

from .schemas import DIMENSIONS, RouteOut, Scores, Weights
from .segments import SegmentMatch


def dimension_scores(matches: list[SegmentMatch]) -> dict[str, float | None]:
    """Per dimension: mean of segment scores weighted by how much of each segment lies on the route."""
    result: dict[str, float | None] = {}
    for dim in DIMENSIONS:
        rated = [(m.overlap_m, m.scores[dim]) for m in matches if m.scores.get(dim) is not None]
        total = sum(length for length, _ in rated)
        result[dim] = round(sum(length * s for length, s in rated) / total, 2) if total else None
    return result


def overall_score(scores: dict[str, float | None], weights: Weights) -> float | None:
    """Mean of the dimensions the user weighted (by weight); with no weights, plain mean of all rated dimensions."""
    weight_of = weights.model_dump()
    chosen = {d: weight_of[d] for d in DIMENSIONS if weight_of[d] > 0 and scores[d] is not None}
    if not chosen:
        chosen = {d: 1 for d in DIMENSIONS if scores[d] is not None}
    total = sum(chosen.values())
    return round(sum(scores[d] * w for d, w in chosen.items()) / total, 2) if total else None


def coverage(matches: list[SegmentMatch], route_length_m: float) -> float:
    if route_length_m <= 0:
        return 0.0
    return round(min(1.0, sum(m.overlap_m for m in matches) / route_length_m), 2)


def rank(routes: list[RouteOut], weights: Weights) -> list[RouteOut]:
    """Best score first (unrated last). With no weights at all the fastest route wins, as in a normal navigator."""
    if not any(weights.model_dump().values()):
        ordered = sorted(routes, key=lambda r: r.duration_s)
    else:
        ordered = sorted(routes, key=lambda r: (r.score is None, -(r.score or 0), r.duration_s))
    return [r.model_copy(update={"rank": i}) for i, r in enumerate(ordered, start=1)]


__all__ = ["dimension_scores", "overall_score", "coverage", "rank", "Scores"]
