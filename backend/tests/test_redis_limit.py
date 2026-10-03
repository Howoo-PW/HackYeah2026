"""Optional real-Redis regressions for shared limits and concurrent workers."""

from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import pytest

from app.errors import AppError
from app.rate_limit import RedisRateLimiter


@pytest.fixture
def limiters():
    url = os.environ.get("REDIS_TEST_URL")
    if not url:
        pytest.skip("Set REDIS_TEST_URL to run real Redis concurrency checks")
    namespace = "b1-test-" + uuid4().hex
    first, second = RedisRateLimiter(url, namespace), RedisRateLimiter(url, namespace)
    first.client.ping()
    try:
        yield first, second
    finally:
        keys = list(first.client.scan_iter(match=namespace + ":*"))
        if keys:
            first.client.delete(*keys)
        first.close()
        second.close()


def test_concurrent_workers_share_one_quota(limiters):
    def attempt(number):
        try:
            limiters[number % 2].check("same-user", "ratings", 10)
            return True
        except AppError as error:
            assert error.code == "RATE_LIMITED"
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(attempt, range(40)))
    assert sum(outcomes) == 10


def test_window_cleanup_and_client_restart(limiters):
    first, second = limiters
    key = first.namespace + ":comments:user"
    seconds, micros = first.client.time()
    first.client.zadd(key, {"expired": seconds + micros / 1000000 - 3601})
    first.check("user", "comments", 1)
    assert 0 < first.client.ttl(key) <= 3600
    with pytest.raises(AppError) as error:
        second.check("user", "comments", 1)
    assert error.value.status == 429
    second.check("another-user", "comments", 1)
    second.check("user", "ratings", 1)


def test_unavailable_redis_fails_closed():
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0")
    try:
        with pytest.raises(AppError) as error:
            limiter.check("user", "ratings", 30)
        assert error.value.code == "INTERNAL_ERROR"
    finally:
        limiter.close()
