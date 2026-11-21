"""Abuse protection for the public API (deployment D1.8).

- Request bodies larger than MAX_REQUEST_BYTES are rejected with 413 (a chat query is < 1 KB).
- POST /api/chat is rate limited per client IP to RATE_LIMIT_PER_MINUTE (sliding 60 s window);
  every chat call spends LLM quota. 0 disables the limit (the default, so local use and tests are
  unaffected); production sets it, e.g. 20.

Behind Railway's proxy the client IP is the first hop of X-Forwarded-For.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

RATE_LIMITED_PATHS = {("POST", "/api/chat")}
WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, now: float = None) -> float:
        """Returns 0 if allowed, else the seconds until the next request would be allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return max(1.0, WINDOW_SECONDS - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > MAX_TRACKED_CLIENTS:  # drop idle clients so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= WINDOW_SECONDS]:
                    del self._hits[k]
            return 0.0


limiter = SlidingWindowLimiter()


class RequestLimitsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request too large."})

        limit = settings.rate_limit_per_minute
        if limit > 0 and (request.method, request.url.path) in RATE_LIMITED_PATHS:
            retry_after = limiter.allow(client_ip(request), limit)
            if retry_after:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many questions in a short time. Please wait a minute and try again."},
                    headers={"Retry-After": str(int(retry_after))},
                )
        return await call_next(request)
