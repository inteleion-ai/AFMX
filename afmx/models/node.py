"""
AFMX Node Model
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import uuid


class NodeType(str, Enum):
    TOOL = "TOOL"
    AGENT = "AGENT"
    FUNCTION = "FUNCTION"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"
    ABORTED = "ABORTED"


class RetryPolicy(BaseModel):
    retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=60.0)
    jitter: bool = Field(default=True)


class TimeoutPolicy(BaseModel):
    # ge=0.01 allows sub-second timeouts for fast nodes and tests.
    # Production nodes default to 30 s via Node.timeout_policy default_factory.
    timeout_seconds: float = Field(default=30.0, ge=0.01)
    hard_kill: bool = Field(default=True)


class CircuitBreakerPolicy(BaseModel):
    enabled: bool = Field(default=False)
    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout_seconds: float = Field(default=60.0)
    half_open_max_calls: int = Field(default=2)


class NodeConfig(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class Node(BaseModel):
    """
    Core execution unit in AFMX.
    Deterministic: same handler + context = same result.
    """
    # FIX: replaced deprecated class Config with model_config (Pydantic v2)
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=128)
    type: NodeType
    handler: str = Field(..., description="Registry key or dotted module path")
    config: NodeConfig = Field(default_factory=NodeConfig)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    circuit_breaker: CircuitBreakerPolicy = Field(default_factory=CircuitBreakerPolicy)
    fallback_node_id: Optional[str] = Field(default=None)
    priority: int = Field(default=5, ge=1, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("handler")
    @classmethod
    def validate_handler(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("handler must be a non-empty string")
        return v.strip()


class NodeResult(BaseModel):
    """Captures the outcome of a single node execution."""
    node_id: str
    node_name: str
    status: NodeStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    attempt: int = Field(default=1)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == NodeStatus.SUCCESS

    @property
    def is_terminal_failure(self) -> bool:
        return self.status in (NodeStatus.FAILED, NodeStatus.ABORTED)
