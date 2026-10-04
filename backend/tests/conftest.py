"""Tests never touch the network or the developer's .env: the rate limiter is the in-memory one (no Redis) and
every test installs its own fake graph or repository."""

import pytest

from app.main import app
from app.rate_limit import RateLimiter


@pytest.fixture(autouse=True)
def offline_routing():
    previous_limiter = app.state.rate_limiter
    app.state.rate_limiter = RateLimiter()
    yield
    app.dependency_overrides.clear()
    app.state.rate_limiter = previous_limiter
