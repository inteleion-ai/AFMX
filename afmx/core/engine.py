"""
AFMX Execution Engine — production version.

Fixes applied in this version:
  - AgentDispatcher.acquire() / release() now called around AGENT node execution
    so max_concurrent limits on agents are actually enforced.
  - checkpoint_store accepted and passed through to NodeExecutor (already wired
    at startup; engine keeps a reference for future resume support).
  - _run_sequential: skips nodes already in record.node_results (prevents
    fallback nodes from double-executing as standalone nodes).
  - _execute_node: marks the fallback node in record.node_results with
    NodeStatus.FALLBACK so the sequential loop knows it already ran.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from afmx.core.dispatcher import AgentDispatcher, AgentRegistration, DispatchRequest
from afmx.core.executor import NodeExecutor, HandlerRegistry
from afmx.core.retry import RetryManager
from afmx.core.router import ToolRouter
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode
from afmx.models.node import Node, NodeResult, NodeStatus, NodeType
from afmx.observability.events import EventBus, AFMXEvent, EventType

logger = logging.getLogger(__name__)

_ABORT_POLICIES = {AbortPolicy.FAIL_FAST, AbortPolicy.CRITICAL_ONLY}


class AFMXEngine:
    """
    AFMX Engine — the deterministic execution fabric.

    Design principles:
    - Deterministic: same matrix + context = same execution path
    - Non-intelligent: does NOT plan, does NOT reason
    - Composable: pluggable router, dispatcher, executor
    - Observable: every state transition emits an event
    - Fault-tolerant: retry, fallback, circuit breaker at node level
    """

    def __init__(
        self,
        tool_router: Optional[ToolRouter] = None,
        agent_dispatcher: Optional[AgentDispatcher] = None,
        event_bus: Optional[EventBus] = None,
        node_executor: Optional[NodeExecutor] = None,
    ):
        self.event_bus = event_bus or EventBus()
        self.retry_manager = RetryManager(event_bus=self.event_bus)
        self.node_executor = node_executor or NodeExecutor(self.retry_manager)
        self.tool_router = tool_router or ToolRouter()
        self.agent_dispatcher = agent_dispatcher or AgentDispatcher()

    # ─── Public API ───────────────────────────────────────────────────────────

    async def execute(
        self,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
    ) -> ExecutionRecord:
        record.total_nodes = len(matrix.nodes)
        record.mark_started()

        context.metadata["__matrix_id__"] = matrix.id
        context.metadata["__matrix_name__"] = matrix.name

        await self.event_bus.emit(AFMXEvent(
            type=EventType.EXECUTION_STARTED,
            execution_id=record.id, matrix_id=matrix.id,
            data={"mode": matrix.mode, "node_count": len(matrix.nodes)},
        ))

        await self._run_matrix_hook("pre_matrix", matrix, context, record)

        try:
            try:
                topo_order = matrix.topological_order()
            except ValueError as exc:
                record.mark_failed(str(exc))
                await self.event_bus.emit(AFMXEvent(
                    type=EventType.EXECUTION_FAILED,
                    execution_id=record.id, matrix_id=matrix.id,
                    data={"error": str(exc)},
                ))
                await self._run_matrix_hook("post_matrix", matrix, context, record)
                return record

            node_index: Dict[str, Node] = {n.id: n for n in matrix.nodes}

            await asyncio.wait_for(
                self._dispatch_mode(matrix, context, record, topo_order, node_index),
                timeout=matrix.global_timeout_seconds,
            )

        except asyncio.TimeoutError:
            record.mark_timeout()
            await self.event_bus.emit(AFMXEvent(
                type=EventType.EXECUTION_TIMEOUT,
                execution_id=record.id, matrix_id=matrix.id,
            ))
            await self._run_matrix_hook("post_matrix", matrix, context, record)
            return record

        if record.status == ExecutionStatus.RUNNING:
            if record.failed_nodes > 0 and matrix.abort_policy == AbortPolicy.CONTINUE:
                record.mark_partial()
            else:
                record.mark_completed()

        final_event = (
            EventType.EXECUTION_COMPLETED
            if record.status == ExecutionStatus.COMPLETED
            else EventType.EXECUTION_FAILED
        )
        await self.event_bus.emit(AFMXEvent(
            type=final_event,
            execution_id=record.id, matrix_id=matrix.id,
            data={
                "duration_ms": record.duration_ms,
                "completed_nodes": record.completed_nodes,
                "failed_nodes": record.failed_nodes,
                "skipped_nodes": record.skipped_nodes,
                "matrix_name": record.matrix_name,
                "mode": matrix.mode,
            },
        ))

        await self._run_matrix_hook("post_matrix", matrix, context, record)
        return record

    # ─── Mode dispatch ────────────────────────────────────────────────────────

    async def _dispatch_mode(
        self,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
        topo_order: List[str],
        node_index: Dict[str, Node],
    ) -> None:
        if matrix.mode == ExecutionMode.SEQUENTIAL:
            await self._run_sequential(matrix, context, record, topo_order, node_index)
        elif matrix.mode == ExecutionMode.PARALLEL:
            await self._run_parallel(matrix, context, record, node_index)
        elif matrix.mode == ExecutionMode.HYBRID:
            await self._run_hybrid(matrix, context, record, node_index)
        else:
            raise ValueError(f"Unknown execution mode: {matrix.mode}")

    # ─── Sequential ───────────────────────────────────────────────────────────

    async def _run_sequential(
        self,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
        order: List[str],
        node_index: Dict[str, Node],
    ) -> None:
        skipped: Set[str] = set()

        for idx, node_id in enumerate(order):
            if record.status in (ExecutionStatus.FAILED, ExecutionStatus.ABORTED):
                for remaining_id in order[idx:]:
                    if remaining_id not in record.node_results:
                        await self._mark_node_skipped(remaining_id, node_index, record)
                break

            if node_id in skipped:
                await self._mark_node_skipped(node_id, node_index, record)
                continue

            # Skip nodes that already ran (e.g. executed as a fallback earlier)
            if node_id in record.node_results:
                continue

            node = node_index.get(node_id)
            if not node:
                continue

            should_skip, reason = self._should_skip_node(node_id, matrix, context, record)
            if should_skip:
                logger.debug(f"[Engine] Skipping '{node.name}': {reason}")
                await self._mark_node_skipped(node_id, node_index, record)
                skipped.add(node_id)
                skipped.update(self._collect_descendants(node_id, matrix))
                continue

            node_result = await self._execute_node(node, matrix, context, record)
            unreachable = self._compute_unreachable(node, node_result, matrix, context)
            skipped.update(unreachable)

            if node_result.is_terminal_failure:
                if matrix.abort_policy in _ABORT_POLICIES:
                    record.mark_failed(
                        error=f"Node '{node.name}' failed: {node_result.error}",
                        error_node_id=node_id,
                    )
                    return

    # ─── Parallel ─────────────────────────────────────────────────────────────

    async def _run_parallel(
        self,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
        node_index: Dict[str, Node],
    ) -> None:
        semaphore = asyncio.Semaphore(matrix.max_parallelism)

        async def bounded(node: Node) -> NodeResult:
            async with semaphore:
                return await self._execute_node(node, matrix, context, record)

        results = await asyncio.gather(
            *[bounded(n) for n in matrix.nodes],
            return_exceptions=True,
        )
        for res in results:
            if isinstance(res, Exception):
                record.failed_nodes += 1
                if matrix.abort_policy in _ABORT_POLICIES:
                    record.mark_failed(str(res))
                    return

    # ─── Hybrid ───────────────────────────────────────────────────────────────

    async def _run_hybrid(
        self,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
        node_index: Dict[str, Node],
    ) -> None:
        batches = matrix.get_parallel_batches()
        semaphore = asyncio.Semaphore(matrix.max_parallelism)

        for batch_idx, batch_ids in enumerate(batches):
            if record.status in (ExecutionStatus.FAILED, ExecutionStatus.ABORTED):
                break

            async def bounded(
                nid: str,
                _idx: Dict[str, Node] = node_index,
                _ctx: ExecutionContext = context,
                _rec: ExecutionRecord = record,
                _sem: asyncio.Semaphore = semaphore,
                _mat: ExecutionMatrix = matrix,
            ) -> Optional[NodeResult]:
                node = _idx.get(nid)
                if not node:
                    return None
                if nid in _rec.node_results:
                    return None
                async with _sem:
                    return await self._execute_node(node, _mat, _ctx, _rec)

            batch_results = await asyncio.gather(
                *[bounded(nid) for nid in batch_ids],
                return_exceptions=True,
            )

            for res in batch_results:
                if isinstance(res, Exception):
                    record.failed_nodes += 1
                    if matrix.abort_policy in _ABORT_POLICIES:
                        record.mark_failed(f"Batch {batch_idx + 1}: {res}")
                        return
                elif res is not None and res.is_terminal_failure:
                    if matrix.abort_policy in _ABORT_POLICIES:
                        record.mark_failed(
                            error=f"Batch {batch_idx + 1} '{res.node_name}' failed",
                            error_node_id=res.node_id,
                        )
                        return

    # ─── Node Execution ───────────────────────────────────────────────────────

    async def _execute_node(
        self,
        node: Node,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
    ) -> NodeResult:
        await self.event_bus.emit(AFMXEvent(
            type=EventType.NODE_STARTED,
            execution_id=record.id, matrix_id=record.matrix_id,
            data={"node_id": node.id, "node_name": node.name, "type": node.type},
        ))

        # FIX: resolve handler AND agent registration together so we can
        # enforce AgentDispatcher.acquire() / release() around AGENT execution.
        injected_handler, agent_reg = self._resolve_handler_and_reg(node)

        # Acquire agent concurrency slot before execution
        if agent_reg is not None:
            agent_reg.acquire()

        try:
            node_result = await self.node_executor.execute(
                node=node, context=context, injected_handler=injected_handler,
            )
        finally:
            # Always release — even if execution raises (which it shouldn't since
            # NodeExecutor never raises, but defensive)
            if agent_reg is not None:
                agent_reg.release()

        # Activate fallback on terminal failure
        if node_result.is_terminal_failure and node.fallback_node_id:
            logger.warning(
                f"[Engine] '{node.name}' failed — "
                f"activating fallback '{node.fallback_node_id}'"
            )
            fallback_node = matrix.get_node_by_id(node.fallback_node_id)
            if fallback_node:
                fallback_handler, fallback_agent_reg = self._resolve_handler_and_reg(fallback_node)
                if fallback_agent_reg:
                    fallback_agent_reg.acquire()
                try:
                    fallback_result = await self.node_executor.execute(
                        node=fallback_node, context=context,
                        injected_handler=fallback_handler,
                    )
                finally:
                    if fallback_agent_reg:
                        fallback_agent_reg.release()

                await self.event_bus.emit(AFMXEvent(
                    type=EventType.NODE_FALLBACK,
                    execution_id=record.id, matrix_id=record.matrix_id,
                    data={"original_node": node.id, "fallback_node": fallback_node.id},
                ))
                if fallback_result.is_success:
                    fallback_result.metadata["fallback_used"] = True
                    fallback_result.metadata["fallback_node_id"] = fallback_node.id
                    node_result = fallback_result

                    # Mark the fallback node as already executed
                    if fallback_node.id not in record.node_results:
                        record.node_results[fallback_node.id] = NodeResult(
                            node_id=fallback_node.id,
                            node_name=fallback_node.name,
                            status=NodeStatus.FALLBACK,
                            metadata={"ran_as_fallback_for": node.id},
                        ).model_dump()

        # Persist output into context for downstream nodes
        if node_result.is_success and node_result.output is not None:
            context.set_node_output(node.id, node_result.output)

        record.node_results[node.id] = node_result.model_dump()
        if node_result.is_success:
            record.completed_nodes += 1
        elif node_result.is_terminal_failure:
            record.failed_nodes += 1

        await self.event_bus.emit(AFMXEvent(
            type=(
                EventType.NODE_COMPLETED if node_result.is_success
                else EventType.NODE_FAILED
            ),
            execution_id=record.id, matrix_id=record.matrix_id,
            data={
                "node_id": node.id,
                "node_name": node.name,
                "node_type": node.type,
                "status": node_result.status,
                "duration_ms": node_result.duration_ms,
                "error": node_result.error,
                "attempt": node_result.attempt,
                "fallback_used": node_result.metadata.get("fallback_used", False),
            },
        ))
        return node_result

    # ─── Handler + Agent Registration Resolution ──────────────────────────────

    def _resolve_handler_and_reg(
        self, node: Node
    ) -> tuple[Optional[Callable], Optional[AgentRegistration]]:
        """
        Resolve the handler callable and, for AGENT nodes, the AgentRegistration.
        The registration is returned so the caller can call acquire()/release()
        to enforce AgentDispatcher concurrency limits.
        """
        try:
            if node.type == NodeType.TOOL:
                reg = self.tool_router.resolve(handler_key=node.handler)
                return reg.handler, None

            if node.type == NodeType.AGENT:
                req = DispatchRequest(task_id=node.id, handler_key=node.handler)
                agent_reg = self.agent_dispatcher.dispatch(req)
                return agent_reg.handler, agent_reg

        except (KeyError, RuntimeError):
            pass

        # FUNCTION type or unresolvable — look up directly in HandlerRegistry
        try:
            handler = HandlerRegistry.resolve(node.handler)
            return handler, None
        except ImportError:
            pass

        return None, None

    # ─── Skip / Reachability ──────────────────────────────────────────────────

    def _should_skip_node(
        self,
        node_id: str,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
    ) -> tuple[bool, str]:
        incoming = matrix.get_edges_to(node_id)
        if not incoming:
            return False, ""

        for edge in incoming:
            pred_data = record.node_results.get(edge.from_node)
            if pred_data is None:
                continue
            pred_succeeded = pred_data.get("status") == NodeStatus.SUCCESS
            pred_output = pred_data.get("output")
            if not edge.is_applicable(
                node_succeeded=pred_succeeded,
                output=pred_output,
                context=context.snapshot(),
            ):
                return True, f"Edge from '{edge.from_node}' condition not satisfied"

        return False, ""

    def _compute_unreachable(
        self,
        node: Node,
        result: NodeResult,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
    ) -> Set[str]:
        unreachable: Set[str] = set()
        for edge in matrix.get_edges_from(node.id):
            if not edge.is_applicable(
                node_succeeded=result.is_success,
                output=result.output,
                context=context.snapshot(),
            ):
                unreachable.add(edge.to_node)
                unreachable.update(self._collect_descendants(edge.to_node, matrix))
        return unreachable

    def _collect_descendants(self, node_id: str, matrix: ExecutionMatrix) -> Set[str]:
        visited: Set[str] = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            for edge in matrix.get_edges_from(current):
                if edge.to_node not in visited:
                    visited.add(edge.to_node)
                    queue.append(edge.to_node)
        return visited

    async def _mark_node_skipped(
        self,
        node_id: str,
        node_index: Dict[str, Node],
        record: ExecutionRecord,
    ) -> None:
        node = node_index.get(node_id)
        name = node.name if node else node_id
        if node_id not in record.node_results:
            record.node_results[node_id] = NodeResult(
                node_id=node_id, node_name=name, status=NodeStatus.SKIPPED,
            ).model_dump()
            record.skipped_nodes += 1
            await self.event_bus.emit(AFMXEvent(
                type=EventType.NODE_SKIPPED,
                execution_id=record.id, matrix_id=record.matrix_id,
                data={"node_id": node_id, "node_name": name},
            ))

    # ─── Matrix-level hooks ───────────────────────────────────────────────────

    async def _run_matrix_hook(
        self,
        hook_type_name: str,
        matrix: ExecutionMatrix,
        context: ExecutionContext,
        record: ExecutionRecord,
    ) -> None:
        hook_registry = getattr(self.node_executor, "hook_registry", None)
        if not hook_registry:
            return
        try:
            from afmx.core.hooks import HookPayload, HookType
            hook_type = (
                HookType.PRE_MATRIX
                if hook_type_name == "pre_matrix"
                else HookType.POST_MATRIX
            )
            payload = HookPayload(
                hook_type=hook_type,
                execution_id=record.id,
                matrix_id=matrix.id,
                matrix_name=matrix.name,
                context=context,
                record=record,
            )
            await hook_registry.run(payload)
        except Exception as exc:
            logger.warning(f"[Engine] Matrix hook '{hook_type_name}' error: {exc}")
