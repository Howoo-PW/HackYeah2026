"""Effective scores: segment scores shrunk toward the fragment and road-type means."""

import pytest

from app.effective_scores import effective_scores, group_scores


def agg(**dims):
    return {d: v for d, v in dims.items()}


def test_unrated_street_has_no_score():
    scores, source, confidence = effective_scores({}, {}, {"surface": (100, 300.0)})
    assert source == "none" and confidence == "none" and all(v is None for v in scores.values())


def test_neighbours_rating_gives_estimated_score_pulled_toward_road_type():
    # Group: one rating of 5 on another segment; road-type mean 3.0 -> (5 + 3*3) / (1 + 3) = 3.5
    scores, source, confidence = effective_scores({}, {"surface": (1, 5.0)}, {"surface": (50, 150.0)})
    assert source == "group" and confidence == "low" and scores["surface"] == 3.5
    assert scores["views"] is None


def test_own_ratings_dominate_and_are_not_double_counted():
    own = {"surface": (4, 4.0)}                  # four 1-star ratings on this segment
    group = {"surface": (6, 4.0 + 10.0)}         # group includes them + two 5-star ratings elsewhere
    scores, source, confidence = effective_scores(own, group, {})
    rest = 5.0                                    # neighbours only: (10)/(2)
    assert source == "own"
    assert scores["surface"] == pytest.approx((4.0 + 2.0 * rest) / (4 + 2.0), abs=0.01)
    assert confidence == "high"


def test_segment_with_only_own_ratings_still_scores():
    scores, source, _ = effective_scores({"safety": (1, 2.0)}, {"safety": (1, 2.0)}, {})
    assert source == "own" and scores["safety"] == 2.0


def test_group_scores_use_road_type_prior():
    out = group_scores({"surface": (2, 10.0)}, {"surface": (100, 300.0)})
    assert out["surface"] == pytest.approx((10.0 + 3 * 3.0) / (2 + 3), abs=0.01)
    assert out["views"] is None
