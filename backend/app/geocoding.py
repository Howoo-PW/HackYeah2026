"""Place names to coordinates for the assistant: OpenStreetMap Nominatim, called from the backend with a cache.

docs/MAP_STACK.md asks for exactly this (an explicit search, not autocomplete; at most 1 request per second; own User-Agent;
cached answers). Results are limited to the Krakow area, and the same name is looked up only once a day.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from .errors import AppError
from .geo import KRAKOW

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RateMyRoad/0.1 (hackathon project; OSM Nominatim client)"
MIN_INTERVAL_S = 1.1  # Nominatim usage policy: at most one request per second
HIT_TTL_S = 24 * 3600
MISS_TTL_S = 3600
TIMEOUT_S = 8


@dataclass(frozen=True)
class Found:
    """A place: display name, point, and (for areas and streets) the extent as west, south, east, north."""

    name: str
    lat: float
    lon: float
    bbox: tuple[float, float, float, float] | None = None
    outline: dict | None = None  # GeoJSON Polygon/MultiPolygon of a district or other area (only when asked for)


class Geocoder(Protocol):
    async def find(self, text: str, area: bool = False) -> Found | None:
        """The best match for `text` inside Krakow, or None. With `area`, a district's real outline comes along when it has one."""


def _key(text: str) -> str:
    return " ".join(text.lower().split())


class NominatimGeocoder:
    """Nominatim with an in-memory cache and a one-request-per-second gate shared by everything in the process."""

    def __init__(self, url: str = NOMINATIM_URL, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url
        self.transport = transport
        self._cache: dict[str, tuple[float, Found | None]] = {}
        self._gate = asyncio.Lock()
        self._last_call = 0.0

    async def find(self, text: str, area: bool = False) -> Found | None:
        key = _key(text) + ("|area" if area else "")
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        west, south, east, north = KRAKOW
        params = {
            "q": text, "format": "jsonv2", "limit": "1", "countrycodes": "pl", "accept-language": "pl",
            "viewbox": f"{west},{north},{east},{south}", "bounded": "1",
            **({"polygon_geojson": "1"} if area else {}),
        }
        async with self._gate:
            wait = self._last_call + MIN_INTERVAL_S - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self.transport, headers={"User-Agent": USER_AGENT}) as client:
                    response = await client.get(self.url, params=params)
                    response.raise_for_status()
                    results = response.json()
            except (httpx.HTTPError, ValueError):
                raise AppError(502, "UPSTREAM_ERROR", "Wyszukiwarka miejsc jest chwilowo niedostępna") from None
            finally:
                self._last_call = time.monotonic()

        found = None
        if results:
            top = results[0]
            box = top.get("boundingbox")  # [south, north, west, east] as strings
            found = Found(
                name=top.get("name") or top.get("display_name", text).split(",")[0],
                lat=float(top["lat"]), lon=float(top["lon"]),
                bbox=(float(box[2]), float(box[0]), float(box[3]), float(box[1])) if box else None,
                outline=top["geojson"] if area and (top.get("geojson") or {}).get("type") in ("Polygon", "MultiPolygon") else None,
            )
        self._cache[key] = (time.monotonic() + (HIT_TTL_S if found else MISS_TTL_S), found)
        return found


_default = NominatimGeocoder()


def get_geocoder() -> Geocoder:
    """The shared geocoder (one gate and one cache per process)."""
    return _default
