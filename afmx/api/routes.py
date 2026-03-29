"""
AFMX API Routes

Endpoints:
  POST /afmx/execute           — synchronous execution
  POST /afmx/execute/async     — fire-and-forget async execution
  GET  /afmx/status/{id}       — poll execution status
  GET  /afmx/result/{id}       — full result with node outputs
  GET  /afmx/executions        — list recent executions
  POST /afmx/validate          — validate a matrix definition
  GET  /afmx/plugins           — list registered handlers
  POST /afmx/cancel/{id}       — cancel a running execution
  POST /afmx/retry/{id}        — retry a failed execution
  POST /afmx/resume/{id}       — resume from last checkpoint
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from afmx.api.schemas import (
    ExecuteRequest,
    ExecutionResponse,
    ExecutionStatusResponse,
    NodeResultResponse,
    PluginListResponse,
    ValidateRequest,
    ValidateResponse,
)
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import ExecutionMatrix
from afmx.models.node import NodeResult

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Dependencies ─────────────────────────────────────────────────────────────

def get_engine():
    from afmx.main import afmx_app
    return afmx_app.engine

def get_state_store():
    from afmx.main import afmx_app
    return afmx_app.state_store

def get_plugin_registry():
    from afmx.main import afmx_app
    return afmx_app.plugin_registry

def get_concurrency_manager():
    from afmx.main import afmx_app
    return afmx_app.concurrency_manager

def get_checkpoint_store():
    from afmx.main import afmx_app
    return afmx_app.checkpoint_store

def get_audit_store():
    from afmx.main import afmx_app
    return afmx_app.audit_store


# ─── Execute (sync) ───────────────────────────────────────────────────────────

@router.post(
    "/execute",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a matrix synchronously",
)
async def execute(
    request: Request,
    body: ExecuteRequest,
    engine=Depends(get_engine),
    state_store=Depends(get_state_store),
    concurrency=Depends(get_concurrency_manager),
    audit=Depends(get_audit_store),
):
    try:
        matrix = ExecutionMatrix.model_validate(body.matrix)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid matrix: {exc}")

    context = ExecutionContext(
        input=body.input,
        memory=body.memory or {},
        variables=body.variables or {},
        metadata=body.metadata or {},
    )
    record = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=context,
        triggered_by=body.triggered_by,
        tags=body.tags or [],
        # v1.2.1: snapshot the matrix definition so POST /resume/{id} works
        # even when this matrix was never saved to MatrixStore.
        matrix_snapshot=matrix.model_dump(),
    )
    await state_store.save(record)

    acquired = await concurrency.acquire(record.id, matrix.name)
    if not acquired:
        raise HTTPException(status_code=503, detail="Server at max concurrency. Retry later.")

    try:
        record = await engine.execute(matrix, context, record)
    except Exception as exc:
        logger.error(f"[API] Execution error: {exc}", exc_info=True)
        record.mark_failed(str(exc))
    finally:
        await concurrency.release(record.id, matrix.name)
        await state_store.save(record)

    # Audit
    await _audit_execution(request, audit, record, "execution.created")

    return _build_execution_response(record)


# ─── Execute (async) ──────────────────────────────────────────────────────────

@router.post(
    "/execute/async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a matrix asynchronously (fire-and-forget)",
)
async def execute_async(
    request: Request,
    body: ExecuteRequest,
    engine=Depends(get_engine),
    state_store=Depends(get_state_store),
    concurrency=Depends(get_concurrency_manager),
    audit=Depends(get_audit_store),
):
    try:
        matrix = ExecutionMatrix.model_validate(body.matrix)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid matrix: {exc}")

    context = ExecutionContext(
        input=body.input,
        memory=body.memory or {},
        variables=body.variables or {},
        metadata=body.metadata or {},
    )
    record = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=context,
        triggered_by=body.triggered_by,
        tags=body.tags or [],
        # v1.2.1: snapshot the matrix definition so POST /resume/{id} works
        # even when this matrix was never saved to MatrixStore.
        matrix_snapshot=matrix.model_dump(),
    )
    await state_store.save(record)

    async def _run_background(
        _engine=engine, _store=state_store, _con=concurrency,
        _mat=matrix, _ctx=context, _rec=record,
    ) -> None:
        acquired = await _con.acquire(_rec.id, _mat.name)
        if not acquired:
            _rec.mark_failed("Concurrency limit reached")
            await _store.save(_rec)
            return
        result_record = _rec
        try:
            result_record = await _engine.execute(_mat, _ctx, _rec)
        except Exception as exc:
            _rec.mark_failed(str(exc))
            result_record = _rec
        finally:
            await _con.release(_rec.id, _mat.name)
            await _store.save(result_record)

    asyncio.create_task(_run_background())

    await _audit_execution(request, audit, record, "execution.async_created")

    return {
        "execution_id": record.id,
        "status": record.status,
        "message": "Execution queued",
        "poll_url": f"/afmx/status/{record.id}",
        "stream_url": f"/afmx/ws/stream/{record.id}",
    }


# ─── Status ───────────────────────────────────────────────────────────────────

@router.get("/status/{execution_id}", response_model=ExecutionStatusResponse)
async def get_status(
    execution_id: str,
    state_store=Depends(get_state_store),
):
    record = await state_store.get(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ExecutionStatusResponse(
        execution_id=record.id,
        status=record.status,
        matrix_id=record.matrix_id,
        matrix_name=record.matrix_name,
        total_nodes=record.total_nodes,
        completed_nodes=record.completed_nodes,
        failed_nodes=record.failed_nodes,
        skipped_nodes=record.skipped_nodes,
        duration_ms=record.duration_ms,
        error=record.error,
        queued_at=record.queued_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


@router.get("/result/{execution_id}", response_model=ExecutionResponse)
async def get_result(
    execution_id: str,
    state_store=Depends(get_state_store),
):
    record = await state_store.get(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return _build_execution_response(record)


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("/executions", summary="List recent executions")
async def list_executions(
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None),
    matrix_name: Optional[str] = Query(default=None),
    state_store=Depends(get_state_store),
):
    status_enum = None
    if status_filter:
        try:
            status_enum = ExecutionStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: '{status_filter}'. "
                       f"Valid: {[s.value for s in ExecutionStatus]}",
            )

    records = await state_store.list_recent(limit=limit, status_filter=status_enum)
    if matrix_name:
        records = [r for r in records if r.matrix_name == matrix_name]

    return {
        "count": len(records),
        "executions": [
            {
                "execution_id": r.id,
                "matrix_name": r.matrix_name,
                "status": r.status,
                "total_nodes": r.total_nodes,
                "completed_nodes": r.completed_nodes,
                "failed_nodes": r.failed_nodes,
                "duration_ms": r.duration_ms,
                "queued_at": r.queued_at,
                "triggered_by": r.triggered_by,
                "tags": r.tags,
            }
            for r in records
        ],
    }


# ─── Validate ─────────────────────────────────────────────────────────────────

@router.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest):
    errors: List[str] = []
    node_count = edge_count = 0
    execution_order: List[str] = []
    try:
        matrix = ExecutionMatrix.model_validate(body.matrix)
        node_count = len(matrix.nodes)
        edge_count = len(matrix.edges)
        execution_order = matrix.topological_order()
    except Exception as exc:
        errors.append(str(exc))
    return ValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        node_count=node_count,
        edge_count=edge_count,
        execution_order=execution_order,
    )


# ─── Plugins ──────────────────────────────────────────────────────────────────

@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins(plugin_registry=Depends(get_plugin_registry)):
    all_plugins = plugin_registry.list_all()
    return PluginListResponse(
        tools=[p for p in all_plugins if p["type"] == "tool"],
        agents=[p for p in all_plugins if p["type"] == "agent"],
        functions=[p for p in all_plugins if p["type"] == "function"],
    )


# ─── Domain Packs (v1.2) ────────────────────────────────────────────────────────

@router.get(
    "/domains",
    summary="v1.2: List all registered domain packs (agent role vocabularies)",
    description=(
        "Returns all built-in and custom domain packs. Each pack defines "
        "the agent role strings (column axis) for a specific industry. "
        "Built-in packs: tech, finance, healthcare, legal, manufacturing."
    ),
)
async def list_domains():
    """List all registered domain packs with their role definitions."""
    from afmx.domains import domain_registry
    return {
        "count":   len(domain_registry),
        "domains": domain_registry.list_all(),
    }


@router.get(
    "/domains/{name}",
    summary="v1.2: Get a specific domain pack by name",
)
async def get_domain(name: str):
    """Return a single domain pack by name, or 404."""
    from afmx.domains import domain_registry
    pack = domain_registry.get(name)
    if not pack:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Domain pack '{name}' not found. "
                f"Available: {[p['name'] for p in domain_registry.list_all()]}"
            ),
        )
    return pack.to_dict()


# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.post("/cancel/{execution_id}", summary="Cancel a running execution (best-effort)")
async def cancel_execution(
    execution_id: str,
    request: Request,
    state_store=Depends(get_state_store),
    audit=Depends(get_audit_store),
):
    record = await state_store.get(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    if record.is_terminal:
        return {"message": f"Already terminal: {record.status}", "status": record.status}
    record.mark_aborted("Cancelled via API")
    await state_store.save(record)
    await _audit_execution(request, audit, record, "execution.cancelled")
    return {"message": "Cancellation requested", "status": record.status}


# ─── Retry ────────────────────────────────────────────────────────────────────

@router.post("/retry/{execution_id}", summary="Retry a failed execution")
async def retry_execution(
    execution_id: str,
    request: Request,
    engine=Depends(get_engine),
    state_store=Depends(get_state_store),
    concurrency=Depends(get_concurrency_manager),
    audit=Depends(get_audit_store),
):
    original = await state_store.get(execution_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    if not original.is_terminal:
        raise HTTPException(status_code=409, detail=f"Execution not terminal: {original.status}")
    if original.status == ExecutionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Cannot retry a successful execution")

    try:
        from afmx.main import afmx_app
        stored = await afmx_app.matrix_store.get(original.matrix_name)
        if not stored:
            raise HTTPException(
                status_code=404,
                detail=f"Matrix '{original.matrix_name}' not in store. "
                       "Save it via POST /afmx/matrices first.",
            )
        matrix = ExecutionMatrix.model_validate(stored.definition)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not reconstruct matrix: {exc}")

    context = original.context
    new_record = ExecutionRecord(
        matrix_id=matrix.id, matrix_name=matrix.name,
        context=context, triggered_by=f"retry:{execution_id}",
        tags=[*original.tags, "retry"],
    )
    await state_store.save(new_record)

    acquired = await concurrency.acquire(new_record.id, matrix.name)
    if not acquired:
        raise HTTPException(status_code=503, detail="Server at max concurrency. Retry later.")

    try:
        new_record = await engine.execute(matrix, context, new_record)
    except Exception as exc:
        new_record.mark_failed(str(exc))
    finally:
        await concurrency.release(new_record.id, matrix.name)
        await state_store.save(new_record)

    await _audit_execution(request, audit, new_record, "execution.retried")

    return {
        "original_execution_id": execution_id,
        "new_execution_id": new_record.id,
        "status": new_record.status,
        "duration_ms": new_record.duration_ms,
    }


# ─── Resume ───────────────────────────────────────────────────────────────────

@router.get(
    "/matrix-view/{execution_id}",
    summary="v1.1: Cognitive Execution Matrix view for an execution",
)
async def matrix_view(execution_id: str, state_store=Depends(get_state_store)):
    """
    Returns a 2D matrix view: CognitiveLayer (rows) x AgentRole (columns).
    Each cell shows the node that ran there, its status, duration, and model tier.
    Cells without a node are omitted from the 'cells' dict.
    Used by the Matrix View dashboard page.
    """
    record = await state_store.get(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    from afmx.models.node import CognitiveLayer

    # ROW axis — always the fixed CognitiveLayer sequence (universal, never changes)
    layers = [layer.value for layer in CognitiveLayer]

    # COLUMN axis — dynamically discovered from the execution's node results.
    # This supports any domain vocabulary: tech, finance, healthcare, legal, etc.
    cells:       Dict[str, Any] = {}
    active       = 0
    success      = 0
    roles_seen:  set = set()

    for node_id, result_data in record.node_results.items():
        if not isinstance(result_data, dict):
            continue
        cl = result_data.get("cognitive_layer")
        ar = result_data.get("agent_role")
        if cl and ar:
            roles_seen.add(ar)
            key = f"{cl}:{ar}"
            active += 1
            if result_data.get("status") == "SUCCESS":
                success += 1
            meta = result_data.get("metadata") or {}
            cells[key] = {
                "node_id":    node_id,
                "node_name":  result_data.get("node_name", node_id),
                "status":     result_data.get("status"),
                "duration_ms":result_data.get("duration_ms"),
                "model_tier": meta.get("__model_tier__"),
                "model":      meta.get("__model_hint__"),
                "error":      result_data.get("error"),
                "attempt":    result_data.get("attempt", 1),
            }

    # Sorted roles list — the column headers for the dashboard matrix grid
    roles          = sorted(roles_seen)
    total_possible = len(layers) * len(roles) if roles else 0

    # Enrich roles with domain pack descriptions where available
    from afmx.domains import domain_registry as _dr
    role_meta = {
        r: {
            "description": _dr.resolve_role(r),
            "domain":      _dr.find_domain_for_role(r),
        }
        for r in roles
    }

    return {
        "execution_id": execution_id,
        "matrix_name":  record.matrix_name,
        "status":       record.status,
        "layers":       layers,
        "roles":        roles,      # dynamic — whatever domain this execution used
        "role_meta":    role_meta,  # descriptions from registered domain packs
        "cells":        cells,
        "summary": {
            "total_possible": total_possible,
            "active_cells":   active,
            "success_cells":  success,
            "failed_cells":   active - success,
            "coverage_pct":   round(active / total_possible * 100, 1) if total_possible else 0.0,
            "success_rate":   round(success / active * 100, 1) if active else 0.0,
        },
    }


@router.post(
    "/resume/{execution_id}",
    summary="Resume a failed/partial execution from its last checkpoint",
    description=(
        "Restores the execution context from the checkpoint saved after the last "
        "successful node, then re-runs only the remaining nodes. Nodes that already "
        "completed are skipped automatically."
    ),
)
async def resume_execution(
    execution_id: str,
    request: Request,
    engine=Depends(get_engine),
    state_store=Depends(get_state_store),
    concurrency=Depends(get_concurrency_manager),
    checkpoint_store=Depends(get_checkpoint_store),
    audit=Depends(get_audit_store),
):
    original = await state_store.get(execution_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    if original.status == ExecutionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Execution already completed — nothing to resume.")

    if original.status == ExecutionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Execution is still running.")

    # Load checkpoint
    checkpoint = await checkpoint_store.load(execution_id)
    if not checkpoint:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No checkpoint found for '{execution_id}'. "
                "Execution must be resumed from scratch using /retry."
            ),
        )

    # Reconstruct matrix — try MatrixStore first, then fall back to the snapshot
    # embedded in the ExecutionRecord (populated since v1.2.1 for ad-hoc executions).
    try:
        from afmx.main import afmx_app
        stored = await afmx_app.matrix_store.get(original.matrix_name)
        if stored:
            matrix = ExecutionMatrix.model_validate(stored.definition)
        elif original.matrix_snapshot:
            logger.info(
                "[resume] Matrix '%s' not in store — restoring from execution snapshot",
                original.matrix_name,
            )
            matrix = ExecutionMatrix.model_validate(original.matrix_snapshot)
        else:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Matrix '{original.matrix_name}' not found in MatrixStore and no "
                    "snapshot was captured at execution time.  Save the matrix via "
                    "POST /afmx/matrices before running, or upgrade to v1.2.1 which "
                    "automatically snapshots ad-hoc matrices."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not reconstruct matrix: {exc}")

    # Build resumed context — restore node outputs + memory from checkpoint
    context = ExecutionContext(
        input=original.context.input,
        memory={**original.context.memory},
        variables={**original.context.variables},
        metadata={**original.context.metadata},
        node_outputs={},
    )
    checkpoint.apply_to_context(context)

    # Build new record — pre-populate completed nodes so engine skips them
    completed_results = {
        nid: original.node_results[nid]
        for nid in checkpoint.completed_node_ids
        if nid in original.node_results
    }
    new_record = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=context,
        triggered_by=f"resume:{execution_id}",
        tags=[*original.tags, "resumed"],
        node_results=completed_results,
        completed_nodes=len(completed_results),
        total_nodes=len(matrix.nodes),
    )
    await state_store.save(new_record)

    acquired = await concurrency.acquire(new_record.id, matrix.name)
    if not acquired:
        raise HTTPException(status_code=503, detail="Server at max concurrency. Retry later.")

    try:
        new_record = await engine.execute(matrix, context, new_record)
    except Exception as exc:
        new_record.mark_failed(str(exc))
    finally:
        await concurrency.release(new_record.id, matrix.name)
        await state_store.save(new_record)

    await _audit_execution(request, audit, new_record, "execution.resumed")

    return {
        "original_execution_id": execution_id,
        "new_execution_id": new_record.id,
        "status": new_record.status,
        "resumed_from_node_count": len(checkpoint.completed_node_ids),
        "duration_ms": new_record.duration_ms,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _audit_execution(
    request: Request,
    audit_store,
    record: ExecutionRecord,
    action_str: str,
) -> None:
    if audit_store is None:
        return
    try:
        from afmx.audit.model import AuditAction, AuditEvent
        principal = getattr(request.state, "principal", None)
        event = AuditEvent(
            action=AuditAction(action_str),
            actor=principal.key_name if principal else (record.triggered_by or "api"),
            actor_id=principal.key_id if principal else "",
            actor_role=principal.role.value if principal else "SYSTEM",
            tenant_id=principal.tenant_id if principal else "default",
            resource_type="execution",
            resource_id=record.id,
            outcome="success",
            details={
                "matrix_name": record.matrix_name,
                "status": record.status,
                "total_nodes": record.total_nodes,
            },
            ip_address=_get_ip(request),
            user_agent=request.headers.get("User-Agent"),
            duration_ms=record.duration_ms,
        )
        await audit_store.append(event)
    except Exception as exc:
        logger.debug(f"[Routes] Audit write failed: {exc}")


def _get_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _build_execution_response(record: ExecutionRecord) -> ExecutionResponse:
    node_results: Dict[str, NodeResultResponse] = {}
    for node_id, result_data in record.node_results.items():
        if isinstance(result_data, dict):
            known = {
                "node_id", "node_name", "status", "output",
                "error", "error_type", "attempt", "duration_ms",
                "started_at", "finished_at", "metadata",
            }
            filtered = {k: v for k, v in result_data.items() if k in known}
            node_results[node_id] = NodeResultResponse(**filtered)
        else:
            node_results[node_id] = NodeResultResponse(
                node_id=result_data.node_id,
                node_name=result_data.node_name,
                status=result_data.status,
                output=result_data.output,
                error=result_data.error,
                error_type=result_data.error_type,
                attempt=result_data.attempt,
                duration_ms=result_data.duration_ms,
            )
    return ExecutionResponse(
        execution_id=record.id,
        matrix_id=record.matrix_id,
        matrix_name=record.matrix_name,
        status=record.status,
        total_nodes=record.total_nodes,
        completed_nodes=record.completed_nodes,
        failed_nodes=record.failed_nodes,
        skipped_nodes=record.skipped_nodes,
        duration_ms=record.duration_ms,
        error=record.error,
        error_node_id=record.error_node_id,
        node_results=node_results,
        queued_at=record.queued_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        tags=record.tags,
    )
