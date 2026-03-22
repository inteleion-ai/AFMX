"""
AFMX LangChain Adapter
Wraps LangChain tools and chains for execution inside the AFMX runtime.

Mapping:
    LangChain BaseTool     → AFMX TOOL node
    LangChain BaseChain    → AFMX FUNCTION node
    LangChain Runnable     → AFMX FUNCTION node

The adapter does NOT import langchain at module level.
If langchain is not installed, registering the adapter succeeds but
calling to_afmx_node() / execute() raises a clear ImportError.

Usage:
    from afmx.adapters.langchain import LangChainAdapter
    from afmx.core.executor import HandlerRegistry

    adapter = LangChainAdapter()

    # Register a tool
    node = adapter.to_afmx_node(my_tool, node_id="search", node_name="web_search")

    # Register the handler so AFMX engine can call it
    adapter.register_handler(my_tool)

    # Use node in an ExecutionMatrix
    matrix = ExecutionMatrix(nodes=[node], ...)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from afmx.adapters.base import AdapterNodeConfig, AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.node import Node, NodeConfig, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "langchain:"


def _require_langchain() -> None:
    try:
        import langchain  # noqa: F401
    except ImportError:
        raise ImportError(
            "langchain is required for LangChainAdapter. "
            "Install: pip install langchain"
        )


class LangChainAdapter(AFMXAdapter):
    """
    AFMX adapter for LangChain tools, chains, and runnables.

    Supports:
    - BaseTool         (.run() / ._arun())
    - BaseChain        (.run() / .ainvoke())
    - Runnable         (.invoke() / .ainvoke())
    """

    @property
    def name(self) -> str:
        return "langchain"

    # ─── Node creation ────────────────────────────────────────────────────────

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: Optional[NodeType] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Convert a LangChain tool / chain / runnable to an AFMX Node.
        Also registers the handler so the AFMX engine can call it.
        """
        _require_langchain()
        detected_type = self._detect_node_type(external_obj)
        resolved_type = node_type or detected_type
        handler_key = self._handler_key(external_obj)

        # Register the handler in the global HandlerRegistry
        self.register_handler(external_obj)

        return self._make_node(
            handler_key=handler_key,
            external_ref=external_obj,
            node_id=node_id,
            node_name=node_name or getattr(external_obj, "name", handler_key),
            node_type=resolved_type,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config=extra_config,
        )

    def register_handler(self, external_obj: Any) -> str:
        """
        Register a LangChain object as an AFMX handler.
        Returns the handler key.
        """
        key = self._handler_key(external_obj)
        handler = self.make_handler(external_obj)
        HandlerRegistry.register(key, handler)
        return key

    # ─── Execution ────────────────────────────────────────────────────────────

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """Execute a LangChain tool / chain / runnable."""
        _require_langchain()
        raw_input = node_input.get("input")
        params = node_input.get("params", {})

        # Build the effective input — params override input when present
        effective_input = params if params else raw_input

        try:
            output = await self._invoke(external_ref, effective_input)
            return self.normalize(output)
        except Exception as exc:
            logger.error(f"[LangChainAdapter] Execution error: {exc}", exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    def normalize(self, raw_output: Any) -> AdapterResult:
        """Normalise LangChain output to AdapterResult."""
        if isinstance(raw_output, dict) and "output" in raw_output:
            return AdapterResult.ok(output=raw_output["output"])
        return AdapterResult.ok(output=raw_output)

    # ─── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _invoke(obj: Any, input_data: Any) -> Any:
        """
        Call the right method based on what the object exposes.
        Prefers async methods when available.
        """
        import asyncio

        # Runnable interface (LangChain v0.1+)
        if hasattr(obj, "ainvoke"):
            return await obj.ainvoke(input_data)
        if hasattr(obj, "invoke"):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, obj.invoke, input_data)

        # Legacy BaseTool interface
        if hasattr(obj, "_arun"):
            input_str = str(input_data) if not isinstance(input_data, str) else input_data
            return await obj._arun(input_str)
        if hasattr(obj, "run"):
            input_str = str(input_data) if not isinstance(input_data, str) else input_data
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, obj.run, input_str)

        # Last resort — call directly
        if callable(obj):
            import inspect
            if inspect.iscoroutinefunction(obj):
                return await obj(input_data)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, obj, input_data)

        raise TypeError(
            f"LangChain object {type(obj).__name__} has no known invocation method"
        )

    @staticmethod
    def _detect_node_type(obj: Any) -> NodeType:
        """Detect whether the object is a tool or a chain/function."""
        try:
            from langchain.tools import BaseTool
            if isinstance(obj, BaseTool):
                return NodeType.TOOL
        except ImportError:
            pass
        return NodeType.FUNCTION

    @staticmethod
    def _handler_key(obj: Any) -> str:
        obj_name = getattr(obj, "name", None) or type(obj).__name__.lower()
        return f"{_HANDLER_PREFIX}{obj_name}"
