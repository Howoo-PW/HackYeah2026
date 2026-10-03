"""Small geo helpers: Kraków bbox check and a local metric projection (no pyproj needed at city scale)."""

import math

from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

# Kraków bbox, docs/CONTRACT.md section 2: minLon, minLat, maxLon, maxLat
KRAKOW_BBOX = (19.792, 49.967, 20.217, 50.126)

_LAT0, _LON0 = 50.06, 19.94
_M_PER_DEG_LAT = 111_132.0
_M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(_LAT0))


def in_krakow(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = KRAKOW_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def to_meters(geom: BaseGeometry) -> BaseGeometry:
    """(lon, lat) degrees -> local x/y in metres. Distances are accurate to well under 1% inside Kraków."""
    return transform(lambda x, y, z=None: ((x - _LON0) * _M_PER_DEG_LON, (y - _LAT0) * _M_PER_DEG_LAT), geom)
