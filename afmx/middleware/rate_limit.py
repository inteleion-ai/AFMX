"""
AFMX Rate Limiting Middleware — token-bucket per IP.

Fix: asyncio.Lock() is now created lazily on first use, not in __init__.
     Creating asyncio primitives outside a running event loop raises on Python 3.12+.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/"}


class TokenBucket:
    """
    Simple token bucket rate limiter.
    Refills at `rate` tokens/second up to `capacity` maximum.
    """

    def __init__(self, capacity: float, rate: float):
        self.capacity = capacity
        self.rate = rate
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP token-bucket rate limiter.

    Fix: asyncio.Lock is created lazily on first dispatch() call
         instead of in __init__ to avoid Python 3.12 event loop errors.

    Config:
        requests_per_minute — sustained throughput limit
        burst               — maximum burst above sustained rate
    """

    def __init__(self, app, requests_per_minute: int = 60, burst: int = 20):
        super().__init__(app)
        self._rpm = requests_per_minute
        self._burst = burst
        self._rate = requests_per_minute / 60.0
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock: Optional[asyncio.Lock] = None  # lazy
        self._cleanup_interval = 300
        self._last_cleanup = time.monotonic()

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        lock = self._get_lock()

        async with lock:
            if client_ip not in self._buckets:
                self._buckets[client_ip] = TokenBucket(
                    capacity=self._burst, rate=self._rate,
                )
            bucket = self._buckets[client_ip]
            allowed = bucket.consume()

            if time.monotonic() - self._last_cleanup > self._cleanup_interval:
                self._cleanup_stale()

        if not allowed:
            logger.warning(f"[RateLimit] Rate limit exceeded for {client_ip}")
            return Response(
                content='{"error":"RATE_LIMITED","message":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self._rpm),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._rpm)
        return response

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _cleanup_stale(self) -> None:
        stale = [ip for ip, b in self._buckets.items() if b._tokens >= b.capacity * 0.99]
        for ip in stale:
            del self._buckets[ip]
        self._last_cleanup = time.monotonic()
        if stale:
            logger.debug(f"[RateLimit] Cleaned up {len(stale)} stale buckets")
