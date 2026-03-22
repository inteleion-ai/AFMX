"""
AFMX — Public SDK surface

FIX: Removed stale adapter class imports that shadowed the real ones
     from afmx.adapters. Adapter classes are accessible via the
     adapter_registry singleton or direct import from afmx.adapters.
"""
from afmx.core.engine import AFMXEngine
from afmx.core.router import ToolRouter, RoutingRule, RoutingStrategy
from afmx.core.dispatcher import AgentDispatcher, DispatchRequest, AgentTier, DispatchPolicy
from afmx.core.executor import HandlerRegistry
from afmx.core.retry import RetryManager
from afmx.core.hooks import HookRegistry, HookPayload, HookType, default_hooks
from afmx.core.concurrency import ConcurrencyManager
from afmx.core.variable_resolver import VariableResolver

from afmx.models.node import (
    Node, NodeType, NodeStatus, NodeResult,
    RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy, NodeConfig,
)
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus

from afmx.plugins.registry import PluginRegistry, default_registry

from afmx.observability.events import EventBus, AFMXEvent, EventType, LoggingEventHandler
from afmx.observability.metrics import AFMXMetrics

from afmx.store.state_store import InMemoryStateStore, RedisStateStore
from afmx.store.matrix_store import InMemoryMatrixStore, RedisMatrixStore, StoredMatrix
from afmx.store.checkpoint import InMemoryCheckpointStore, CheckpointData

from afmx.adapters.base import AFMXAdapter, AdapterResult, AdapterNodeConfig
from afmx.adapters.registry import AdapterRegistry, adapter_registry

from afmx.utils.exceptions import (
    AFMXException, MatrixValidationError, MatrixCycleError,
    ExecutionTimeoutError, HandlerNotFoundError,
    ToolRoutingError, AgentDispatchError,
)
from afmx.utils.helpers import (
    generate_id, now_ms, elapsed_ms,
    deep_merge, resolve_dotted_path, hash_matrix,
    truncate, async_retry, Timer,
)

__version__ = "1.0.0"
__author__ = "Agentdyne9"
__python_requires__ = ">=3.10"

__all__ = [
    # Engine
    "AFMXEngine",
    "ToolRouter", "RoutingRule", "RoutingStrategy",
    "AgentDispatcher", "DispatchRequest", "AgentTier", "DispatchPolicy",
    "HandlerRegistry", "RetryManager",
    "HookRegistry", "HookPayload", "HookType", "default_hooks",
    "ConcurrencyManager", "VariableResolver",
    # Models
    "Node", "NodeType", "NodeStatus", "NodeResult",
    "RetryPolicy", "TimeoutPolicy", "CircuitBreakerPolicy", "NodeConfig",
    "Edge", "EdgeCondition", "EdgeConditionType",
    "ExecutionMatrix", "ExecutionMode", "AbortPolicy",
    "ExecutionContext", "ExecutionRecord", "ExecutionStatus",
    # Plugins
    "PluginRegistry", "default_registry",
    # Observability
    "EventBus", "AFMXEvent", "EventType", "LoggingEventHandler", "AFMXMetrics",
    # Store
    "InMemoryStateStore", "RedisStateStore",
    "InMemoryMatrixStore", "RedisMatrixStore", "StoredMatrix",
    "InMemoryCheckpointStore", "CheckpointData",
    # Adapters (base + registry; individual adapters via afmx.adapters)
    "AFMXAdapter", "AdapterResult", "AdapterNodeConfig",
    "AdapterRegistry", "adapter_registry",
    # Exceptions
    "AFMXException", "MatrixValidationError", "MatrixCycleError",
    "ExecutionTimeoutError", "HandlerNotFoundError",
    "ToolRoutingError", "AgentDispatchError",
    # Helpers
    "generate_id", "now_ms", "elapsed_ms", "deep_merge",
    "resolve_dotted_path", "hash_matrix", "truncate", "async_retry", "Timer",
]
