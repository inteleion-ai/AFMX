"""
AFMX Admin Routes — API Key Management
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from afmx.auth.rbac import ROLE_PERMISSIONS, APIKey, Role

logger = logging.getLogger(__name__)

admin_router = APIRouter()


def get_api_key_store():
    from afmx.main import afmx_app
    return afmx_app.api_key_store


def get_audit_store():
    from afmx.main import afmx_app
    return afmx_app.audit_store


class CreateKeyRequest(BaseModel):
    name: str                        = Field(..., min_length=1, max_length=128)
    role: Role                       = Field(default=Role.DEVELOPER)
    tenant_id: str                   = Field(default="default", min_length=1, max_length=64)
    description: str                 = Field(default="")
    expires_in_days: Optional[float] = Field(default=None, ge=1)
    permission_overrides: List[str]  = Field(default_factory=list)


@admin_router.post("/admin/keys", status_code=201, summary="Create a new API key", tags=["Admin"])
async def create_key(
    request: Request,
    body: CreateKeyRequest,
    store=Depends(get_api_key_store),
    audit=Depends(get_audit_store),
):
    principal = getattr(request.state, "principal", None)
    caller_name = principal.key_name if principal else "system"

    expires_at = None
    if body.expires_in_days:
        expires_at = time.time() + body.expires_in_days * 86400

    key = APIKey(
        name=body.name,
        role=body.role,
        tenant_id=body.tenant_id,
        description=body.description,
        expires_at=expires_at,
        permission_overrides=set(body.permission_overrides),
        created_by=caller_name,
    )
    await store.create(key)

    try:
        from afmx.audit.model import AuditAction, AuditEvent
        await audit.append(AuditEvent(
            action=AuditAction.KEY_CREATED,
            actor=caller_name,
            actor_id=principal.key_id if principal else "",
            actor_role=principal.role.value if principal else "SYSTEM",
            tenant_id=body.tenant_id,
            resource_type="key",
            resource_id=key.id,
            outcome="success",
            details={"name": body.name, "role": body.role.value},
        ))
    except Exception:
        pass

    return {
        **key.to_dict(redact=False),
        "message": "Store this key securely — it will not be shown again.",
    }


@admin_router.get("/admin/keys", summary="List all API keys (redacted)", tags=["Admin"])
async def list_keys(
    request: Request,
    tenant_id: Optional[str] = None,
    active_only: bool = False,
    store=Depends(get_api_key_store),
):
    principal = getattr(request.state, "principal", None)
    if principal and principal.role.value not in ("ADMIN",):
        tenant_id = principal.tenant_id
    keys = await store.list_all(tenant_id=tenant_id, active_only=active_only)
    return {"count": len(keys), "keys": [k.to_dict(redact=True) for k in keys]}


@admin_router.get("/admin/keys/{key_id}", summary="Get a single API key", tags=["Admin"])
async def get_key(key_id: str, store=Depends(get_api_key_store)):
    key = await store.get_by_id(key_id)
    if not key:
        raise HTTPException(status_code=404, detail=f"Key '{key_id}' not found")
    return key.to_dict(redact=True)


@admin_router.post("/admin/keys/{key_id}/revoke", summary="Revoke an API key", tags=["Admin"])
async def revoke_key(
    key_id: str,
    request: Request,
    store=Depends(get_api_key_store),
    audit=Depends(get_audit_store),
):
    principal = getattr(request.state, "principal", None)
    ok = await store.revoke(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Key '{key_id}' not found")
    try:
        from afmx.audit.model import AuditAction, AuditEvent
        await audit.append(AuditEvent(
            action=AuditAction.KEY_REVOKED,
            actor=principal.key_name if principal else "system",
            actor_id=principal.key_id if principal else "",
            actor_role=principal.role.value if principal else "SYSTEM",
            resource_type="key", resource_id=key_id, outcome="success",
        ))
    except Exception:
        pass
    return {"message": f"Key '{key_id}' revoked", "key_id": key_id}


@admin_router.delete("/admin/keys/{key_id}", summary="Hard-delete an API key", tags=["Admin"])
async def delete_key(
    key_id: str,
    request: Request,
    store=Depends(get_api_key_store),
    audit=Depends(get_audit_store),
):
    principal = getattr(request.state, "principal", None)
    ok = await store.delete(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Key '{key_id}' not found")
    try:
        from afmx.audit.model import AuditAction, AuditEvent
        await audit.append(AuditEvent(
            action=AuditAction.KEY_DELETED,
            actor=principal.key_name if principal else "system",
            actor_id=principal.key_id if principal else "",
            actor_role=principal.role.value if principal else "SYSTEM",
            resource_type="key", resource_id=key_id, outcome="success",
        ))
    except Exception:
        pass
    return {"message": f"Key '{key_id}' permanently deleted", "key_id": key_id}


@admin_router.get("/admin/stats", summary="System statistics", tags=["Admin"])
async def admin_stats(store=Depends(get_api_key_store)):
    from afmx.config import settings
    from afmx.main import afmx_app

    state_count = 0
    try:
        if afmx_app.state_store:
            state_count = await afmx_app.state_store.count()
    except Exception:
        pass

    audit_count = 0
    try:
        if afmx_app.audit_store:
            audit_count = await afmx_app.audit_store.count()
    except Exception:
        pass

    key_count = await store.count()

    return {
        "version": settings.APP_VERSION,
        "uptime_seconds": round(afmx_app.uptime_seconds, 2),
        "concurrency": afmx_app.concurrency_manager.get_stats(),
        "store_backend": settings.STORE_BACKEND,       # FIX: was hardcoded "memory"
        "executions_in_store": state_count,
        "audit_events": audit_count,
        "api_keys": key_count,
        "adapters": [a["name"] for a in afmx_app.adapter_registry.list_adapters()],
        "handlers": len(afmx_app.plugin_registry.list_all()),
    }


@admin_router.get("/admin/roles", summary="List roles and permissions", tags=["Admin"])
async def list_roles():
    return {
        "roles": [
            {"role": role.value, "permissions": sorted(perms)}
            for role, perms in ROLE_PERMISSIONS.items()
        ]
    }
