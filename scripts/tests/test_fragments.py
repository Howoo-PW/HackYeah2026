"""Rating fragments of 300-700 m: cut at important junctions, short pieces merged into a neighbour."""

from collections import defaultdict

from fragments import SegmentRow, build_fragments


def seg(i, a, b, length=200.0, name="Długa", highway="residential", way=None):
    return SegmentRow(i, way or i, name, highway, length, a, b)


def touching(segs):
    """Segments sharing an end node touch (the loader also adds T-junctions found in geometry)."""
    at = defaultdict(set)
    for s in segs:
        at[s.start].add(s.id)
        at[s.end].add(s.id)
    out = defaultdict(set)
    for ids in at.values():
        for i in ids:
            out[i] |= ids - {i}
    return out


def important(segs):
    """Node -> ids of important-road segments that have an end there."""
    out = defaultdict(set)
    for s in segs:
        if s.highway in ("primary", "secondary", "tertiary"):
            out[s.start].add(s.id)
            out[s.end].add(s.id)
    return out


def fragments(segs, **kw):
    return build_fragments(segs, touching(segs), important(segs), **kw)


def lengths(groups):
    return sorted(round(g.length_m) for g in groups)


def test_street_is_cut_at_an_important_junction_once_it_is_long_enough():
    # 6 x 200 m = 1200 m; Basztowa (primary) meets after the third segment (node 4) -> 600 + 600
    street = [seg(i, (i, 0), (i + 1, 0)) for i in range(1, 7)]
    main_road = seg(100, (4, 0), (4, 1), length=400.0, name="Basztowa", highway="primary")
    groups = fragments(street + [main_road])
    streets = [g for g in groups if g.name == "Długa"]
    assert lengths(streets) == [600, 600]
    assert sorted(s for g in streets for s in g.segment_ids) == [1, 2, 3, 4, 5, 6]
    assert [sorted(g.segment_ids) for g in streets] in ([[1, 2, 3], [4, 5, 6]], [[4, 5, 6], [1, 2, 3]])


def test_minor_side_streets_never_cut():
    street = [seg(i, (i, 0), (i + 1, 0)) for i in range(1, 4)]                  # 600 m
    side = [seg(100 + i, (i, 0), (i, 1), length=300.0, name=f"Boczna {i}") for i in (1, 2)]   # residential crossings
    groups = fragments(street + side)
    assert [g.length_m for g in groups if g.name == "Długa"] == [600.0]


def test_a_junction_with_an_important_road_before_the_minimum_does_not_cut():
    street = [seg(i, (i, 0), (i + 1, 0)) for i in range(1, 5)]                  # 800 m
    cross = seg(100, (2, 0), (2, 1), length=400.0, name="Basztowa", highway="primary")   # after only 200 m
    groups = fragments(street + [cross])
    long_ones = [g for g in groups if g.name == "Długa"]
    assert all(g.length_m >= 300 for g in long_ones)


def test_long_street_without_important_junctions_is_cut_at_the_maximum_and_the_tail_merged_back():
    street = [seg(i, (i, 0), (i + 1, 0)) for i in range(1, 11)]                 # 2000 m
    groups = fragments(street)
    assert all(300 <= g.length_m <= 900 for g in groups)
    assert sum(g.length_m for g in groups) == 2000.0
    assert max(g.length_m for g in groups) <= 900


def test_a_short_street_is_merged_into_its_neighbour():
    long_street = [seg(i, (i, 0), (i + 1, 0), name="Długa") for i in range(1, 4)]       # 600 m
    stub = seg(50, (4, 0), (4, 1), length=100.0, name="Krótka")                          # attached at the end
    groups = fragments(long_street + [stub])
    assert len(groups) == 1
    assert groups[0].length_m == 700.0 and groups[0].name == "Długa"
    assert groups[0].from_street is None and groups[0].to_street is None  # merged: no single start/end


def test_prefers_a_neighbour_of_the_same_road_type():
    stub = seg(1, (0, 0), (0, 1), length=100.0, name="Krótka", highway="residential")
    same = seg(2, (0, 0), (1, 0), length=300.0, name="A", highway="residential")
    other = seg(3, (0, 0), (-1, 0), length=300.0, name="B", highway="service")
    groups = fragments([stub, same, other])
    merged = next(g for g in groups if 1 in g.segment_ids)
    assert 2 in merged.segment_ids and 3 not in merged.segment_ids


def test_merge_never_exceeds_the_cap():
    stub = seg(1, (0, 0), (0, 1), length=200.0, name="Krótka")
    big = [seg(10 + i, (i, 0), (i + 1, 0), length=300.0, name="Duża") for i in range(3)]  # 900 m
    groups = fragments([stub] + big, merge_max_m=700.0)
    stub_group = next(g for g in groups if 1 in g.segment_ids)
    assert stub_group.length_m == 200.0  # 200 + 600 > 700: stays alone


def test_isolated_short_road_stays_short():
    groups = fragments([seg(1, (0, 0), (1, 0), length=80.0)])
    assert lengths(groups) == [80]


