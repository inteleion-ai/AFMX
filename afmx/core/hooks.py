"""
AFMX Node Hooks
Pre/post execution hooks at both matrix and node level.

Hook types:
    PRE_MATRIX  — fires before any node in the matrix runs
    POST_MATRIX — fires after matrix completes (success or failure)
    PRE_NODE    — fires before each individual node executes
    POST_NODE   — fires after each individual node completes

Usage:
    hooks = HookRegistry()

    @hooks.pre_node("enrich_input")
    async def add_trace_id(payload: HookPayload) -> HookPayload:
        payload.node_input["metadata"]["trace_id"] = generate_id()
        return payload

    @hooks.post_node("audit_log")
    async def log_result(payload: HookPayload) -> HookPayload:
        await audit_logger.log(payload.node_result)
        return payload
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from afmx.models.execution import ExecutionContext, ExecutionRecord
from afmx.models.node import Node, NodeResult

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    PRE_MATRIX = "pre_matrix"
    POST_MATRIX = "post_matrix"
    PRE_NODE = "pre_node"
    POST_NODE = "post_node"


@dataclass
class HookPayload:
    """
    Passed into every hook. Hooks may mutate node_input or context.memory.
    They must NOT mutate node, matrix structure, or record directly.
    """
    hook_type: HookType
    execution_id: str
    matrix_id: str
    matrix_name: str

    # Node-level only (None for matrix hooks)
    node: Optional[Node] = None
    node_input: Optional[Dict[str, Any]] = None   # PRE_NODE — hooks can mutate this
    node_result: Optional[NodeResult] = None       # POST_NODE — hooks can read this

    # Always available
    context: Optional[ExecutionContext] = None
    record: Optional[ExecutionRecord] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Hook callable type — receives payload, returns (possibly mutated) payload
HookFn = Callable[[HookPayload], Coroutine[Any, Any, HookPayload]]


@dataclass
class HookRegistration:
    name: str
    fn: HookFn
    hook_type: HookType
    priority: int = 100  # Lower = runs first
    enabled: bool = True
    node_filter: Optional[str] = None  # If set, only runs for this node name/id


class HookRegistry:
    """
    AFMX Hook Registry — middleware for node and matrix execution.

    Hooks execute in priority order.
    A hook that raises will be logged and skipped — it never kills execution.
    Hooks CAN mutate node_input (PRE_NODE) to enrich/transform before execution.
    Hooks CAN read node_result (POST_NODE) for audit/logging/alerting.
    """

    def __init__(self):
        self._hooks: List[HookRegistration] = []

    # ─── Decorator Registration ───────────────────────────────────────────────

    def pre_matrix(self, name: str, priority: int = 100):
        def decorator(fn: HookFn) -> HookFn:
            self.register(name, fn, HookType.PRE_MATRIX, priority=priority)
            return fn
        return decorator

    def post_matrix(self, name: str, priority: int = 100):
        def decorator(fn: HookFn) -> HookFn:
            self.register(name, fn, HookType.POST_MATRIX, priority=priority)
            return fn
        return decorator

    def pre_node(self, name: str, priority: int = 100, node_filter: Optional[str] = None):
        def decorator(fn: HookFn) -> HookFn:
            self.register(name, fn, HookType.PRE_NODE, priority=priority, node_filter=node_filter)
            return fn
        return decorator

    def post_node(self, name: str, priority: int = 100, node_filter: Optional[str] = None):
        def decorator(fn: HookFn) -> HookFn:
            self.register(name, fn, HookType.POST_NODE, priority=priority, node_filter=node_filter)
            return fn
        return decorator

    # ─── Programmatic Registration ────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: HookFn,
        hook_type: HookType,
        priority: int = 100,
        node_filter: Optional[str] = None,
    ) -> "HookRegistry":
        reg = HookRegistration(
            name=name,
            fn=fn,
            hook_type=hook_type,
            priority=priority,
            node_filter=node_filter,
        )
        self._hooks.append(reg)
        self._hooks.sort(key=lambda h: h.priority)
        logger.debug(f"[HookRegistry] Registered [{hook_type}] hook: '{name}'")
        return self

    def disable(self, name: str) -> None:
        for h in self._hooks:
            if h.name == name:
                h.enabled = False

    def enable(self, name: str) -> None:
        for h in self._hooks:
            if h.name == name:
                h.enabled = True

    # ─── Execution ────────────────────────────────────────────────────────────

    async def run(self, payload: HookPayload) -> HookPayload:
        """
        Run all applicable hooks for this payload's hook_type.
        Each hook receives the (possibly mutated) payload from the previous hook.
        Hook errors are isolated — execution continues regardless.
        """
        applicable = [
            h for h in self._hooks
            if h.enabled
            and h.hook_type == payload.hook_type
            and self._passes_node_filter(h, payload)
        ]

        for hook in applicable:
            try:
                payload = await hook.fn(payload)
            except Exception as exc:
                logger.error(
                    f"[HookRegistry] Hook '{hook.name}' raised {type(exc).__name__}: {exc}",
                    exc_info=True,
                )
                # Continue — hooks never kill execution

        return payload

    def list_hooks(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": h.name,
                "type": h.hook_type,
                "priority": h.priority,
                "enabled": h.enabled,
                "node_filter": h.node_filter,
            }
            for h in self._hooks
        ]

    # ─── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _passes_node_filter(hook: HookRegistration, payload: HookPayload) -> bool:
        if hook.node_filter is None:
            return True
        if payload.node is None:
            return False
        return payload.node.id == hook.node_filter or payload.node.name == hook.node_filter


# Global default hook registry
default_hooks = HookRegistry()
