"""
AFMX Matrix Store API Routes

FIX: execute_named_matrix now uses the ConcurrencyManager (was missing).
FIX: SaveMatrixRequest uses ConfigDict instead of deprecated Pydantic v1 class Config.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from afmx.models.execution import ExecutionContext, ExecutionRecord
from afmx.models.matrix import ExecutionMatrix
from afmx.store.matrix_store import StoredMatrix

logger = logging.getLogger(__name__)

matrix_router = APIRouter()


def get_matrix_store():
    from afmx.main import afmx_app
    return afmx_app.matrix_store


def get_engine():
    from afmx.main import afmx_app
    return afmx_app.engine


def get_state_store():
    from afmx.main import afmx_app
    return afmx_app.state_store


def get_concurrency_manager():
    from afmx.main import afmx_app
    return afmx_app.concurrency_manager


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SaveMatrixRequest(BaseModel):
    # FIX: ConfigDict instead of class Config
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "search-and-summarize",
                "version": "1.0.0",
                "description": "Searches the web and summarizes results",
                "tags": ["search", "nlp"],
                "definition": {
                    "name": "search-and-summarize",
                    "mode": "SEQUENTIAL",
                    "nodes": [
                        {"id": "n1", "name": "search", "type": "TOOL", "handler": "search_tool"},
                        {"id": "n2", "name": "summarize", "type": "AGENT", "handler": "summarizer"},
                    ],
                    "edges": [{"from": "n1", "to": "n2"}],
                },
            }
        }
    )

    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(default="1.0.0")
    definition: Dict[str, Any] = Field(...)
    description: str = Field(default="")
    tags: List[str] = Field(default_factory=list)
    created_by: Optional[str] = Field(default=None)


class ExecuteNamedMatrixRequest(BaseModel):
    input: Optional[Any] = None
    memory: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    triggered_by: Optional[str] = None
    tags: Optional[List[str]] = None
    version: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@matrix_router.post(
    "/matrices",
    status_code=status.HTTP_201_CREATED,
    summary="Save a named matrix definition",
)
async def save_matrix(
    request: SaveMatrixRequest,
    matrix_store=Depends(get_matrix_store),
):
    try:
        ExecutionMatrix.model_validate(request.definition)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid matrix definition: {exc}",
        )

    stored = StoredMatrix(
        name=request.name, version=request.version,
        definition=request.definition, description=request.description,
        tags=request.tags, created_by=request.created_by,
    )
    await matrix_store.save(stored)
    return {"message": "Matrix saved", "name": stored.name,
            "version": stored.version, "created_at": stored.created_at}


@matrix_router.get("/matrices", summary="List all saved matrices")
async def list_matrices(
    tag: Optional[str] = Query(default=None),
    matrix_store=Depends(get_matrix_store),
):
    matrices = await matrix_store.list_all(tag_filter=tag)
    return {
        "count": len(matrices),
        "matrices": [
            {"name": m.name, "version": m.version, "description": m.description,
             "tags": m.tags, "created_at": m.created_at, "created_by": m.created_by}
            for m in matrices
        ],
    }


@matrix_router.get("/matrices/{name}", summary="Get a saved matrix by name")
async def get_matrix(
    name: str,
    version: Optional[str] = Query(default=None),
    matrix_store=Depends(get_matrix_store),
):
    stored = await matrix_store.get(name, version)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrix '{name}'" + (f" v{version}" if version else "") + " not found",
        )
    return stored.to_dict()


@matrix_router.get("/matrices/{name}/versions", summary="List all versions of a named matrix")
async def list_matrix_versions(
    name: str,
    matrix_store=Depends(get_matrix_store),
):
    versions = await matrix_store.list_versions(name)
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrix '{name}' not found",
        )
    return {
        "name": name,
        "versions": [
            {"version": m.version, "description": m.description,
             "created_at": m.created_at, "created_by": m.created_by}
            for m in versions
        ],
    }


@matrix_router.delete("/matrices/{name}", summary="Delete a saved matrix")
async def delete_matrix(
    name: str,
    version: Optional[str] = Query(default=None),
    matrix_store=Depends(get_matrix_store),
):
    deleted = await matrix_store.delete(name, version)
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrix '{name}' not found",
        )
    return {"message": f"Deleted {deleted} version(s) of '{name}'"}


@matrix_router.post("/matrices/{name}/execute", summary="Execute a saved matrix by name")
async def execute_named_matrix(
    name: str,
    request: ExecuteNamedMatrixRequest,
    matrix_store=Depends(get_matrix_store),
    engine=Depends(get_engine),
    state_store=Depends(get_state_store),
    # FIX: concurrency manager was missing from this endpoint
    concurrency=Depends(get_concurrency_manager),
):
    stored = await matrix_store.get(name, request.version)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrix '{name}'" + (f" v{request.version}" if request.version else "") + " not found",
        )

    try:
        matrix = ExecutionMatrix.model_validate(stored.definition)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored matrix is invalid: {exc}",
        )

    context = ExecutionContext(
        input=request.input,
        memory=request.memory or {},
        variables=request.variables or {},
        metadata=request.metadata or {},
    )
    record = ExecutionRecord(
        matrix_id=matrix.id, matrix_name=matrix.name,
        context=context, triggered_by=request.triggered_by,
        tags=request.tags or [],
    )
    await state_store.save(record)

    # FIX: acquire concurrency slot
    acquired = await concurrency.acquire(record.id, matrix.name)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server at maximum concurrency. Retry later.",
        )

    try:
        record = await engine.execute(matrix, context, record)
    except Exception as exc:
        logger.error(f"[MatrixRouter] Execution error: {exc}", exc_info=True)
        record.mark_failed(str(exc))
    finally:
        await concurrency.release(record.id, matrix.name)
        await state_store.save(record)

    return {
        "execution_id": record.id, "matrix_name": name,
        "version": stored.version, "status": record.status,
        "duration_ms": record.duration_ms,
        "completed_nodes": record.completed_nodes,
        "failed_nodes": record.failed_nodes,
    }
