"""
AFMX core package
"""
from afmx.core.cognitive_router import CognitiveModelRouter
from afmx.core.concurrency import ConcurrencyManager
from afmx.core.dispatcher import AgentDispatcher, AgentTier, DispatchPolicy, DispatchRequest
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry, NodeExecutor
from afmx.core.hooks import HookPayload, HookRegistry, HookType, default_hooks
from afmx.core.retry import CircuitBreaker, CircuitState, RetryManager
from afmx.core.router import RoutingRule, RoutingStrategy, ToolRouter
from afmx.core.variable_resolver import VariableResolver
from afmx.core.variable_resolver import resolver as default_resolver

__all__ = [
    "AFMXEngine",
    "NodeExecutor", "HandlerRegistry",
    "ToolRouter", "RoutingRule", "RoutingStrategy",
    "AgentDispatcher", "DispatchRequest", "AgentTier", "DispatchPolicy",
    "RetryManager", "CircuitBreaker", "CircuitState",
    "HookRegistry", "HookPayload", "HookType", "default_hooks",
    "ConcurrencyManager",
    "VariableResolver", "default_resolver",
    # v1.1
    "CognitiveModelRouter",
]
