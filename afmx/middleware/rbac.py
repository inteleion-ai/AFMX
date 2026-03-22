"""
AFMX RBAC Middleware

Replaces the simple APIKeyMiddleware when RBAC is enabled (AFMX_RBAC_ENABLED=true).

Request flow:
  1. Extract API key from X-AFMX-API-Key header (configurable)
  2. If RBAC is disabled → inject system principal, pass through
  3. If path is public (health, docs, UI) → pass through
  4. Determine required permission for this endpoint
  5. If endpoint is public (no permission needed) → pass through
  6. If no key provided → 401 Unauthorized     (audit: auth.failure)
  7. Look up key in API key store (lazy — resolved at dispatch time)
  8. If key not found or invalid → 401           (audit: auth.failure / auth.expired)
  9. If key lacks the permission → 403 Forbidden (audit: auth.denied)
 10. Inject Principal into request.state.principal
 11. Schedule last_used_at update as a background task (non-blocking)
 12. Pass request to the next handler

IMPORTANT: Stores are resolved lazily via afmx_app at dispatch time, NOT at
construction time. create_app() runs before startup(), so stores are None
during __init__. Never capture them in the constructor.

The principal is always available to route handlers via:
    principal = request.state.principal
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from afmx.auth.rbac import Principal, get_required_permission, PUBLIC_PATHS
from afmx.audit.model import AuditEvent, AuditAction

logger = logging.getLogger(__name__)


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Full RBAC enforcement middleware.

    Parameters
    ----------
    app           ASGI application
    header_name   Header carrying the API key (default: X-AFMX-API-Key)
    enabled       When False, injects a system ADMIN principal and skips checks

    Stores are intentionally NOT passed as constructor arguments.
    They are looked up from afmx_app at dispatch time so that the middleware
    works correctly even though create_app() runs before startup().
    """

    def __init__(
        self,
        app,
        *,
        header_name: str = "X-AFMX-API-Key",
        enabled: bool = True,
    ):
        super().__init__(app)
        self._header = header_name
        self._enabled = enabled

    def _get_stores(self):
        """Lazy store resolution — safe to call from any async context."""
        from afmx.main import afmx_app
        return afmx_app.api_key_store, afmx_app.audit_store

    async def dispatch(self, request: Request, call_next) -> Response:
        # Guarantee request.state.principal always exists
        request.state.principal = Principal.system()

        if not self._enabled:
            return await call_next(request)

        path = request.url.path

        # Public paths bypass all checks
        for pub in PUBLIC_PATHS:
            if path == pub or path.startswith(pub.rstrip("/") + "/"):
                return await call_next(request)

        # Determine required permission for this endpoint
        required = get_required_permission(request.method, path)
        if required is None:
            return await call_next(request)

        # Resolve stores lazily
        key_store, audit_store = self._get_stores()

        # If stores aren't ready yet (mid-startup), pass through safely
        if key_store is None:
            return await call_next(request)

        # Read API key from header
        key_value: Optional[str] = request.headers.get(self._header)

        if not key_value:
            await self._write_audit(
                audit_store, request,
                AuditAction.AUTH_FAILURE, "failure",
                error="Missing API key header",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "UNAUTHORIZED",
                    "message": f"API key required. Supply header: {self._header}",
                },
            )

        # Look up key
        api_key = await key_store.get_by_key(key_value)

        if api_key is None:
            await self._write_audit(
                audit_store, request,
                AuditAction.AUTH_FAILURE, "failure",
                error="API key not found",
            )
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "Invalid API key"},
            )

        if not api_key.is_valid():
            action = (
                AuditAction.AUTH_EXPIRED
                if api_key.expires_at
                else AuditAction.AUTH_FAILURE
            )
            await self._write_audit(
                audit_store, request, action, "failure",
                actor=api_key.name, actor_id=api_key.id,
                actor_role=api_key.role.value, tenant_id=api_key.tenant_id,
                error="API key is inactive or expired",
            )
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "API key inactive or expired"},
            )

        # Check permission
        if not api_key.has_permission(required):
            await self._write_audit(
                audit_store, request,
                AuditAction.AUTH_DENIED, "denied",
                actor=api_key.name, actor_id=api_key.id,
                actor_role=api_key.role.value, tenant_id=api_key.tenant_id,
                error=f"Permission denied: requires '{required}'",
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "FORBIDDEN",
                    "message": (
                        f"Permission '{required}' required. "
                        f"Key '{api_key.name}' has role '{api_key.role.value}'."
                    ),
                },
            )

        # ── Auth success ──────────────────────────────────────────────────────
        request.state.principal = Principal.from_api_key(api_key)

        logger.debug(
            f"[RBAC] ✅ '{api_key.name}' ({api_key.role.value}) "
            f"→ {request.method} {path}"
        )

        # Background: update last_used — non-blocking, never fails the request
        try:
            asyncio.ensure_future(key_store.update_last_used(key_value))
        except RuntimeError:
            pass

        return await call_next(request)

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _write_audit(
        self,
        audit_store,
        request: Request,
        action: AuditAction,
        outcome: str,
        *,
        error: Optional[str] = None,
        actor: str = "anonymous",
        actor_id: str = "",
        actor_role: str = "",
        tenant_id: str = "default",
    ) -> None:
        if audit_store is None:
            return
        try:
            event = AuditEvent(
                action=action,
                actor=actor,
                actor_id=actor_id,
                actor_role=actor_role,
                tenant_id=tenant_id,
                resource_type="auth",
                resource_id=request.url.path,
                outcome=outcome,
                details={"method": request.method, "path": request.url.path},
                ip_address=_get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                error=error,
            )
            await audit_store.append(event)
        except Exception as exc:
            logger.debug(f"[RBAC] Audit write error: {exc}")


def _get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
