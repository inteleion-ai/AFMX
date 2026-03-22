"""
AFMX Execution Context & Execution Record Models
Context flows between nodes. ExecutionRecord tracks the full run lifecycle.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid
import time


class ExecutionStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    TIMEOUT = "TIMEOUT"
    PARTIAL = "PARTIAL"   # CONTINUE mode — some nodes failed


class ExecutionContext(BaseModel):
    """
    Mutable execution context passed between nodes.
    Carries input, accumulated outputs, and arbitrary memory.
    """
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input: Any = Field(default=None, description="Initial input to the matrix")
    memory: Dict[str, Any] = Field(
        default_factory=dict,
        description="Shared memory for inter-node communication"
    )
    node_outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Map of node_id → output for downstream reference"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-supplied metadata (tenant_id, trace_id, etc.)"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime variables injectable into node configs"
    )

    def set_node_output(self, node_id: str, output: Any) -> None:
        self.node_outputs[node_id] = output

    def get_node_output(self, node_id: str) -> Optional[Any]:
        return self.node_outputs.get(node_id)

    def set_memory(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        return self.memory.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """Create an immutable snapshot for checkpointing."""
        return {
            "execution_id": self.execution_id,
            "input": self.input,
            "memory": dict(self.memory),
            "node_outputs": dict(self.node_outputs),
            "metadata": dict(self.metadata),
            "variables": dict(self.variables),
        }


class ExecutionRecord(BaseModel):
    """
    Full lifecycle record of a matrix execution.
    Persisted to the store for observability and replay.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    matrix_id: str
    matrix_name: str
    status: ExecutionStatus = Field(default=ExecutionStatus.QUEUED)
    context: ExecutionContext = Field(default_factory=ExecutionContext)
    node_results: Dict[str, Any] = Field(default_factory=dict)
    total_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    skipped_nodes: int = 0
    queued_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    error_node_id: Optional[str] = None
    triggered_by: Optional[str] = Field(
        default=None,
        description="Caller identifier — user_id, system, etc."
    )
    tags: List[str] = Field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at) * 1000
        return None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.ABORTED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.PARTIAL,
        )

    def mark_started(self) -> None:
        self.status = ExecutionStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self) -> None:
        self.status = ExecutionStatus.COMPLETED
        self.finished_at = time.time()

    def mark_failed(self, error: str, error_node_id: Optional[str] = None) -> None:
        self.status = ExecutionStatus.FAILED
        self.finished_at = time.time()
        self.error = error
        self.error_node_id = error_node_id

    def mark_aborted(self, reason: str) -> None:
        self.status = ExecutionStatus.ABORTED
        self.finished_at = time.time()
        self.error = reason

    def mark_timeout(self) -> None:
        self.status = ExecutionStatus.TIMEOUT
        self.finished_at = time.time()
        self.error = "Global execution timeout exceeded"

    def mark_partial(self) -> None:
        self.status = ExecutionStatus.PARTIAL
        self.finished_at = time.time()
