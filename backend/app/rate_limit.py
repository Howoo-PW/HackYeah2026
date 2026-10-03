"""Atomic shared Redis limits, plus an in-memory implementation for unit tests."""

from collections import deque
from threading import Lock
from time import monotonic
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from .errors import AppError


class RateLimiter:
    """Thread-safe hourly limiter used only by isolated unit tests."""

    def __init__(self):
        self._events: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def check(self, user_id: str, action: str, limit: int, window: int = 3600) -> None:
        """Consume one attempt or raise the contract RATE_LIMITED error."""
        now = monotonic()
        with self._lock:
            # Remove expired users so the dictionary does not grow forever.
            for key in list(self._events):
                events = self._events[key]
                while events and events[0] <= now - window:
                    events.popleft()
                if not events:
                    del self._events[key]
            events = self._events.setdefault((user_id, action), deque())
            if len(events) >= limit:
                raise AppError(429, "RATE_LIMITED", "Przekroczono godzinowy limit żądań")
            events.append(now)


LUA = """
local timestamp = redis.call('TIME')
local now = tonumber(timestamp[1]) + tonumber(timestamp[2]) / 1000000
local window = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    return 0
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('EXPIRE', KEYS[1], window)
return 1
"""


class RedisRateLimiter:
    """Share a sliding-window limit across backend processes with atomic Lua."""

    def __init__(self, url: str, namespace: str = "rate-your-ride"):
        self.client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        self.namespace = namespace
        self.script = self.client.register_script(LUA)

    def check(self, user_id: str, action: str, limit: int, window: int = 3600) -> None:
        """Consume one attempt using server time, or fail closed on Redis outages."""
        key = f"{self.namespace}:{action}:{user_id}"
        try:
            accepted = self.script(keys=[key], args=[limit, window, uuid4().hex])
        except RedisError:
            raise AppError(500, "INTERNAL_ERROR", "Usługa limitów jest niedostępna") from None
        if not accepted:
            raise AppError(429, "RATE_LIMITED", "Przekroczono limit żądań")

    def close(self) -> None:
        """Release Redis connections when the backend shuts down."""
        self.client.close()
