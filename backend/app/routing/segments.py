"""Source of rated road segments. The in-memory version reads a sample GeoJSON; B2 replaces it with PostGIS."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shapely.geometry import LineString, shape

from .geo import to_meters
from .schemas import DIMENSIONS

SAMPLE_FILE = Path(__file__).parent / "data" / "sample_segments.geojson"


@dataclass
class SegmentMatch:
    id: int
    overlap_m: float  # length of the segment lying within the buffer around the route
    scores: dict[str, float | None]  # per dimension, 1-5 averages (None = no ratings)


class SegmentSource(Protocol):
    def matches(self, route: LineString, buffer_m: float, min_share: float) -> list[SegmentMatch]:
        """Segments lying on `route` (lon/lat coordinates), with the length within `buffer_m` metres of it.

        Segments that only touch the route or run alongside it for a while (junctions, crossings, routes diverging
        at a shallow angle) are dropped: at least `min_share` (0-1) of the segment's own length must lie in the buffer.
        A PostGIS implementation does the same with ST_DWithin / ST_Intersection on `segments` and `segment_stats`.
        """
        ...


class InMemorySegmentSource:
    def __init__(self, features: list[dict]):
        self._segments = [
            (
                f["properties"]["id"],
                to_meters(shape(f["geometry"])),
                {d: f["properties"].get(d) for d in DIMENSIONS},
            )
            for f in features
        ]

    @classmethod
    def from_file(cls, path: Path = SAMPLE_FILE) -> "InMemorySegmentSource":
        return cls(json.loads(path.read_text(encoding="utf-8"))["features"])

    def matches(self, route: LineString, buffer_m: float, min_share: float) -> list[SegmentMatch]:
        zone = to_meters(route).buffer(buffer_m)
        hits = []
        for seg_id, geom, scores in self._segments:
            overlap = zone.intersection(geom).length
            if overlap > 0 and overlap >= min_share * geom.length:
                hits.append(SegmentMatch(seg_id, overlap, scores))
        return hits
