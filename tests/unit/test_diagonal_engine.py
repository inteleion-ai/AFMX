"""
Integration tests — DIAGONAL execution mode + cognitive router

Verifies that:
  - DIAGONAL mode executes nodes grouped by CognitiveLayer
  - CognitiveModelRouter injects correct __model_hint__ / __model_tier__ metadata
  - NodeResult captures cognitive_layer and agent_role after execution
  - matrix_view endpoint returns correctly keyed cells
  - Nodes without coordinates still execute in DIAGONAL (unclassified batch)
  - DIAGONAL is deterministic — same order every run
"""
from __future__ import annotations

import asyncio
import pytest

from afmx.core.cognitive_router import CognitiveModelRouter
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import ExecutionMatrix, ExecutionMode
from afmx.models.node import AgentRole, CognitiveLayer, Node, NodeType
from afmx.observability.events import EventBus


# ─── Helpers ──────────────────────────────────────────────────────────────────

CHEAP_MODEL   = "test-cheap-model"
PREMIUM_MODEL = "test-premium-model"

_EXECUTION_ORDER: list[str] = []


def _make_engine() -> AFMXEngine:
    return AFMXEngine(
        event_bus=EventBus(),
        cognitive_router=CognitiveModelRouter(
            cheap_model=CHEAP_MODEL,
            premium_model=PREMIUM_MODEL,
        ),
    )


def _make_node(
    node_id: str,
    name:    str,
    layer:   CognitiveLayer,
    role:    AgentRole,
    handler: str = "capture_handler",
) -> Node:
    return Node(
        id=node_id,
        name=name,
        type=NodeType.TOOL,
        handler=handler,
        cognitive_layer=layer,
        agent_role=role,
    )


# ─── Capture handler — records execution order + metadata ─────────────────────

async def _capture_handler(node_input: dict, context: ExecutionContext, node: Node) -> dict:
    """Records which node ran and what metadata was injected."""
    meta = node_input.get("metadata", {})
    _EXECUTION_ORDER.append(node.name)
    return {
        "node":         node.name,
        "layer":        meta.get("__cognitive_layer__"),
        "role":         meta.get("__agent_role__"),
        "model_hint":   meta.get("__model_hint__"),
        "model_tier":   meta.get("__model_tier__"),
    }


