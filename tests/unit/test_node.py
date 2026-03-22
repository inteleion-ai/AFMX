"""
Unit tests for Node model
"""
import pytest
from pydantic import ValidationError
from afmx.models.node import (
    Node, NodeType, NodeStatus, NodeResult,
    RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy, NodeConfig,
)


class TestNode:
    def test_node_minimal(self):
        node = Node(name="test", type=NodeType.TOOL, handler="my_tool")
        assert node.name == "test"
        assert node.type == NodeType.TOOL
        assert node.handler == "my_tool"
        assert node.id is not None
        assert len(node.id) == 36  # UUID

    def test_node_full(self):
        node = Node(
            name="search",
            type=NodeType.TOOL,
            handler="search_tool",
            config=NodeConfig(params={"limit": 10}, tags=["search"]),
            retry_policy=RetryPolicy(retries=5, backoff_seconds=2.0),
            timeout_policy=TimeoutPolicy(timeout_seconds=15.0),
            circuit_breaker=CircuitBreakerPolicy(enabled=True, failure_threshold=3),
            fallback_node_id="fallback-1",
            priority=2,
        )
        assert node.retry_policy.retries == 5
        assert node.timeout_policy.timeout_seconds == 15.0
        assert node.circuit_breaker.enabled is True
        assert node.fallback_node_id == "fallback-1"
        assert node.priority == 2

    def test_node_handler_strips_whitespace(self):
        node = Node(name="n", type=NodeType.TOOL, handler="  my_handler  ")
        assert node.handler == "my_handler"

    def test_node_empty_handler_raises(self):
        with pytest.raises(ValidationError):
            Node(name="n", type=NodeType.TOOL, handler="   ")

    def test_node_invalid_priority_raises(self):
        with pytest.raises(ValidationError):
            Node(name="n", type=NodeType.TOOL, handler="h", priority=0)
        with pytest.raises(ValidationError):
            Node(name="n", type=NodeType.TOOL, handler="h", priority=11)

    def test_node_types(self):
        for t in [NodeType.TOOL, NodeType.AGENT, NodeType.FUNCTION]:
            node = Node(name="n", type=t, handler="h")
            assert node.type == t

    def test_retry_policy_defaults(self):
        rp = RetryPolicy()
        assert rp.retries == 3
        assert rp.backoff_seconds == 1.0
        assert rp.backoff_multiplier == 2.0
        assert rp.jitter is True

    def test_retry_policy_max_retries(self):
        with pytest.raises(ValidationError):
            RetryPolicy(retries=11)

    def test_node_result_is_success(self):
        r = NodeResult(node_id="x", node_name="x", status=NodeStatus.SUCCESS)
        assert r.is_success is True
        assert r.is_terminal_failure is False

    def test_node_result_is_failure(self):
        r = NodeResult(node_id="x", node_name="x", status=NodeStatus.FAILED, error="boom")
        assert r.is_success is False
        assert r.is_terminal_failure is True

    def test_node_result_aborted_is_terminal(self):
        r = NodeResult(node_id="x", node_name="x", status=NodeStatus.ABORTED)
        assert r.is_terminal_failure is True
