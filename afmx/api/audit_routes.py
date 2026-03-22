"""
AFMX Audit Routes — Query and Export

Endpoints:
  GET  /afmx/audit                  — paginated query with filters
  GET  /afmx/audit/export/json      — full export as JSON array
  GET  /afmx/audit/export/ndjson    — full export as NDJSON
  GET  /afmx/audit/export/csv       — full export as CSV
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response as FResponse

logger = logging.getLogger(__name__)

audit_router = APIRouter()


def get_audit_store():
    from afmx.main import afmx_app
    return afmx_app.audit_store


@audit_router.get("/audit", summary="Query audit log with filters", tags=["Audit"])
async def query_audit(
    request: Request,                         # FIX: no default — FastAPI injects it
    since: Optional[float]       = Query(default=None),
    until: Optional[float]       = Query(default=None),
    action: Optional[str]        = Query(default=None),
    actor: Optional[str]         = Query(default=None),
    actor_id: Optional[str]      = Query(default=None),
    tenant_id: Optional[str]     = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    resource_id: Optional[str]   = Query(default=None),
    outcome: Optional[str]       = Query(default=None),
    limit: int                   = Query(default=100, ge=1, le=1000),
    offset: int                  = Query(default=0, ge=0),
    store=Depends(get_audit_store),
):
    # Tenant scoping — non-admin callers see only their own tenant
    principal = getattr(request.state, "principal", None)
    if principal and principal.role.value not in ("ADMIN", "OPERATOR"):
        tenant_id = principal.tenant_id

    events = await store.query(
        since=since, until=until, action=action,
        actor=actor, actor_id=actor_id, tenant_id=tenant_id,
        resource_type=resource_type, resource_id=resource_id,
        outcome=outcome, limit=limit, offset=offset,
    )
    total = await store.count()
    return {
        "total": total,
        "count": len(events),
        "offset": offset,
        "limit": limit,
        "events": [e.to_dict() for e in events],
    }


@audit_router.get(
    "/audit/export/json",
    summary="Export audit log as JSON",
    tags=["Audit"],
    response_class=FResponse,
)
async def export_json(
    since: Optional[float]   = Query(default=None),
    until: Optional[float]   = Query(default=None),
    action: Optional[str]    = Query(default=None),
    actor: Optional[str]     = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    outcome: Optional[str]   = Query(default=None),
    store=Depends(get_audit_store),
):
    content = await store.export_json(
        since=since, until=until, action=action,
        actor=actor, tenant_id=tenant_id, outcome=outcome,
    )
    return FResponse(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=afmx-audit.json"},
    )


@audit_router.get(
    "/audit/export/ndjson",
    summary="Export audit log as NDJSON",
    tags=["Audit"],
    response_class=FResponse,
)
async def export_ndjson(
    since: Optional[float]   = Query(default=None),
    until: Optional[float]   = Query(default=None),
    action: Optional[str]    = Query(default=None),
    actor: Optional[str]     = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    outcome: Optional[str]   = Query(default=None),
    store=Depends(get_audit_store),
):
    content = await store.export_ndjson(
        since=since, until=until, action=action,
        actor=actor, tenant_id=tenant_id, outcome=outcome,
    )
    return FResponse(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=afmx-audit.ndjson"},
    )


@audit_router.get(
    "/audit/export/csv",
    summary="Export audit log as CSV",
    tags=["Audit"],
    response_class=FResponse,
)
async def export_csv(
    since: Optional[float]   = Query(default=None),
    until: Optional[float]   = Query(default=None),
    action: Optional[str]    = Query(default=None),
    actor: Optional[str]     = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    outcome: Optional[str]   = Query(default=None),
    store=Depends(get_audit_store),
):
    content = await store.export_csv(
        since=since, until=until, action=action,
        actor=actor, tenant_id=tenant_id, outcome=outcome,
    )
    return FResponse(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afmx-audit.csv"},
    )
