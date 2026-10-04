"""Effective scores: every segment gets a score even when only its neighbours were rated.

A segment's own ratings are shrunk toward the mean of its fragment (segment group), and the fragment
mean toward the mean of the road type. Pure functions over `{dimension: (ratings count, sum)}` maps;
the fragments themselves are built offline (scripts/fragments.py).
"""

from .schemas import DIMENSIONS

K_SEGMENT = 2.0  # own ratings needed to weigh as much as the group mean
K_GROUP = 3.0    # group ratings needed to weigh as much as the road-type mean

Agg = dict  # {dimension: (count, sum)}


def _mean(count: int, total: float) -> float | None:
    return total / count if count else None


def group_scores(group: Agg, highway: Agg) -> dict[str, float | None]:
    """Group mean per dimension, pulled toward the road-type mean while the group has few ratings."""
    out: dict[str, float | None] = {}
    for d in DIMENSIONS:
        gn, gs = group.get(d, (0, 0.0))
        prior = _mean(*highway.get(d, (0, 0.0)))
        if not gn:
            out[d] = None
        elif prior is None:
            out[d] = round(gs / gn, 2)
        else:
            out[d] = round((gs + K_GROUP * prior) / (gn + K_GROUP), 2)
    return out


def effective_scores(own: Agg, group: Agg, highway: Agg):
    """Return (scores, source, confidence) for one segment.

    own/group/highway map a dimension to (ratings count, sum of ratings); `group` includes the
    segment's own ratings, which are taken out so they are not counted twice.
    """
    scores: dict[str, float | None] = {}
    evidence = 0.0
    has_own = False
    for d in DIMENSIONS:
        on, os_ = own.get(d, (0, 0.0))
        gn, gs = group.get(d, (0, 0.0))
        rest_n, rest_s = max(gn - on, 0), max(gs - os_, 0.0)
        prior = _mean(*highway.get(d, (0, 0.0)))
        rest_mean = None
        if rest_n:
            rest_mean = (rest_s + K_GROUP * prior) / (rest_n + K_GROUP) if prior is not None else rest_s / rest_n
        if on:
            has_own = True
            base = rest_mean if rest_mean is not None else (prior if prior is not None else os_ / on)
            scores[d] = round((os_ + K_SEGMENT * base) / (on + K_SEGMENT), 2)
        else:
            scores[d] = round(rest_mean, 2) if rest_mean is not None else None
        evidence = max(evidence, on + 0.5 * rest_n)
    if all(v is None for v in scores.values()):
        return scores, "none", "none"
    confidence = "high" if evidence >= 5 else "medium" if evidence >= 2 else "low"
    return scores, "own" if has_own else "group", confidence
