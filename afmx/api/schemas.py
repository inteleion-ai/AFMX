"""
AFMX API Request/Response Schemas

FIX 1: Replaced deprecated Pydantic v1 class Config with model_config = ConfigDict()
FIX 2: NodeResultResponse now includes started_at and finished_at so the UI
        waterfall timeline can render accurate per-node Gantt bars.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ─── Request Schemas ──────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    """POST /afmx/execute"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "matrix": {
                    "name": "my-flow",
                    "mode": "SEQUENTIAL",
                    "nodes": [
                        {"id": "n1", "name": "search", "type": "TOOL", "handler": "search_tool"},
                        {"id": "n2", "name": "summarize", "type": "AGENT", "handler": "summarizer"},
                    ],
                    "edges": [{"from": "n1", "to": "n2"}],
                },
                "input": {"query": "latest AI research"},
                "triggered_by": "user_123",
            }
        }
    )

    matrix: Dict[str, Any] = Field(..., description="ExecutionMatrix definition as JSON")
    input: Optional[Any] = Field(default=None)
    memory: Optional[Dict[str, Any]] = Field(default=None)
    variables: Optional[Dict[str, Any]] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)
    triggered_by: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)


class ValidateRequest(BaseModel):
    """POST /afmx/validate"""
    matrix: Dict[str, Any] = Field(..., description="Matrix definition to validate")


# ─── Response Schemas ─────────────────────────────────────────────────────────

class NodeResultResponse(BaseModel):
    node_id: str
    node_name: str
    status: str
    output: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    attempt: int = 1
    duration_ms: Optional[float] = None
    # FIX 2: expose per-node wall-clock timestamps so the dashboard waterfall
    # timeline can compute accurate start offsets and bar widths.
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    # fallback metadata so callers know a fallback was used
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    """Returned from POST /afmx/execute"""
    execution_id: str
    matrix_id: str
    matrix_name: str
    status: str
    total_nodes: int
    completed_nodes: int
    failed_nodes: int
    skipped_nodes: int
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    error_node_id: Optional[str] = None
    node_results: Dict[str, NodeResultResponse] = Field(default_factory=dict)
    queued_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


class ExecutionStatusResponse(BaseModel):
    """Returned from GET /afmx/status/{id}"""
    execution_id: str
    status: str
    matrix_id: str
    matrix_name: str
    total_nodes: int
    completed_nodes: int
    failed_nodes: int
    skipped_nodes: int
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    queued_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


class ValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    execution_order: List[str] = Field(default_factory=list)


class PluginListResponse(BaseModel):
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    functions: List[Dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    store_backend: str
    active_executions: int = 0
    uptime_seconds: Optional[float] = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