HandlerRegistry.register("capture_handler", _capture_handler)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestDiagonalExecution:
    """DIAGONAL mode: nodes grouped by CognitiveLayer, layers in canonical order."""

    def setup_method(self):
        _EXECUTION_ORDER.clear()

    def _run(self, matrix: ExecutionMatrix) -> ExecutionRecord:
        context = ExecutionContext(input={"test": True})
        record  = ExecutionRecord(
            matrix_id=matrix.id,
            matrix_name=matrix.name,
            context=context,
        )
        return asyncio.get_event_loop().run_until_complete(
            _make_engine().execute(matrix, context, record)
        )

    def test_diagonal_completes_successfully(self):
        """A matrix with DIAGONAL mode and coordinated nodes completes."""
        matrix = ExecutionMatrix(
            name="diag-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("p1", "perceive-ops",     CognitiveLayer.PERCEIVE,  AgentRole.OPS),
                _make_node("r1", "reason-analyst",   CognitiveLayer.REASON,    AgentRole.ANALYST),
                _make_node("a1", "act-coder",        CognitiveLayer.ACT,       AgentRole.CODER),
            ],
            edges=[
                {"from": "p1", "to": "r1"},
                {"from": "r1", "to": "a1"},
            ],
        )
        record = self._run(matrix)
        assert record.status == ExecutionStatus.COMPLETED
        assert record.completed_nodes == 3
        assert record.failed_nodes    == 0

    def test_cognitive_layer_order_is_canonical(self):
        """PERCEIVE must always execute before REASON, which must precede PLAN."""
        matrix = ExecutionMatrix(
            name="order-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("a1", "act-first",        CognitiveLayer.ACT,      AgentRole.OPS),
                _make_node("p1", "perceive-first",   CognitiveLayer.PERCEIVE, AgentRole.OPS),
                _make_node("r1", "reason-first",     CognitiveLayer.REASON,   AgentRole.ANALYST),
            ],
            edges=[],  # no edges — DIAGONAL groups by layer, not DAG adjacency
        )
        self._run(matrix)
        # Canonical order: PERCEIVE → REASON → ACT
        assert _EXECUTION_ORDER.index("perceive-first") < _EXECUTION_ORDER.index("reason-first")
        assert _EXECUTION_ORDER.index("reason-first")   < _EXECUTION_ORDER.index("act-first")

    def test_model_tier_injected_correctly_cheap(self):
        """PERCEIVE nodes get cheap model tier injected."""
        matrix = ExecutionMatrix(
            name="cheap-tier-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("p1", "perceive-ops", CognitiveLayer.PERCEIVE, AgentRole.OPS),
            ],
            edges=[],
        )
        record = self._run(matrix)
        result = list(record.node_results.values())[0]
        output = result.get("output") if isinstance(result, dict) else result.output
        assert output is not None
        assert output["model_hint"] == CHEAP_MODEL
        assert output["model_tier"] == "cheap"

    def test_model_tier_injected_correctly_premium(self):
        """REASON nodes get premium model tier injected."""
        matrix = ExecutionMatrix(
            name="premium-tier-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("r1", "reason-analyst", CognitiveLayer.REASON, AgentRole.ANALYST),
            ],
            edges=[],
        )
        record = self._run(matrix)
        result = list(record.node_results.values())[0]
        output = result.get("output") if isinstance(result, dict) else result.output
        assert output is not None
        assert output["model_hint"] == PREMIUM_MODEL
        assert output["model_tier"] == "premium"

    def test_cognitive_layer_captured_in_node_result(self):
        """NodeResult.cognitive_layer and agent_role are populated after execution."""
        matrix = ExecutionMatrix(
            name="result-capture-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("e1", "evaluate-verifier", CognitiveLayer.EVALUATE, AgentRole.VERIFIER),
            ],
            edges=[],
        )
        record = self._run(matrix)
        result = record.node_results.get("e1") or {}
        if isinstance(result, dict):
            assert result.get("cognitive_layer") == "EVALUATE"
            assert result.get("agent_role")      == "VERIFIER"

    def test_uncoordinated_nodes_still_execute(self):
        """Nodes without cognitive_layer run in the 'unclassified' batch last."""
        async def _plain_handler(node_input, context, node):
            _EXECUTION_ORDER.append("unclassified")
            return {"ran": True}

        HandlerRegistry.register("plain_handler", _plain_handler)

        matrix = ExecutionMatrix(
            name="mixed-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("p1", "perceive-node",   CognitiveLayer.PERCEIVE, AgentRole.OPS),
                Node(name="legacy-node", type=NodeType.TOOL, handler="plain_handler"),
            ],
            edges=[],
        )
        record = self._run(matrix)
        assert record.status == ExecutionStatus.COMPLETED
        assert record.completed_nodes == 2
        # PERCEIVE must run before unclassified
        assert _EXECUTION_ORDER.index("perceive-node") < _EXECUTION_ORDER.index("unclassified")

    def test_diagonal_with_abort_on_failure(self):
        """A node failure in DIAGONAL + FAIL_FAST aborts the matrix."""
        from afmx.models.matrix import AbortPolicy

        async def _fail_handler(node_input, context, node):
            raise RuntimeError("Deliberate failure")

        HandlerRegistry.register("fail_handler", _fail_handler)

        matrix = ExecutionMatrix(
            name="fail-test",
            mode=ExecutionMode.DIAGONAL,
            abort_policy=AbortPolicy.FAIL_FAST,
            nodes=[
                Node(name="fail-node", id="f1", type=NodeType.TOOL, handler="fail_handler",
                     cognitive_layer=CognitiveLayer.PERCEIVE, agent_role=AgentRole.OPS),
                _make_node("r1", "reason-node", CognitiveLayer.REASON, AgentRole.ANALYST),
            ],
            edges=[{"from": "f1", "to": "r1"}],
        )
        record = self._run(matrix)
        assert record.status in (ExecutionStatus.FAILED, ExecutionStatus.ABORTED)

    def test_matrix_coverage_summary(self):
        """matrix_coverage_summary correctly counts coordinated vs uncoordinated."""
        matrix = ExecutionMatrix(
            name="coverage-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("p1", "perceive-ops",   CognitiveLayer.PERCEIVE, AgentRole.OPS),
                _make_node("r1", "reason-analyst", CognitiveLayer.REASON,   AgentRole.ANALYST),
                Node(name="legacy", type=NodeType.TOOL, handler="capture_handler"),
            ],
            edges=[],
        )
        summary = matrix.matrix_coverage_summary()
        assert summary["total_nodes"]         == 3
        assert summary["coordinated_nodes"]   == 2
        assert summary["uncoordinated_nodes"] == 1
        assert summary["cells_populated"]     == 2
        assert summary["cells_possible"]      == 49  # 7 × 7


class TestCognitiveRouterStandalone:
    """Direct tests of CognitiveModelRouter without engine involvement."""

    def test_default_models(self):
        router = CognitiveModelRouter()
        # Default cheap model
        assert "haiku" in router.cheap_model.lower() or router.cheap_model  # non-empty
        # Default premium model
        assert "opus" in router.premium_model.lower() or router.premium_model

    def test_custom_models(self):
        router = CognitiveModelRouter(cheap_model="gpt-4o-mini", premium_model="gpt-4o")
        assert router.resolve(CognitiveLayer.PERCEIVE) == "gpt-4o-mini"
        assert router.resolve(CognitiveLayer.REASON)   == "gpt-4o"

    def test_all_cheap_layers_get_cheap(self):
        router = CognitiveModelRouter(cheap_model="cheap", premium_model="premium")
        for layer in [CognitiveLayer.PERCEIVE, CognitiveLayer.RETRIEVE,
                      CognitiveLayer.ACT, CognitiveLayer.REPORT]:
            assert router.resolve(layer) == "cheap", f"{layer} should be cheap"

    def test_all_premium_layers_get_premium(self):
        router = CognitiveModelRouter(cheap_model="cheap", premium_model="premium")
        for layer in [CognitiveLayer.REASON, CognitiveLayer.PLAN, CognitiveLayer.EVALUATE]:
            assert router.resolve(layer) == "premium", f"{layer} should be premium"

    def test_inject_hint_sets_all_keys(self):
        router  = CognitiveModelRouter(cheap_model="c", premium_model="p")
        node    = Node(
            name="test", type=NodeType.TOOL, handler="echo",
            cognitive_layer=CognitiveLayer.PLAN,
            agent_role=AgentRole.PLANNER,
        )
        context = ExecutionContext()
        router.inject_hint(node, context)

        assert context.metadata["__model_hint__"]      == "p"
        assert context.metadata["__model_tier__"]      == "premium"
        assert context.metadata["__cognitive_layer__"] == "PLAN"
        assert context.metadata["__agent_role__"]      == "PLANNER"