def test_every_segment_is_in_exactly_one_fragment_and_ids_are_deterministic():
    segs = [seg(i, (i, 0), (i + 1, 0), length=90.0 + i) for i in range(1, 40)]
    segs += [seg(100 + i, (i * 3, 0), (i * 3, 1), length=60.0, name=f"S{i}") for i in range(1, 12)]
    a, b = fragments(segs), fragments(list(reversed(segs)))
    assert sorted(s for g in a for s in g.segment_ids) == sorted(s.id for s in segs)
    assert [(g.id, g.segment_ids) for g in a] == [(g.id, g.segment_ids) for g in b]


def test_t_junction_neighbours_given_by_the_loader_are_used_for_merging():
    # The side street ends in the middle of the long street (no shared segment end), so only the
    # explicit neighbour map connects them.
    long_street = [seg(1, (0, 0), (1, 0), length=500.0, name="Długa")]
    side = seg(2, (9, 9), (9, 8), length=100.0, name="Boczna")
    segs = long_street + [side]
    groups = build_fragments(segs, {1: {2}, 2: {1}}, {})
    assert len(groups) == 1 and groups[0].length_m == 600.0


def test_the_tail_of_a_street_goes_back_to_its_own_street_before_a_foreign_stub_takes_the_room():
    street = [seg(i, (i, 0), (i + 1, 0)) for i in range(1, 5)]                  # 800 m, cut at 700 -> 600 + 200 tail
    stub = seg(100, (1, 0), (1, 1), length=200.0, name="Obca", highway="primary")
    groups = fragments(street + [stub])
    dluga = [g for g in groups if g.name == "Długa"]
    assert [g.length_m for g in dluga] == [800.0]  # tail merged into its own street
    assert next(g for g in groups if 100 in g.segment_ids).length_m == 200.0  # the stub no longer fits


# --- chains of one street (no cutting, no merging) ----------------------------------------------

def chains(segs):
    """Fragments of build_fragments with cutting and merging switched off: the plain chains of one street."""
    return build_fragments(segs, touching(segs), {}, min_m=0.0, max_m=1e9)


def by_member(groups):
    return {sid: g for g in groups for sid in g.segment_ids}


def test_consecutive_pieces_of_one_street_merge():
    groups = chains([seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0)), seg(3, (2, 0), (3, 0))])
    assert len(groups) == 1
    assert groups[0].segment_ids == [1, 2, 3] and groups[0].length_m == 600.0


def test_a_crossing_street_does_not_break_the_chain_but_names_the_ends():
    # Długa runs through a junction with Basztowa (a T from the north) and ends at Pędzichów.
    segs = [
        seg(1, (0, 0), (1, 0)),
        seg(2, (1, 0), (2, 0)),
        seg(3, (1, 0), (1, 1), name="Basztowa", highway="primary"),
        seg(4, (2, 0), (3, 0), name="Pędzichów"),
    ]
    g = by_member(chains(segs))
    assert g[1] is g[2]
    assert g[1].segment_ids == [1, 2]            # Pędzichów is another street
    assert g[1].to_street == "Pędzichów" and g[1].from_street is None
    assert g[3] is not g[1]


def test_street_forking_into_two_same_name_branches_is_not_merged_across():
    segs = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0)), seg(3, (1, 0), (2, 1))]
    g = by_member(chains(segs))
    assert len({id(g[1]), id(g[2]), id(g[3])}) == 3


def test_different_road_type_or_name_never_merges():
    segs = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (2, 0), highway="tertiary"), seg(3, (2, 0), (3, 0), name="Inna")]
    assert len(chains(segs)) == 3


def test_unnamed_segments_merge_only_within_one_osm_way():
    segs = [seg(1, (0, 0), (1, 0), name=None, way=7), seg(2, (1, 0), (2, 0), name=None, way=7),
            seg(3, (2, 0), (3, 0), name=None, highway="cycleway", way=8)]
    g = by_member(chains(segs))
    assert g[1] is g[2] and g[3] is not g[1]


def test_unnamed_pieces_merge_across_ways_only_at_a_plain_continuation():
    chain = [seg(1, (0, 0), (1, 0), name=None, highway="cycleway", way=7),
             seg(2, (1, 0), (2, 0), name=None, highway="cycleway", way=8)]
    assert len(chains(chain)) == 1
    with_branch = chain + [seg(3, (1, 0), (1, 1), name=None, highway="cycleway", way=9)]
    assert len(chains(with_branch)) == 3
    other_type = [chain[0], seg(2, (1, 0), (2, 0), name=None, highway="residential", way=8)]
    assert len(chains(other_type)) == 2


def test_closed_ring_does_not_loop_forever_and_keeps_every_segment():
    ring = [seg(1, (0, 0), (1, 0)), seg(2, (1, 0), (1, 1)), seg(3, (1, 1), (0, 1)), seg(4, (0, 1), (0, 0))]
    groups = chains(ring)
    assert sorted(sid for g in groups for sid in g.segment_ids) == [1, 2, 3, 4]


def test_every_segment_is_in_exactly_one_fragment_and_ids_do_not_depend_on_input_order():
    segs = [seg(i, (i, 0), (i + 1, 0), length=120.0) for i in range(1, 30)]
    a, b = fragments(segs), fragments(list(reversed(segs)))
    assert [(g.id, sorted(g.segment_ids)) for g in a] == [(g.id, sorted(g.segment_ids)) for g in b]
    assert sorted(sid for g in a for sid in g.segment_ids) == [s.id for s in segs]
