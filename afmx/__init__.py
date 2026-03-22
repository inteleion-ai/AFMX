"""
AFMX — Agent Flow Matrix Execution Engine
Public SDK surface — import everything from here.
"""
from afmx.adapters.base import AdapterNodeConfig, AdapterResult, AFMXAdapter
from afmx.adapters.registry import AdapterRegistry, adapter_registry
from afmx.core.concurrency import ConcurrencyManager
from afmx.core.dispatcher import AgentDispatcher, AgentTier, DispatchPolicy, DispatchRequest
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry
from afmx.core.hooks import HookPayload, HookRegistry, HookType, default_hooks
from afmx.core.retry import RetryManager
from afmx.core.router import RoutingRule, RoutingStrategy, ToolRouter
from afmx.core.variable_resolver import VariableResolver
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode
from afmx.models.node import (
    CircuitBreakerPolicy,
    Node,
    NodeConfig,
    NodeResult,
    NodeStatus,
    NodeType,
    RetryPolicy,
    TimeoutPolicy,
)
from afmx.observability.events import AFMXEvent, EventBus, EventType, LoggingEventHandler
from afmx.observability.metrics import AFMXMetrics
from afmx.plugins.registry import PluginRegistry, default_registry
from afmx.store.checkpoint import CheckpointData, InMemoryCheckpointStore
from afmx.store.matrix_store import InMemoryMatrixStore, RedisMatrixStore, StoredMatrix
from afmx.store.state_store import InMemoryStateStore, RedisStateStore
from afmx.utils.exceptions import (
    AFMXException,
    AgentDispatchError,
    ExecutionTimeoutError,
    HandlerNotFoundError,
    MatrixCycleError,
    MatrixValidationError,
    ToolRoutingError,
)
from afmx.utils.helpers import (
    Timer,
    async_retry,
    deep_merge,
    elapsed_ms,
    generate_id,
    hash_matrix,
    now_ms,
    resolve_dotted_path,
    truncate,
)

__version__ = "1.0.1"
__author__  = "Agentdyne9"
__license__ = "Apache-2.0"
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
    # Adapters
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
