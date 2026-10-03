"""Tests never touch the network or the developer's .env: routing always uses the mock provider and sample data,
and the rate limiter is the in-memory one (no Redis)."""

import pytest

from app.main import app
from app.rate_limit import RateLimiter
from app.routing.providers import MockProvider
from app.routing.router import get_provider, get_segment_source
from app.routing.segments import InMemorySegmentSource


@pytest.fixture(autouse=True)
def offline_routing():
    app.dependency_overrides[get_provider] = lambda: MockProvider()
    app.dependency_overrides[get_segment_source] = lambda: InMemorySegmentSource.from_file()
    previous_limiter = app.state.rate_limiter
    app.state.rate_limiter = RateLimiter()
    yield
    app.dependency_overrides.clear()
    app.state.rate_limiter = previous_limiter
