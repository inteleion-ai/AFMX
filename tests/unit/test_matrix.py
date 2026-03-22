"""
Unit tests for ExecutionMatrix — topology, validation, batching
"""
import pytest
from pydantic import ValidationError
from afmx.models.node import Node, NodeType
from afmx.models.edge import Edge
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy


def make_node(name: str, nid: str = None) -> Node:
    return Node(
        id=nid or name,
        name=name,
        type=NodeType.TOOL,
        handler=f"handler_{name}",
    )


def make_edge(from_id: str, to_id: str) -> Edge:
    return Edge(**{"from": from_id, "to": to_id})


class TestExecutionMatrix:
    def test_single_node_matrix(self):
        n = make_node("only", "only")
        m = ExecutionMatrix(nodes=[n], edges=[])
        assert len(m.nodes) == 1
        order = m.topological_order()
        assert order == ["only"]

    def test_linear_chain(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        n3 = make_node("c", "c")
        m = ExecutionMatrix(
            nodes=[n1, n2, n3],
            edges=[make_edge("a", "b"), make_edge("b", "c")],
        )
        order = m.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_fan_out(self):
        root = make_node("root", "root")
        left = make_node("left", "left")
        right = make_node("right", "right")
        m = ExecutionMatrix(
            nodes=[root, left, right],
            edges=[make_edge("root", "left"), make_edge("root", "right")],
        )
        order = m.topological_order()
        assert order.index("root") < order.index("left")
        assert order.index("root") < order.index("right")

    def test_cycle_raises(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        m = ExecutionMatrix(
            nodes=[n1, n2],
            edges=[make_edge("a", "b"), make_edge("b", "a")],
        )
        with pytest.raises(ValueError, match="Cycle detected"):
            m.topological_order()

    def test_invalid_edge_ref_raises(self):
        n1 = make_node("a", "a")
        with pytest.raises(ValidationError):
            ExecutionMatrix(
                nodes=[n1],
                edges=[make_edge("a", "nonexistent")],
            )

    def test_invalid_entry_node_raises(self):
        n1 = make_node("a", "a")
        with pytest.raises(ValidationError):
            ExecutionMatrix(
                nodes=[n1],
                entry_node_id="ghost",
            )

    def test_invalid_fallback_node_raises(self):
        n1 = make_node("a", "a")
        n1.fallback_node_id = "ghost"
        with pytest.raises(ValidationError):
            ExecutionMatrix(nodes=[n1])

    def test_get_entry_nodes_no_edges(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        m = ExecutionMatrix(nodes=[n1, n2], edges=[])
        entries = m.get_entry_nodes()
        assert len(entries) == 2

    def test_get_entry_nodes_with_edges(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        m = ExecutionMatrix(nodes=[n1, n2], edges=[make_edge("a", "b")])
        entries = m.get_entry_nodes()
        assert len(entries) == 1
        assert entries[0].id == "a"

    def test_parallel_batches_linear(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        n3 = make_node("c", "c")
        m = ExecutionMatrix(
            nodes=[n1, n2, n3],
            edges=[make_edge("a", "b"), make_edge("b", "c")],
        )
        batches = m.get_parallel_batches()
        assert len(batches) == 3
        assert "a" in batches[0]
        assert "b" in batches[1]
        assert "c" in batches[2]

    def test_parallel_batches_fan_out(self):
        root = make_node("root", "root")
        left = make_node("left", "left")
        right = make_node("right", "right")
        m = ExecutionMatrix(
            nodes=[root, left, right],
            edges=[make_edge("root", "left"), make_edge("root", "right")],
        )
        batches = m.get_parallel_batches()
        assert "root" in batches[0]
        assert "left" in batches[1]
        assert "right" in batches[1]

    def test_get_edges_from(self):
        n1 = make_node("a", "a")
        n2 = make_node("b", "b")
        m = ExecutionMatrix(nodes=[n1, n2], edges=[make_edge("a", "b")])
        edges = m.get_edges_from("a")
        assert len(edges) == 1
        assert edges[0].to_node == "b"

    def test_get_node_by_id(self):
        n = make_node("x", "node-x")
        m = ExecutionMatrix(nodes=[n])
        found = m.get_node_by_id("node-x")
        assert found is not None
        assert found.name == "x"
        assert m.get_node_by_id("missing") is None
