"""The overall score of a route: the user-weighted mean of its dimension scores."""

from .schemas import DIMENSIONS, Weights


def overall_score(scores: dict[str, float | None], weights: Weights) -> float | None:
    """Mean of the dimensions the user weighted (by weight); with no weights, plain mean of all rated dimensions."""
    weight_of = weights.model_dump()
    chosen = {d: weight_of[d] for d in DIMENSIONS if weight_of[d] > 0 and scores[d] is not None}
    if not chosen:
        chosen = {d: 1 for d in DIMENSIONS if scores[d] is not None}
    total = sum(chosen.values())
    return round(sum(scores[d] * w for d, w in chosen.items()) / total, 2) if total else None
