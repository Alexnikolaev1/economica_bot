"""
utils/rate_limiter.py — ограничитель запросов к Gemini API.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

USER_RPM = 5
GLOBAL_RPM = 14
WINDOW = 60.0


class RateLimiter:
    def __init__(self) -> None:
        self._user_timestamps: dict[int, deque] = defaultdict(deque)
        self._global_timestamps: deque = deque()
        self._lock = asyncio.Lock()

    def _purge_old(self, dq: deque, now: float) -> None:
        while dq and now - dq[0] > WINDOW:
            dq.popleft()

    async def acquire(self, user_id: int) -> bool:
        async with self._lock:
            now = time.monotonic()
            self._purge_old(self._global_timestamps, now)
            self._purge_old(self._user_timestamps[user_id], now)

            if len(self._user_timestamps[user_id]) >= USER_RPM:
                logger.warning("Rate limit (user %s)", user_id)
                return False
            if len(self._global_timestamps) >= GLOBAL_RPM:
                logger.warning("Rate limit (global)")
                return False

            self._user_timestamps[user_id].append(now)
            self._global_timestamps.append(now)
            return True


rate_limiter = RateLimiter()
