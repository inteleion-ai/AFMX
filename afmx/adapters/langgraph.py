"""
AFMX LangGraph Bridge Adapter
Translates a compiled LangGraph StateGraph into an AFMX ExecutionMatrix.

Philosophy (founder note):
    LangGraph = how agents THINK  (reasoning, state machine, LLM decisions)
    AFMX      = how agents ACT   (deterministic execution, retry, fallback)

    The bridge runs the LangGraph reasoning layer INSIDE AFMX execution nodes,
    so every step gets AFMX's retry, timeout, fallback, and circuit breaker —
    without changing a single line of LangGraph code.

Translation:
    LangGraph node  →  AFMX FUNCTION node  (handler = afmx wrapper)
    LangGraph edge  →  AFMX Edge           (condition = edge type)
    LangGraph graph →  AFMX ExecutionMatrix (SEQUENTIAL by default)

Two integration modes:
    1. FULL BRIDGE  — translate the entire graph to a matrix.
       Best for graphs where AFMX should control execution order.

    2. SINGLE NODE  — wrap the full compiled graph as ONE AFMX node.
       Best when LangGraph controls its own routing and AFMX provides
       retry + timeout around the full invocation.

Usage:
    from afmx.adapters.langgraph import LangGraphAdapter

    adapter = LangGraphAdapter()

    # Mode 1: Full bridge — translate graph to matrix
    matrix = adapter.translate_graph(compiled_graph, input_schema={"query": str})

    # Mode 2: Single-node wrap — whole graph as one AFMX node
    node = adapter.to_afmx_node(compiled_graph, node_name="reasoning_graph")
    adapter.register_handler(compiled_graph)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from afmx.adapters.base import AFMXAdapter, AdapterResult
from afmx.core.executor import HandlerRegistry
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy
from afmx.models.node import Node, NodeType, RetryPolicy, TimeoutPolicy, NodeConfig

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "langgraph:"


def _require_langgraph() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        raise ImportError(
            "langgraph is required for LangGraphAdapter. "
            "Install: pip install langgraph"
        )


class LangGraphAdapter(AFMXAdapter):
    """
    AFMX adapter / bridge for LangGraph compiled graphs.

    Supports both single-node wrapping and full graph translation.
    """

    @property
    def name(self) -> str:
        return "langgraph"

    # ─── Mode 1: Full graph translation ───────────────────────────────────────

    def translate_graph(
        self,
        compiled_graph: Any,
        *,
        matrix_name: str = "langgraph-matrix",
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        abort_policy: AbortPolicy = AbortPolicy.FAIL_FAST,
        default_timeout: float = 30.0,
        default_retries: int = 2,
        global_timeout: float = 300.0,
    ) -> ExecutionMatrix:
        """
        Translate a compiled LangGraph StateGraph into an AFMX ExecutionMatrix.

        Each LangGraph node becomes an AFMX FUNCTION node.
        Each LangGraph edge becomes an AFMX Edge (with ON_SUCCESS condition).
        The AFMX engine then controls execution with retry/timeout/fallback.
        """
        _require_langgraph()

        nodes: List[Node] = []
        edges: List[Edge] = []

        # Extract graph structure from LangGraph compiled graph
        graph_nodes, graph_edges = self._extract_graph_structure(compiled_graph)

        # Build AFMX nodes
        node_registry: Dict[str, Any] = {}
        for lg_node_id, lg_node_runnable in graph_nodes.items():
            if lg_node_id in ("__start__", "__end__"):
                continue

            handler_key = f"{_HANDLER_PREFIX}{lg_node_id}"
            node_registry[lg_node_id] = handler_key

            # Register the LangGraph node's runnable as an AFMX handler
            lg_runnable = lg_node_runnable
            self._register_node_handler(handler_key, lg_runnable, compiled_graph)

            afmx_node = Node(
                id=lg_node_id,
                name=lg_node_id,
                type=NodeType.FUNCTION,
                handler=handler_key,
                config=NodeConfig(params={"node_id": lg_node_id}),
                retry_policy=RetryPolicy(
                    retries=default_retries,
                    backoff_seconds=0.5,
                    jitter=True,
                ),
                timeout_policy=TimeoutPolicy(timeout_seconds=default_timeout),
                metadata={"adapter": "langgraph", "langgraph_node_id": lg_node_id},
            )
            nodes.append(afmx_node)

        # Build AFMX edges
        for from_id, to_id, condition_type in graph_edges:
            # Skip virtual __start__ / __end__ nodes
            if from_id in ("__start__", "__end__"):
                continue
            if to_id in ("__start__", "__end__"):
                continue

            # Only add edge if both nodes exist in our AFMX node set
            node_ids = {n.id for n in nodes}
            if from_id not in node_ids or to_id not in node_ids:
                continue

            afmx_edge = Edge(
                **{
                    "from": from_id,
                    "to": to_id,
                    "condition": EdgeCondition(
                        type=EdgeConditionType.ON_SUCCESS
                        if condition_type == "normal"
                        else EdgeConditionType.ALWAYS
                    ),
                    "label": f"{from_id} → {to_id}",
                }
            )
            edges.append(afmx_edge)

        if not nodes:
            raise ValueError(
                "LangGraph translation produced 0 AFMX nodes. "
                "Ensure your compiled graph has named nodes other than __start__/__end__."
            )

        return ExecutionMatrix(
            name=matrix_name,
            mode=mode,
            nodes=nodes,
            edges=edges,
            abort_policy=abort_policy,
            global_timeout_seconds=global_timeout,
        )

    # ─── Mode 2: Single-node wrap ─────────────────────────────────────────────

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
        Wrap an entire compiled LangGraph graph as a single AFMX node.
        The full graph is invoked as one atomic unit — LangGraph controls
        its own internal routing; AFMX wraps it with retry + timeout.
        """
        resolved_name = node_name or "langgraph_graph"
        handler_key = f"{_HANDLER_PREFIX}{resolved_name}"
        self.register_handler(external_obj, handler_key=handler_key)

        return self._make_node(
            handler_key=handler_key,
            external_ref=external_obj,
            node_id=node_id,
            node_name=resolved_name,
            node_type=node_type,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config=extra_config,
        )

    def register_handler(
        self,
        external_obj: Any,
        handler_key: Optional[str] = None,
    ) -> str:
        """Register a LangGraph graph's invocation as an AFMX handler."""
        key = handler_key or f"{_HANDLER_PREFIX}graph"
        HandlerRegistry.register(key, self.make_handler(external_obj))
        return key

    # ─── Execution ────────────────────────────────────────────────────────────

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """Invoke a LangGraph graph or node with the AFMX node input."""
        _require_langgraph()
        raw_input = node_input.get("input")
        params = node_input.get("params", {})
        effective_input = {**(params if params else {}), "input": raw_input}

        try:
            import asyncio
            if hasattr(external_ref, "ainvoke"):
                output = await external_ref.ainvoke(effective_input)
            elif hasattr(external_ref, "invoke"):
                loop = asyncio.get_running_loop()
                output = await loop.run_in_executor(None, external_ref.invoke, effective_input)
            else:
                raise TypeError(
                    f"LangGraph object {type(external_ref).__name__} "
                    "has no ainvoke() or invoke() method"
                )
            return self.normalize(output)
        except Exception as exc:
            logger.error(f"[LangGraphAdapter] Execution error: {exc}", exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    def normalize(self, raw_output: Any) -> AdapterResult:
        """Normalise LangGraph state dict output."""
        if isinstance(raw_output, dict):
            # LangGraph returns full state — wrap it
            return AdapterResult.ok(output=raw_output)
        return AdapterResult.ok(output=raw_output)

    # ─── Graph structure extraction ───────────────────────────────────────────

    @staticmethod
    def _extract_graph_structure(
        compiled_graph: Any,
    ) -> tuple:
        """
        Extract nodes and edges from a compiled LangGraph StateGraph.

        Returns:
            nodes: Dict[node_id, runnable]
            edges: List[Tuple[from_id, to_id, edge_type]]
        """
        nodes: Dict[str, Any] = {}
        edges: List[tuple] = []

        # Try to access LangGraph's internal graph structure
        # LangGraph < 0.1  uses .graph attribute
        # LangGraph >= 0.1 uses .nodes and .edges via get_graph()
        try:
            if hasattr(compiled_graph, "nodes"):
                for node_id, node_obj in compiled_graph.nodes.items():
                    nodes[node_id] = node_obj

            elif hasattr(compiled_graph, "graph") and hasattr(compiled_graph.graph, "nodes"):
                for node_id, node_obj in compiled_graph.graph.nodes.items():
                    nodes[node_id] = node_obj

            # Extract edges
            graph_obj = getattr(compiled_graph, "graph", compiled_graph)
            if hasattr(graph_obj, "edges"):
                raw_edges = graph_obj.edges
                if hasattr(raw_edges, "items"):
                    for edge_key, edge_data in raw_edges.items():
                        from_id = getattr(edge_key, "start", None) or str(edge_key)
                        to_id = getattr(edge_data, "end", None) or str(edge_data)
                        edges.append((from_id, to_id, "normal"))
                elif hasattr(raw_edges, "__iter__"):
                    for edge in raw_edges:
                        if hasattr(edge, "start") and hasattr(edge, "end"):
                            edges.append((edge.start, edge.end, "normal"))
                        elif isinstance(edge, (tuple, list)) and len(edge) >= 2:
                            edges.append((str(edge[0]), str(edge[1]), "normal"))

        except Exception as exc:
            logger.warning(
                f"[LangGraphAdapter] Could not fully extract graph structure: {exc}. "
                "Nodes will be treated as independent — no edges created."
            )

        return nodes, edges

    def _register_node_handler(
        self,
        handler_key: str,
        node_runnable: Any,
        compiled_graph: Any,
    ) -> None:
        """
        Register an individual LangGraph node as an AFMX handler.
        Each node receives the current AFMX context input and returns
        the node's output state.
        """
        adapter = self
        graph = compiled_graph

        async def _node_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            # Build LangGraph-compatible state from AFMX input
            raw_in = node_input.get("input")
            memory = node_input.get("memory", {})
            state = {**(raw_in if isinstance(raw_in, dict) else {"input": raw_in})}
            state.update(memory)

            result = await adapter.execute(node_input={"input": state}, external_ref=node_runnable)
            if not result.success:
                raise RuntimeError(f"[LangGraph node] {result.error}")
            return result.output

        HandlerRegistry.register(handler_key, _node_handler)
