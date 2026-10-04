"""Waypoints along the river: only bank points that hardly lengthen the trip, spread along the way, in driving order."""

import asyncio

from app.assistant_river import BankPoint, candidates, pick_river_vias

START, END = (50.0614, 19.9357), (50.0446, 19.9700)  # about 3 km apart, going south-east
ON_WAY = [BankPoint("A", 50.0580, 19.9420), BankPoint("B", 50.0530, 19.9530), BankPoint("C", 50.0480, 19.9630)]
FAR = BankPoint("Far", 50.0300, 19.9000)  # the other way: a big detour
BEHIND = BankPoint("Behind", 50.0700, 19.9300)  # before the start


def test_candidates_drop_points_that_make_a_detour_or_lie_outside_the_way():
    names = {c[2].name for c in candidates(START, END, [*ON_WAY, FAR, BEHIND])}
    assert names == {"A", "B", "C"}


def test_picks_are_in_driving_order_one_per_third():
    vias = asyncio.run(pick_river_vias(END, START, ON_WAY, None))  # reversed trip: order follows the new direction
    assert [v.name for v in vias] == ["C", "B", "A"]


def test_points_far_from_a_road_of_the_profile_are_skipped():
    async def snap(lat, lon):
        return 400.0 if lat > 50.056 else 20.0

    assert [v.name for v in asyncio.run(pick_river_vias(START, END, ON_WAY, snap))] == ["B", "C"]


def test_no_bank_nearby_means_no_waypoints():
    assert asyncio.run(pick_river_vias(START, END, [FAR, BEHIND], None)) == []
