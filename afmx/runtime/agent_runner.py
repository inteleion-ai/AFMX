"""
AFMX Agent Runner
Wraps agent callables for execution within the AFMX runtime.
Manages agent lifecycle (acquire/release) and structured error capture.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from afmx.models.execution import ExecutionContext
from afmx.models.node import Node

logger = logging.getLogger(__name__)


class AgentRunnerError(Exception):
    """Raised when an agent execution fails after all retries."""
    def __init__(self, agent_key: str, original: Exception):
        self.agent_key = agent_key
        self.original = original
        super().__init__(f"Agent '{agent_key}' failed: {original}")


async def run_agent(
    handler: Callable,
    node_input: Dict[str, Any],
    context: ExecutionContext,
    node: Node,
) -> Any:
    """
    AFMX standard agent runner.

    Agent handlers receive the same signature as tool handlers:
        input:    dict with {input, params, variables, node_outputs, memory, metadata}
        context:  ExecutionContext
        node:     Node definition

    Agents differ from tools in:
    - They may produce structured decisions (not just data)
    - They may write to context.memory (shared state)
    - They are tracked for concurrency via AgentDispatcher.acquire/release

    Returns:
        Any — agent output
    """
    agent_key = node.handler
    start = time.perf_counter()

    try:
        if asyncio.iscoroutinefunction(handler):
            result = await handler(node_input, context, node)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, handler, node_input, context, node)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"[AgentRunner] '{agent_key}' completed in {elapsed_ms:.1f}ms")
        return result

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            f"[AgentRunner] '{agent_key}' raised {type(exc).__name__} "
            f"after {elapsed_ms:.1f}ms: {exc}"
        )
        raise AgentRunnerError(agent_key=agent_key, original=exc) from exc
