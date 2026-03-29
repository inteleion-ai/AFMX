# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
AFMX — Agent Flow Matrix Execution Engine  v1.3.0
=================================================
Public SDK surface.  Import everything from here.
"""

__version__ = "1.3.0"
__author__  = "Agentdyne9"
__license__ = "Apache-2.0"
from afmx.adapters.base import AdapterNodeConfig, AdapterResult, AFMXAdapter
from afmx.adapters.bedrock import BedrockAdapter
from afmx.adapters.google_adk import GoogleADKAdapter
from afmx.adapters.mcp import MCPAdapter, MCPServerConfig, infer_cognitive_layer
from afmx.adapters.registry import AdapterRegistry, adapter_registry
from afmx.adapters.semantic_kernel import SemanticKernelAdapter
from afmx.core.cognitive_router import CognitiveModelRouter
from afmx.core.concurrency import ConcurrencyManager
from afmx.domains import DomainPack, DomainRegistry, domain_registry
from afmx.domains.finance import FinanceDomain, FinanceRole
from afmx.domains.healthcare import HealthcareDomain, HealthcareRole
from afmx.domains.legal import LegalDomain, LegalRole
from afmx.domains.manufacturing import ManufacturingDomain, ManufacturingRole
from afmx.domains.tech import AgentRole, TechDomain
from afmx.core.dispatcher import AgentDispatcher, AgentTier, DispatchPolicy, DispatchRequest
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry
from afmx.core.hooks import HookPayload, HookRegistry, HookType, default_hooks
from afmx.core.retry import RetryManager
from afmx.core.router import RoutingRule, RoutingStrategy, ToolRouter
from afmx.core.variable_resolver import VariableResolver
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode, MatrixAddress
from afmx.models.node import (
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

__all__ = [
    # Engine
    "AFMXEngine",
    "ToolRouter", "RoutingRule", "RoutingStrategy",
    "AgentDispatcher", "DispatchRequest", "AgentTier", "DispatchPolicy",
    "HandlerRegistry", "RetryManager",
    "HookRegistry", "HookPayload", "HookType", "default_hooks",
    "ConcurrencyManager", "VariableResolver",
    # v1.2: Cognitive Execution Matrix
    "CognitiveModelRouter",
    "CognitiveLayer", "AgentRole", "MatrixAddress",
    # v1.2: Domain packs — open column axis
    "DomainPack", "DomainRegistry", "domain_registry",
    "TechDomain",
    "FinanceDomain",    "FinanceRole",
    "HealthcareDomain", "HealthcareRole",
    "LegalDomain",      "LegalRole",
    "ManufacturingDomain", "ManufacturingRole",
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
    "MCPAdapter", "MCPServerConfig", "infer_cognitive_layer",
    "SemanticKernelAdapter", "GoogleADKAdapter", "BedrockAdapter",
    # Exceptions
    "AFMXException", "MatrixValidationError", "MatrixCycleError",
    "ExecutionTimeoutError", "HandlerNotFoundError",
    "ToolRoutingError", "AgentDispatchError",
    # Helpers
    "generate_id", "now_ms", "elapsed_ms", "deep_merge",
    "resolve_dotted_path", "hash_matrix", "truncate", "async_retry", "Timer",
]
