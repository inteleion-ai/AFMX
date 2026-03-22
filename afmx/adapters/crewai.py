"""
AFMX CrewAI Adapter
Wraps CrewAI agents and tasks for execution inside the AFMX runtime.

Mapping:
    CrewAI Agent  → AFMX AGENT node
    CrewAI Task   → AFMX FUNCTION node
    CrewAI Crew   → AFMX ExecutionMatrix (each task = one node)

The adapter does NOT import crewai at module level.
If crewai is not installed, to_afmx_node() / execute() raise a clear ImportError.

Usage:
    from afmx.adapters.crewai import CrewAIAdapter

    adapter = CrewAIAdapter()

    # Wrap a single task
    node = adapter.to_afmx_node(my_task, node_type=NodeType.FUNCTION)
    adapter.register_handler(my_task)

    # Translate an entire Crew to a matrix
    matrix = adapter.translate_crew(my_crew)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from afmx.adapters.base import AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.edge import Edge
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode
from afmx.models.node import Node, NodeConfig, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "crewai:"


def _require_crewai() -> None:
    try:
        import crewai  # noqa: F401
    except ImportError:
        raise ImportError(
            "crewai is required for CrewAIAdapter. "
            "Install: pip install crewai"
        )


class CrewAIAdapter(AFMXAdapter):
    """
    AFMX adapter for CrewAI agents and tasks.

    Supports:
    - Individual Agent  (wrapped as AFMX AGENT node)
    - Individual Task   (wrapped as AFMX FUNCTION node)
    - Full Crew         (translated to AFMX ExecutionMatrix)
    """

    @property
    def name(self) -> str:
        return "crewai"

    # ─── Single task/agent node ───────────────────────────────────────────────

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
        """Convert a CrewAI Agent or Task to an AFMX Node."""
        _require_crewai()
        resolved_type = node_type or self._detect_node_type(external_obj)
        handler_key = self._handler_key(external_obj)
        self.register_handler(external_obj)

        return self._make_node(
            handler_key=handler_key,
            external_ref=external_obj,
            node_id=node_id,
            node_name=node_name or self._obj_name(external_obj),
            node_type=resolved_type,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config=extra_config,
        )

    def register_handler(
        self,
        external_obj: Any,
        handler_key: Optional[str] = None,
    ) -> str:
        """Register a CrewAI object as an AFMX handler."""
        key = handler_key or self._handler_key(external_obj)
        HandlerRegistry.register(key, self.make_handler(external_obj))
        return key

    # ─── Full Crew translation ────────────────────────────────────────────────

    def translate_crew(
        self,
        crew: Any,
        *,
        matrix_name: str = "crewai-matrix",
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        abort_policy: AbortPolicy = AbortPolicy.FAIL_FAST,
        default_timeout: float = 120.0,
        default_retries: int = 1,
        global_timeout: float = 600.0,
    ) -> ExecutionMatrix:
        """
        Translate a CrewAI Crew into an AFMX ExecutionMatrix.

        Each task in the crew becomes a separate AFMX node.
        Sequential process → SEQUENTIAL mode.
        Hierarchical process → HYBRID mode.
        """
        _require_crewai()

        tasks = getattr(crew, "tasks", [])
        if not tasks:
            raise ValueError("Crew has no tasks to translate.")

        nodes: List[Node] = []
        edges: List[Edge] = []
        prev_id: Optional[str] = None

        for task in tasks:
            task_id = str(uuid.uuid4())[:8]
            task_name = self._task_name(task)
            handler_key = f"{_HANDLER_PREFIX}task:{task_name}"

            # Register task execution as an AFMX handler
            self._register_task_handler(handler_key, task)

            # Identify the agent assigned to this task
            assigned_agent = getattr(task, "agent", None)
            agent_name = self._obj_name(assigned_agent) if assigned_agent else "unassigned"

            node = Node(
                id=task_id,
                name=task_name,
                type=NodeType.FUNCTION,
                handler=handler_key,
                config=NodeConfig(params={
                    "task_name": task_name,
                    "agent": agent_name,
                }),
                retry_policy=RetryPolicy(
                    retries=default_retries,
                    backoff_seconds=1.0,
                    jitter=True,
                ),
                timeout_policy=TimeoutPolicy(timeout_seconds=default_timeout),
                metadata={
                    "adapter": "crewai",
                    "task_description": getattr(task, "description", ""),
                    "expected_output": getattr(task, "expected_output", ""),
                    "agent": agent_name,
                },
            )
            nodes.append(node)

            # Sequential tasks: chain with ON_SUCCESS edges
            if prev_id and mode == ExecutionMode.SEQUENTIAL:
                edges.append(Edge(**{"from": prev_id, "to": task_id}))
            prev_id = task_id

        # Detect process type for mode override
        process = getattr(crew, "process", None)
        process_name = getattr(process, "value", str(process)) if process else "sequential"
        if "hierarchical" in str(process_name).lower():
            mode = ExecutionMode.HYBRID

        return ExecutionMatrix(
            name=matrix_name,
            mode=mode,
            nodes=nodes,
            edges=edges,
            abort_policy=abort_policy,
            global_timeout_seconds=global_timeout,
        )

    # ─── Execution ────────────────────────────────────────────────────────────

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """Execute a CrewAI Agent or Task."""
        _require_crewai()
        raw_input = node_input.get("input")
        params = node_input.get("params", {})

        try:
            import asyncio
            import inspect

            effective_input = params.get("task_input") or raw_input

            # Task execution
            if hasattr(external_ref, "execute") or hasattr(external_ref, "_execute"):
                execute_fn = getattr(
                    external_ref, "execute_sync",
                    getattr(external_ref, "execute", None),
                )
                if execute_fn:
                    if inspect.iscoroutinefunction(execute_fn):
                        output = await execute_fn(effective_input)
                    else:
                        loop = asyncio.get_running_loop()
                        output = await loop.run_in_executor(
                            None, execute_fn, effective_input
                        )
                    return self.normalize(output)

            # Agent execution via kickoff
            if hasattr(external_ref, "kickoff"):
                kickoff = external_ref.kickoff
                if inspect.iscoroutinefunction(kickoff):
                    output = await kickoff(inputs={"input": effective_input})
                else:
                    loop = asyncio.get_running_loop()
                    output = await loop.run_in_executor(
                        None, kickoff, {"input": effective_input}
                    )
                return self.normalize(output)

            # Generic callable
            if callable(external_ref):
                if inspect.iscoroutinefunction(external_ref):
                    output = await external_ref(effective_input)
                else:
                    loop = asyncio.get_running_loop()
                    output = await loop.run_in_executor(None, external_ref, effective_input)
                return self.normalize(output)

            raise TypeError(
                f"CrewAI object {type(external_ref).__name__} "
                "has no known execution interface"
            )

        except Exception as exc:
            logger.error(f"[CrewAIAdapter] Execution error: {exc}", exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    def normalize(self, raw_output: Any) -> AdapterResult:
        """Normalise CrewAI output."""
        if isinstance(raw_output, str):
            return AdapterResult.ok(output={"result": raw_output})
        return AdapterResult.ok(output=raw_output)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _register_task_handler(self, handler_key: str, task: Any) -> None:
        """Register a single CrewAI task as an AFMX handler."""
        adapter = self

        async def _task_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await adapter.execute(node_input=node_input, external_ref=task)
            if not result.success:
                raise RuntimeError(f"[CrewAI task] {result.error}")
            return result.output

        HandlerRegistry.register(handler_key, _task_handler)

    @staticmethod
    def _detect_node_type(obj: Any) -> NodeType:
        class_name = type(obj).__name__.lower()
        if "agent" in class_name:
            return NodeType.AGENT
        return NodeType.FUNCTION

    @staticmethod
    def _obj_name(obj: Any) -> str:
        if obj is None:
            return "unnamed"
        for attr in ("role", "name", "description"):
            val = getattr(obj, attr, None)
            if val and isinstance(val, str):
                return val[:64].replace(" ", "_").lower()
        return type(obj).__name__.lower()

    @staticmethod
    def _task_name(task: Any) -> str:
        desc = getattr(task, "description", None)
        if desc:
            return desc[:40].replace(" ", "_").lower().rstrip("_")
        return f"task_{id(task) % 10000}"

    @staticmethod
    def _handler_key(obj: Any) -> str:
        class_name = type(obj).__name__.lower()
        obj_name = CrewAIAdapter._obj_name(obj)
        return f"{_HANDLER_PREFIX}{class_name}:{obj_name}"
