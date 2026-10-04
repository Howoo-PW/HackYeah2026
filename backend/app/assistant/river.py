"""Waypoints along the river for "wzdłuż Wisły": chosen from the embankment paths in the database, not from the model's memory.

The model only says the route should follow the river; the points come from the OSM ways named "Bulwar ..." (public.osm_ways).
A point is a candidate when going through it hardly lengthens the trip from start to end, and the picks are spread along
the way, so the route follows the bank where start and end are on the same stretch and is left alone where they are not.
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

MAX_VIA = 3
MIN_DETOUR_M = 300  # always allowed
DETOUR_SHARE = 0.4  # ... or this share of the straight distance start -> end, whichever is larger
SNAP_M = 150  # a waypoint farther from a road of the profile would only cause a detour


@dataclass(frozen=True)
class BankPoint:
    name: str
    lat: float
    lon: float


def _xy(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """Metres east / north of the origin (flat approximation, good enough for a city)."""
    return math.radians(lon) * 6371000 * math.cos(math.radians(lat0)), math.radians(lat) * 6371000


def candidates(start: tuple[float, float], end: tuple[float, float], points: list[BankPoint]) -> list[tuple[float, float, BankPoint]]:
    """Bank points worth passing between `start` and `end` (lat, lon): (position along the way 0..1, detour in metres, point), best detour first."""
    lat0 = (start[0] + end[0]) / 2
    ax, ay = _xy(*start, lat0)
    bx, by = _xy(*end, lat0)
    ab = math.hypot(bx - ax, by - ay)
    if ab < 1:
        return []
    allowed = max(MIN_DETOUR_M, DETOUR_SHARE * ab)
    found = []
    for p in points:
        px, py = _xy(p.lat, p.lon, lat0)
        detour = math.hypot(px - ax, py - ay) + math.hypot(bx - px, by - py) - ab
        t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (ab * ab)
        if detour <= allowed and 0.05 < t < 0.95:
            found.append((t, detour, p))
    return sorted(found, key=lambda c: c[1])


async def pick_river_vias(
    start: tuple[float, float], end: tuple[float, float], points: list[BankPoint],
    snap_distance: Callable[[float, float], Awaitable[float | None]] | None,
) -> list[BankPoint]:
    """Up to MAX_VIA bank points along start -> end in driving order: the least detour in each third of the way, reachable by the profile."""
    ranked = candidates(start, end, points)
    chosen: list[tuple[float, BankPoint]] = []
    for third in range(MAX_VIA):
        for t, _detour, p in (c for c in ranked if third / MAX_VIA <= c[0] < (third + 1) / MAX_VIA):
            if snap_distance is not None:
                away = await snap_distance(p.lat, p.lon)
                if away is None or away > SNAP_M:
                    continue
            chosen.append((t, p))
            break
    return [p for _t, p in sorted(chosen, key=lambda c: c[0])]
