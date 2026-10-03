"""Validation of the agreed Krakow bounding box, with GeoJSON longitude first."""

import math

from .errors import AppError

KRAKOW = (19.792, 49.967, 20.217, 50.126)


def validate_point(lat: float, lon: float) -> None:
    """Reject non-finite coordinates and locations outside Krakow."""
    west, south, east, north = KRAKOW
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise AppError(422, "VALIDATION_ERROR", "Nieprawidłowe współrzędne")
    if not (west <= lon <= east and south <= lat <= north):
        raise AppError(422, "OUT_OF_AREA", "Współrzędne poza Krakowem")


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """Parse minLon,minLat,maxLon,maxLat and require a positive, in-area box."""
    try:
        west, south, east, north = map(float, value.split(","))
    except ValueError:
        raise AppError(422, "VALIDATION_ERROR", "bbox: minLon,minLat,maxLon,maxLat") from None
    validate_point(south, west)
    validate_point(north, east)
    if west >= east or south >= north:
        raise AppError(422, "VALIDATION_ERROR", "Nieprawidłowa kolejność bbox")
    return west, south, east, north


def clamp_bbox(value: str) -> tuple[float, float, float, float] | None:
    """Like parse_bbox, but a viewport reaching past the area is cut to it (zoomed-out maps do).

    Returns None when the viewport does not touch the area at all.
    """
    try:
        west, south, east, north = map(float, value.split(","))
    except ValueError:
        raise AppError(422, "VALIDATION_ERROR", "bbox: minLon,minLat,maxLon,maxLat") from None
    if not all(map(math.isfinite, (west, south, east, north))):
        raise AppError(422, "VALIDATION_ERROR", "Nieprawidłowe współrzędne")
    if west >= east or south >= north:
        raise AppError(422, "VALIDATION_ERROR", "Nieprawidłowa kolejność bbox")
    a_west, a_south, a_east, a_north = KRAKOW
    west, south, east, north = max(west, a_west), max(south, a_south), min(east, a_east), min(north, a_north)
    return None if west >= east or south >= north else (west, south, east, north)
