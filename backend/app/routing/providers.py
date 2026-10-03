"""Route sources: OpenRouteService (real) and a deterministic mock for work without an API key."""

from dataclasses import dataclass
from typing import Protocol

import httpx
from shapely.geometry import LineString

from ..config import settings
from ..errors import AppError
from .geo import to_meters
from .schemas import Point, Profile


@dataclass
class RawRoute:
    coordinates: list[list[float]]  # [lon, lat]
    distance_m: float
    duration_s: float


class RouteProvider(Protocol):
    async def routes(self, start: Point, end: Point, profile: Profile) -> list[RawRoute]: ...


class OrsProvider:
    """OpenRouteService directions. Asks for up to 3 alternatives (ORS allows them for routes < 100 km)."""

    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None):
        self._api_key, self._base_url, self._client = api_key, base_url.rstrip("/"), client

    async def routes(self, start: Point, end: Point, profile: Profile) -> list[RawRoute]:
        body = {
            "coordinates": [[start.lon, start.lat], [end.lon, end.lat]],
            "alternative_routes": {"target_count": 3, "share_factor": 0.6, "weight_factor": 1.6},
        }
        headers = {"Authorization": self._api_key, "User-Agent": settings.user_agent}
        url = f"{self._base_url}/v2/directions/{profile}/geojson"
        try:
            if self._client:
                res = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    res = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise AppError(502, "UPSTREAM_ERROR", "Routing service unreachable", {"reason": type(exc).__name__}) from exc

        if res.status_code == 429:
            raise AppError(429, "RATE_LIMITED", "Routing provider quota exceeded")
        if res.status_code != 200:
            raise AppError(502, "UPSTREAM_ERROR", "Routing service error", {"status": res.status_code})
        return self._parse(res.json())

    @staticmethod
    def _parse(data: dict) -> list[RawRoute]:
        try:
            return [
                RawRoute(
                    coordinates=f["geometry"]["coordinates"],
                    distance_m=f["properties"]["summary"]["distance"],
                    duration_s=f["properties"]["summary"]["duration"],
                )
                for f in data["features"]
            ]
        except (KeyError, TypeError) as exc:
            raise AppError(502, "UPSTREAM_ERROR", "Unexpected routing response format") from exc


_SPEED_MS = {"driving-car": 8.3, "cycling-regular": 4.2, "foot-walking": 1.4}  # city averages


class MockProvider:
    """Direct line plus a detour east and west of the midpoint (+/-0.003 deg lon). Matches data/sample_segments.geojson."""

    async def routes(self, start: Point, end: Point, profile: Profile) -> list[RawRoute]:
        mid_lon, mid_lat = (start.lon + end.lon) / 2, (start.lat + end.lat) / 2
        routes = []
        for offset in (0.0, 0.003, -0.003):
            coords = [[start.lon, start.lat], [mid_lon + offset, mid_lat], [end.lon, end.lat]]
            length = to_meters(LineString(coords)).length
            routes.append(RawRoute(coords, round(length, 1), round(length / _SPEED_MS[profile], 1)))
        return routes


def build_provider() -> RouteProvider:
    """Choose an explicitly configured provider without silently mocking ORS errors."""
    if settings.routing_provider == "ors":
        key = settings.ors_api_key.get_secret_value()
        if not key:
            raise AppError(502, "UPSTREAM_ERROR", "ORS_API_KEY is not configured")
        return OrsProvider(key, settings.ors_base_url)
    if settings.routing_provider != "mock":
        raise AppError(502, "UPSTREAM_ERROR", "Unsupported routing provider")
    return MockProvider()
