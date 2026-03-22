"""
AFMX Node Executor

Fixes applied:
  - checkpoint_store wired in: saves a checkpoint after every successful node execution
  - hooks receive matrix_id and matrix_name via context.metadata
"""
from __future__ import annotations
import asyncio
import importlib
import logging
import time
from typing import Any, Callable, Dict, Optional

from afmx.core.retry import RetryManager
from afmx.models.execution import ExecutionContext
from afmx.models.node import Node, NodeResult, NodeStatus

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """
    Global registry mapping handler keys to callable functions.
    Supports short aliases and dotted module paths.
    """
    _registry: Dict[str, Callable] = {}

    @classmethod
    def register(cls, key: str, handler: Callable) -> None:
        cls._registry[key] = handler
        logger.debug(f"[HandlerRegistry] Registered: '{key}'")

    @classmethod
    def resolve(cls, handler_str: str) -> Callable:
        if handler_str in cls._registry:
            return cls._registry[handler_str]
        try:
            module_path, func_name = handler_str.rsplit(".", 1)
            module = importlib.import_module(module_path)
            fn = getattr(module, func_name)
            cls._registry[handler_str] = fn
            return fn
        except (ValueError, ImportError, AttributeError) as exc:
            raise ImportError(
                f"Cannot resolve handler '{handler_str}': {exc}"
            ) from exc

    @classmethod
    def list_registered(cls) -> Dict[str, str]:
        return {k: repr(v) for k, v in cls._registry.items()}

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()


