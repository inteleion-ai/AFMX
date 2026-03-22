"""
AFMX Tool Runner
Wraps arbitrary tool callables for execution within the AFMX runtime.
Provides input validation, output normalization, and structured error capture.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from afmx.models.execution import ExecutionContext
from afmx.models.node import Node

logger = logging.getLogger(__name__)


class ToolRunnerError(Exception):
    """Raised when a tool execution fails after all retries."""
    def __init__(self, tool_key: str, original: Exception):
        self.tool_key = tool_key
        self.original = original
        super().__init__(f"Tool '{tool_key}' failed: {original}")


async def run_tool(
    handler: Callable,
    node_input: Dict[str, Any],
    context: ExecutionContext,
    node: Node,
) -> Any:
    """
    AFMX standard tool runner.

    Handlers receive:
        input:    dict with {input, params, variables, node_outputs, memory, metadata}
        context:  ExecutionContext (read-only recommended)
        node:     Node definition (for config access)

    Returns:
        Any — tool output, passed into context.node_outputs

    Raises:
        ToolRunnerError on failure (after retries exhausted)
    """
    tool_key = node.handler
    start = time.perf_counter()

    try:
        if asyncio.iscoroutinefunction(handler):
            result = await handler(node_input, context, node)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, handler, node_input, context, node)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"[ToolRunner] '{tool_key}' completed in {elapsed_ms:.1f}ms")
        return result

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            f"[ToolRunner] '{tool_key}' raised {type(exc).__name__} "
            f"after {elapsed_ms:.1f}ms: {exc}"
        )
        raise ToolRunnerError(tool_key=tool_key, original=exc) from exc
