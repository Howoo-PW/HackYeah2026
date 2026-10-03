"""Per-user sliding-window limits for the single-process hackathon backend."""

from collections import deque
from threading import Lock
from time import monotonic

from .errors import AppError


class RateLimiter:
    """Thread-safe hourly limits; use shared storage before deploying multiple workers."""

    def __init__(self):
        self._events: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def check(self, user_id: str, action: str, limit: int) -> None:
        """Consume one attempt or raise the contract RATE_LIMITED error."""
        now = monotonic()
        with self._lock:
            # Remove expired users so the dictionary does not grow forever.
            for key in list(self._events):
                events = self._events[key]
                while events and events[0] <= now - 3600:
                    events.popleft()
                if not events:
                    del self._events[key]
            events = self._events.setdefault((user_id, action), deque())
            if len(events) >= limit:
                raise AppError(429, "RATE_LIMITED", "Przekroczono godzinowy limit żądań")
            events.append(now)
