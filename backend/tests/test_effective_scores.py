"""Segment grouping and effective scores on small synthetic road networks."""

import pytest

from app.grouping import SegmentRow, build_groups, effective_scores, group_scores


def seg(i, a, b, length=100.0, name="Długa", highway="residential", way=None):
    return SegmentRow(i, way or i, name, highway, length, a, b)


def by_member(groups):
    return {sid: g for g in groups for sid in g.segment_ids}


def test_consecutive_pieces_of_one_street_merge():
    segs = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0)), seg(3, (2, 0), (3, 0))]
    groups = build_groups(segs)
    assert len(groups) == 1
    assert groups[0].segment_ids == [1, 2, 3] and groups[0].length_m == 300.0


def test_a_crossing_street_does_not_break_the_chain_but_names_the_ends():
    # Długa runs through a junction with Basztowa (a T from the north) and ends at Pędzichów.
    segs = [
        seg(1, (0, 0), (1, 0)),
        seg(2, (1, 0), (2, 0)),
        seg(3, (1, 0), (1, 1), name="Basztowa", highway="primary"),
        seg(4, (2, 0), (3, 0), name="Pędzichów"),
    ]
    g = by_member(build_groups(segs))
    assert g[1] is g[2]
    assert g[1].segment_ids == [1, 2]            # Pędzichów is another street
    assert g[1].to_street == "Pędzichów" and g[1].from_street is None
    assert g[3] is not g[1]


def test_street_forking_into_two_same_name_branches_is_not_merged_across():
    segs = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0)), seg(3, (1, 0), (2, 1))]
    g = by_member(build_groups(segs))
    assert len({id(g[1]), id(g[2]), id(g[3])}) == 3


def test_different_road_type_or_name_never_merges():
    segs = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0), highway="tertiary"), seg(3, (2, 0), (3, 0), name="Inna")]
    assert len(build_groups(segs)) == 3


def test_unnamed_segments_merge_only_within_one_osm_way():
    segs = [seg(1, (0, 0), (1, 0), name=None, way=7), seg(2, (1, 0), (2, 0), name=None, way=7),
            seg(3, (2, 0), (3, 0), name=None, highway="cycleway", way=8)]
    g = by_member(build_groups(segs))
    assert g[1] is g[2] and g[3] is not g[1]


def test_unnamed_pieces_merge_across_ways_only_at_a_plain_continuation():
    chain = [seg(1, (0, 0), (1, 0), name=None, highway="cycleway", way=7),
             seg(2, (1, 0), (2, 0), name=None, highway="cycleway", way=8)]
    assert len(build_groups(chain)) == 1
    with_branch = chain + [seg(3, (1, 0), (1, 1), name=None, highway="cycleway", way=9)]
    assert len(build_groups(with_branch)) == 3
    other_type = [chain[0], seg(2, (1, 0), (2, 0), name=None, highway="residential", way=8)]
    assert len(build_groups(other_type)) == 2


def test_long_street_is_split_into_balanced_groups_in_street_order():
    segs = [seg(i, (i, 0), (i + 1, 0), length=250.0) for i in range(1, 9)]  # 2000 m
    groups = build_groups(segs)
    assert [round(g.length_m) for g in groups] == [500, 500, 500, 500]
    flat = [sid for g in groups for sid in g.segment_ids]
    assert flat == list(range(1, 9)) or flat == list(range(8, 0, -1))


def test_street_shorter_than_target_stays_one_group():
    segs = [seg(i, (i, 0), (i + 1, 0), length=40.0) for i in range(1, 6)]
    assert len(build_groups(segs)) == 1


def test_closed_ring_does_not_loop_forever_and_keeps_every_segment():
    ring = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (1, 1)), seg(3, (1, 1), (0, 1)), seg(4, (0, 1), (0, 0))]
    groups = build_groups(ring)
    assert sorted(sid for g in groups for sid in g.segment_ids) == [1, 2, 3, 4]


def test_ids_are_deterministic_and_every_segment_is_in_exactly_one_group():
    segs = [seg(i, (i, 0), (i + 1, 0), length=120.0) for i in range(1, 30)]
    a, b = build_groups(segs), build_groups(list(reversed(segs)))
    assert [(g.id, g.segment_ids) for g in a] == [(g.id, g.segment_ids) for g in b] or \
        [g.length_m for g in a] == [g.length_m for g in b]
    members = [sid for g in a for sid in g.segment_ids]
    assert sorted(members) == [s.id for s in segs]


# --- effective scores -------------------------------------------------------------------------

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
