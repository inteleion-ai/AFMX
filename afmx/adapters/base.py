"""
AFMX Adapter Base Contract
Every adapter is a thin, stateless translation layer between an external
agent framework and the AFMX execution runtime.

Design rules:
  - Adapters never hold state
  - Adapters never call the AFMX engine directly
  - Adapters translate: external thing → AFMX Node / ExecutionMatrix
  - Adapters wrap: external callable → AFMX-compatible handler
  - External framework imports are always lazy (inside methods)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from afmx.models.node import Node, NodeType, RetryPolicy, TimeoutPolicy, NodeConfig

logger = logging.getLogger(__name__)


# ─── Adapter Result ───────────────────────────────────────────────────────────

@dataclass
class AdapterResult:
    """
    Normalised result returned by every adapter execution.
    AFMX maps this to a NodeResult internally.
    """
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, output: Any = None, **meta) -> "AdapterResult":
        return cls(success=True, output=output, metadata=meta)

    @classmethod
    def fail(cls, error: str, error_type: str = "AdapterError", **meta) -> "AdapterResult":
        return cls(
            success=False, error=error,
            error_type=error_type, metadata=meta,
        )


# ─── Adapter Config ───────────────────────────────────────────────────────────

@dataclass
class AdapterNodeConfig:
    """
    Config block carried inside a Node when created by an adapter.
    Stored in node.metadata["adapter_config"].
    """
    adapter_name: str
    external_ref: Any = None          # The original external object (tool, chain, etc.)
    extra: Dict[str, Any] = field(default_factory=dict)


# ─── Base Adapter ─────────────────────────────────────────────────────────────

class AFMXAdapter(ABC):
    """
    Abstract base for all AFMX adapters.

    Subclasses implement:
      - name            property — unique adapter identifier
      - to_afmx_node()  — convert an external object to an AFMX Node
      - execute()       — run the external logic; return AdapterResult
      - normalize()     — convert raw external output to AdapterResult

    Handler factories:
      - make_handler()  — returns an AFMX-compatible async callable that
                          wraps execute() for use with HandlerRegistry
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter name, e.g. 'langchain', 'langgraph', 'crewai'."""

    @abstractmethod
    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.FUNCTION,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Translate an external framework object into an AFMX Node.
        The returned Node has its handler set to the adapter's registry key
        so the AFMX engine can dispatch to this adapter's execute() method.
        """

    @abstractmethod
    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """
        Execute the external framework object.
        node_input is the standard AFMX node input dict.
        external_ref is the original external object (tool, chain, etc.).
        Returns an AdapterResult — never raises.
        """

    def normalize(self, raw_output: Any) -> AdapterResult:
        """
        Convert raw output from external framework to AdapterResult.
        Override this when the framework returns non-standard shapes.
        """
        return AdapterResult.ok(output=raw_output)

    def make_handler(self, external_ref: Any) -> Callable:
        """
        Return an AFMX-compatible async handler that wraps execute().

        Usage:
            handler = adapter.make_handler(langchain_tool)
            HandlerRegistry.register("my_tool", handler)

        Handler signature:  handler(input, context, node) → Any
        """
        adapter = self

        async def _handler(node_input: Dict[str, Any], context: Any, node: Any) -> Any:
            result = await adapter.execute(node_input, external_ref)
            if not result.success:
                raise RuntimeError(
                    f"[{adapter.name}] Execution failed: {result.error}"
                )
            return result.output

        _handler.__name__ = f"{self.name}_{getattr(external_ref, 'name', 'handler')}"
        return _handler

    def _make_node(
        self,
        handler_key: str,
        external_ref: Any,
        node_id: Optional[str],
        node_name: Optional[str],
        node_type: NodeType,
        retry_policy: Optional[RetryPolicy],
        timeout_policy: Optional[TimeoutPolicy],
        extra_config: Optional[Dict[str, Any]],
    ) -> Node:
        """Shared Node construction used by all to_afmx_node() implementations."""
        import uuid
        resolved_name = node_name or getattr(external_ref, "name", handler_key)
        resolved_id = node_id or str(uuid.uuid4())

        return Node(
            id=resolved_id,
            name=resolved_name,
            type=node_type,
            handler=handler_key,
            config=NodeConfig(params=extra_config or {}),
            retry_policy=retry_policy or RetryPolicy(retries=2, backoff_seconds=0.5),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=30.0),
            metadata={
                "adapter": self.name,
                "adapter_config": AdapterNodeConfig(
                    adapter_name=self.name,
                    external_ref=external_ref,
                    extra=extra_config or {},
                ).__dict__,
            },
        )
