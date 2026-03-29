"""
AFMX models package
"""
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode, MatrixAddress
from afmx.models.node import (
    AgentRole,
    CircuitBreakerPolicy,
    CognitiveLayer,
    Node,
    NodeConfig,
    NodeResult,
    NodeStatus,
    NodeType,
    RetryPolicy,
    TimeoutPolicy,
)

__all__ = [
    # Node
    "Node", "NodeType", "NodeStatus", "NodeResult",
    "RetryPolicy", "TimeoutPolicy", "CircuitBreakerPolicy", "NodeConfig",
    # Cognitive matrix — ROW axis (fixed enum)
    "CognitiveLayer",
    # Cognitive matrix — COLUMN axis (backward-compat constants)
    "AgentRole",
    # Edge
    "Edge", "EdgeCondition", "EdgeConditionType",
    # Matrix
    "ExecutionMatrix", "ExecutionMode", "AbortPolicy",
    "MatrixAddress",
    # Execution
    "ExecutionContext", "ExecutionRecord", "ExecutionStatus",
]
