"""Service-area check for routes. The area itself is defined once, in app/geo.py."""

from ..geo import KRAKOW as KRAKOW_BBOX  # minLon, minLat, maxLon, maxLat (docs/CONTRACT.md, section 2)


def in_krakow(lat: float, lon: float) -> bool:
    """True when the point lies inside the service area."""
    min_lon, min_lat, max_lon, max_lat = KRAKOW_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
