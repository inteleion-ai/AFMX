"""
AFMX Middleware — API Key Auth (optional)
"""
from __future__ import annotations
import logging

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_keys: list, header_name: str = "X-AFMX-API-Key"):
        super().__init__(app)
        self._keys = set(api_keys)
        self._header = header_name

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        key = request.headers.get(self._header)
        if not key or key not in self._keys:
            return Response(
                content='{"error":"UNAUTHORIZED","message":"Invalid or missing API key"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
            )

        return await call_next(request)