class NodeExecutor:
    """
    Executes a single AFMX node.

    Responsibilities:
    - Resolve handler from registry
    - Resolve template variables in params
    - Run pre/post hooks
    - Enforce timeout over the full retry loop
    - Delegate retry + circuit breaker to RetryManager
    - Save checkpoint after each successful node (if checkpoint_store is wired)
    - Return NodeResult (never raises)
    """

    def __init__(
        self,
        retry_manager: RetryManager,
        hook_registry=None,
        variable_resolver=None,
        checkpoint_store=None,
    ):
        self.retry_manager = retry_manager
        self.hook_registry = hook_registry
        self.variable_resolver = variable_resolver
        self.checkpoint_store = checkpoint_store  # wired from AFMXApplication.startup

    async def execute(
        self,
        node: Node,
        context: ExecutionContext,
        injected_handler: Optional[Callable] = None,
    ) -> NodeResult:
        """Execute a node and return a NodeResult. Never raises."""
        started_at = time.time()
        node_input: Dict[str, Any] = {}

        result = NodeResult(
            node_id=node.id,
            node_name=node.name,
            status=NodeStatus.RUNNING,
            started_at=started_at,
        )

        try:
            handler = injected_handler or HandlerRegistry.resolve(node.handler)
            node_input = self._build_input(node, context)
            node_input = await self._run_pre_hook(node, node_input, context)

            output, attempt = await asyncio.wait_for(
                self._retry_wrapped(node, handler, node_input, context),
                timeout=node.timeout_policy.timeout_seconds,
            )

            finished_at = time.time()
            result.status = NodeStatus.SUCCESS
            result.output = output
            result.attempt = attempt
            result.finished_at = finished_at
            result.duration_ms = (finished_at - started_at) * 1000

            logger.info(
                f"[NodeExecutor] ✅ '{node.name}' succeeded "
                f"in {result.duration_ms:.1f}ms (attempt {attempt})"
            )

            # Checkpoint: persist completed node so execution can resume after a crash
            if self.checkpoint_store is not None:
                try:
                    await self.checkpoint_store.update_node_complete(
                        execution_id=context.execution_id,
                        node_id=node.id,
                        node_output=output,
                        context=context,
                    )
                except Exception as ckpt_exc:
                    logger.warning(
                        f"[NodeExecutor] Checkpoint save failed for '{node.name}': {ckpt_exc}"
                    )

        except asyncio.TimeoutError:
            finished_at = time.time()
            result.status = NodeStatus.FAILED
            result.error = (
                f"Node '{node.name}' timed out after "
                f"{node.timeout_policy.timeout_seconds}s"
            )
            result.error_type = "TimeoutError"
            result.finished_at = finished_at
            result.duration_ms = (finished_at - started_at) * 1000
            logger.error(f"[NodeExecutor] ⏱ '{node.name}' timed out")

        except RuntimeError as exc:
            finished_at = time.time()
            result.status = NodeStatus.ABORTED
            result.error = str(exc)
            result.error_type = type(exc).__name__
            result.finished_at = finished_at
            result.duration_ms = (finished_at - started_at) * 1000
            logger.error(f"[NodeExecutor] 🚫 '{node.name}' aborted: {exc}")

        except ImportError as exc:
            finished_at = time.time()
            result.status = NodeStatus.FAILED
            result.error = str(exc)
            result.error_type = "ImportError"
            result.finished_at = finished_at
            result.duration_ms = (finished_at - started_at) * 1000
            logger.error(f"[NodeExecutor] ❓ '{node.name}' handler not found: {exc}")

        except Exception as exc:
            finished_at = time.time()
            result.status = NodeStatus.FAILED
            result.error = str(exc)
            result.error_type = type(exc).__name__
            result.finished_at = finished_at
            result.duration_ms = (finished_at - started_at) * 1000
            logger.error(f"[NodeExecutor] ❌ '{node.name}' failed: {exc}", exc_info=True)

        await self._run_post_hook(node, node_input, result, context)
        return result

    async def _retry_wrapped(
        self,
        node: Node,
        handler: Callable,
        node_input: Dict[str, Any],
        context: ExecutionContext,
    ) -> tuple[Any, int]:
        async def attempt_fn() -> Any:
            return await NodeExecutor._invoke_handler(handler, node_input, context, node)

        return await self.retry_manager.execute_with_retry(
            node_id=node.id,
            handler=attempt_fn,
            retry_policy=node.retry_policy,
            circuit_breaker_policy=node.circuit_breaker,
        )

    @staticmethod
    async def _invoke_handler(
        handler: Callable,
        node_input: Dict[str, Any],
        context: ExecutionContext,
        node: Node,
    ) -> Any:
        if asyncio.iscoroutinefunction(handler):
            return await handler(node_input, context, node)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, handler, node_input, context, node)

    def _build_input(self, node: Node, context: ExecutionContext) -> Dict[str, Any]:
        params = dict(node.config.params)
        if self.variable_resolver and params:
            params = self.variable_resolver.resolve_params(params, context)

        return {
            "input": context.input,
            "params": params,
            "variables": context.variables,
            "node_outputs": dict(context.node_outputs),
            "memory": dict(context.memory),
            "metadata": {**context.metadata, **node.metadata},
        }

    async def _run_pre_hook(
        self,
        node: Node,
        node_input: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        if not self.hook_registry:
            return node_input
        from afmx.core.hooks import HookPayload, HookType
        payload = HookPayload(
            hook_type=HookType.PRE_NODE,
            execution_id=context.execution_id,
            matrix_id=context.metadata.get("__matrix_id__", ""),
            matrix_name=context.metadata.get("__matrix_name__", ""),
            node=node,
            node_input=node_input,
            context=context,
        )
        payload = await self.hook_registry.run(payload)
        return payload.node_input if payload.node_input is not None else node_input

    async def _run_post_hook(
        self,
        node: Node,
        node_input: Dict[str, Any],
        result: NodeResult,
        context: ExecutionContext,
    ) -> None:
        if not self.hook_registry:
            return
        from afmx.core.hooks import HookPayload, HookType
        payload = HookPayload(
            hook_type=HookType.POST_NODE,
            execution_id=context.execution_id,
            matrix_id=context.metadata.get("__matrix_id__", ""),
            matrix_name=context.metadata.get("__matrix_name__", ""),
            node=node,
            node_input=node_input,
            node_result=result,
            context=context,
        )
        await self.hook_registry.run(payload)
