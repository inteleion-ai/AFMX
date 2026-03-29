# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
AFMX Execution Context & Execution Record Models
=================================================
``ExecutionContext`` flows between nodes during a run, carrying input,
accumulated node outputs, shared memory, variables, and execution metadata.

``ExecutionRecord`` is the durable lifecycle record persisted to the store.
It captures every state transition, all node results, timing, error info,
and — from v1.2.1 — a full snapshot of the matrix definition so that
ad-hoc executions (never saved to ``MatrixStore``) can be resumed from
their last checkpoint.

Changelog
---------
v1.2.1  Added ``ExecutionRecord.matrix_snapshot`` — stores the serialised
        ``ExecutionMatrix`` at execution time so ``POST /afmx/resume/{id}``
        can reconstruct the matrix for executions that were never saved to
        ``MatrixStore``.  The field is ``Optional`` and ``None``-defaulted
        for full backward compatibility.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Terminal and non-terminal states for an AFMX matrix execution."""

    QUEUED    = "QUEUED"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    ABORTED   = "ABORTED"
    TIMEOUT   = "TIMEOUT"
    PARTIAL   = "PARTIAL"   # CONTINUE abort-policy — some nodes failed


class ExecutionContext(BaseModel):
    """
    Mutable execution context passed between nodes during a run.

    Carries the initial input, accumulated per-node outputs, shared working
    memory, runtime variables, and arbitrary metadata (tenant_id, trace_id,
    TCFP provenance hashes, etc.).

    All fields are plain Python types so the context can be serialised to
    JSON for checkpointing without custom encoders.
    """

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input: Any = Field(default=None, description="Initial input passed to the matrix")
    memory: Dict[str, Any] = Field(
        default_factory=dict,
        description="Shared memory — persisted across all nodes in this execution",
    )
    node_outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Map of node_id → output for downstream variable resolution",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Caller-supplied metadata propagated to every node handler. "
            "Common keys: tenant_id, trace_id, triggered_by, "
            "tcfp_run_id, tcfp_audit_hash."
        ),
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime variables injectable into node config params via {{variables.x}}",
    )

    # ── Convenience accessors ─────────────────────────────────────────────────

    def set_node_output(self, node_id: str, output: Any) -> None:
        """Persist a node's output so downstream nodes can reference it."""
        self.node_outputs[node_id] = output

    def get_node_output(self, node_id: str) -> Optional[Any]:
        """Return the stored output for *node_id*, or ``None``."""
        return self.node_outputs.get(node_id)

    def set_memory(self, key: str, value: Any) -> None:
        """Write *key* to shared working memory."""
        self.memory[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        """Read *key* from shared working memory, falling back to *default*."""
        return self.memory.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """
        Return an immutable dict snapshot suitable for checkpointing.

        Used by ``CheckpointStore.update_node_complete()`` after each
        successful node so that the execution can be resumed from its
        last good state.
        """
        return {
            "execution_id": self.execution_id,
            "input":        self.input,
            "memory":       dict(self.memory),
            "node_outputs": dict(self.node_outputs),
            "metadata":     dict(self.metadata),
            "variables":    dict(self.variables),
        }


class ExecutionRecord(BaseModel):
    """
    Full durable lifecycle record for a matrix execution.

    Persisted to ``StateStore`` after every state transition and after
    each node completes.  The record is the authoritative source of truth
    for the execution lifecycle used by the dashboard, audit trail, and
    the resume / retry endpoints.

    .. versionchanged:: 1.2.1
       Added ``matrix_snapshot`` — an optional full serialisation of the
       ``ExecutionMatrix`` captured at execution start.  This allows
       ``POST /afmx/resume/{execution_id}`` to reconstruct the matrix
       definition for executions that were never saved to ``MatrixStore``
       (i.e., ad-hoc executions submitted directly via the API).

       Backward compatibility: the field defaults to ``None``.  Existing
       records without the field load and function identically.
    """

    id:            str            = Field(default_factory=lambda: str(uuid.uuid4()))
    matrix_id:     str
    matrix_name:   str
    status:        ExecutionStatus = Field(default=ExecutionStatus.QUEUED)
    context:       ExecutionContext = Field(default_factory=ExecutionContext)
    node_results:  Dict[str, Any]   = Field(default_factory=dict)
    total_nodes:     int = 0
    completed_nodes: int = 0
    failed_nodes:    int = 0
    skipped_nodes:   int = 0
    queued_at:  float          = Field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error:          Optional[str] = None
    error_node_id:  Optional[str] = None
    triggered_by:   Optional[str] = Field(
        default=None,
        description="Caller identifier — user_id, 'api', 'retry:…', 'resume:…', etc.",
    )
    tags: List[str] = Field(default_factory=list)

    # v1.2.1 — full matrix definition snapshot captured at execution start.
    # Used by the resume endpoint when the matrix is not in MatrixStore.
    matrix_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Serialised ExecutionMatrix captured when the execution started. "
            "Populated by POST /afmx/execute and POST /afmx/execute/async. "
            "Allows POST /afmx/resume/{id} to work for ad-hoc matrices "
            "that were never saved to MatrixStore."
        ),
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def duration_ms(self) -> Optional[float]:
        """Wall-clock execution duration in milliseconds, or ``None`` if not finished."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at) * 1000.0
        return None

    @property
    def is_terminal(self) -> bool:
        """``True`` when the execution has reached a final non-running state."""
        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.ABORTED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.PARTIAL,
        )

    # ── State transitions ─────────────────────────────────────────────────────

    def mark_started(self) -> None:
        """Transition to RUNNING and record wall-clock start time."""
        self.status     = ExecutionStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self) -> None:
        """Transition to COMPLETED and record wall-clock finish time."""
        self.status      = ExecutionStatus.COMPLETED
        self.finished_at = time.time()

    def mark_failed(
        self,
        error: str,
        error_node_id: Optional[str] = None,
    ) -> None:
        """Transition to FAILED, recording the error message and offending node."""
        self.status        = ExecutionStatus.FAILED
        self.finished_at   = time.time()
        self.error         = error
        self.error_node_id = error_node_id

    def mark_aborted(self, reason: str) -> None:
        """Transition to ABORTED (e.g. manual cancel or CCL policy rejection)."""
        self.status      = ExecutionStatus.ABORTED
        self.finished_at = time.time()
        self.error       = reason

    def mark_timeout(self) -> None:
        """Transition to TIMEOUT when ``global_timeout_seconds`` is exceeded."""
        self.status      = ExecutionStatus.TIMEOUT
        self.finished_at = time.time()
        self.error       = "Global execution timeout exceeded"

    def mark_partial(self) -> None:
        """
        Transition to PARTIAL — used when ``AbortPolicy.CONTINUE`` is set
        and one or more nodes failed but execution completed for the rest.
        """
        self.status      = ExecutionStatus.PARTIAL
        self.finished_at = time.time()
