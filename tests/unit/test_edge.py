"""
Unit tests for Edge model and condition evaluation
"""
import pytest
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType


class TestEdge:
    def _make_edge(self, condition_type=EdgeConditionType.ALWAYS, **kwargs):
        condition = EdgeCondition(type=condition_type, **kwargs)
        return Edge(**{"from": "a", "to": "b", "condition": condition})

    def test_edge_always_applies(self):
        edge = self._make_edge(EdgeConditionType.ALWAYS)
        assert edge.is_applicable(True) is True
        assert edge.is_applicable(False) is True

    def test_edge_on_success(self):
        edge = self._make_edge(EdgeConditionType.ON_SUCCESS)
        assert edge.is_applicable(True) is True
        assert edge.is_applicable(False) is False

    def test_edge_on_failure(self):
        edge = self._make_edge(EdgeConditionType.ON_FAILURE)
        assert edge.is_applicable(True) is False
        assert edge.is_applicable(False) is True

    def test_edge_on_output_exact_match(self):
        edge = self._make_edge(
            EdgeConditionType.ON_OUTPUT,
            output_key="status",
            output_value="active",
        )
        assert edge.is_applicable(True, output={"status": "active"}) is True
        assert edge.is_applicable(True, output={"status": "inactive"}) is False

    def test_edge_on_output_nested_key(self):
        edge = self._make_edge(
            EdgeConditionType.ON_OUTPUT,
            output_key="user.role",
            output_value="admin",
        )
        output = {"user": {"role": "admin"}}
        assert edge.is_applicable(True, output=output) is True
        output2 = {"user": {"role": "guest"}}
        assert edge.is_applicable(True, output=output2) is False

    def test_edge_on_output_missing_key_returns_false(self):
        edge = self._make_edge(
            EdgeConditionType.ON_OUTPUT,
            output_key="nonexistent.key",
            output_value="val",
        )
        assert edge.is_applicable(True, output={"other": "data"}) is False

    def test_edge_expression_true(self):
        edge = self._make_edge(
            EdgeConditionType.EXPRESSION,
            expression="output['score'] > 0.5",
        )
        assert edge.is_applicable(True, output={"score": 0.9}) is True
        assert edge.is_applicable(True, output={"score": 0.2}) is False

    def test_edge_expression_context(self):
        edge = self._make_edge(
            EdgeConditionType.EXPRESSION,
            expression="context['retry_count'] < 3",
        )
        assert edge.is_applicable(True, context={"retry_count": 2}) is True
        assert edge.is_applicable(True, context={"retry_count": 5}) is False

    def test_edge_expression_invalid_is_false(self):
        edge = self._make_edge(
            EdgeConditionType.EXPRESSION,
            expression="this is not python",
        )
        assert edge.is_applicable(True, output={}) is False

    def test_edge_alias_from_to(self):
        edge = Edge(**{"from": "node-1", "to": "node-2"})
        assert edge.from_node == "node-1"
        assert edge.to_node == "node-2"

    def test_edge_default_condition_always(self):
        edge = Edge(**{"from": "a", "to": "b"})
        assert edge.condition.type == EdgeConditionType.ALWAYS
