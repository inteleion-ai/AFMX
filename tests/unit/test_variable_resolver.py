"""
Unit tests for VariableResolver
"""
import pytest
from afmx.core.variable_resolver import VariableResolver
from afmx.models.execution import ExecutionContext


@pytest.fixture
def resolver():
    return VariableResolver()


@pytest.fixture
def context():
    ctx = ExecutionContext(
        input={"query": "hello", "nested": {"key": "value"}},
        memory={"session": "abc123", "counter": 5},
        variables={"page_size": 10, "model": "gpt-4"},
        metadata={"tenant_id": "t-001", "env": "prod"},
    )
    ctx.set_node_output("prev-node", {"result": "upstream_data", "count": 42})
    return ctx


class TestVariableResolver:

    def test_resolve_input_root(self, resolver, context):
        params = {"q": "{{input}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["q"] == {"query": "hello", "nested": {"key": "value"}}

    def test_resolve_input_field(self, resolver, context):
        params = {"query": "{{input.query}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["query"] == "hello"

    def test_resolve_input_nested(self, resolver, context):
        params = {"val": "{{input.nested.key}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["val"] == "value"

    def test_resolve_memory(self, resolver, context):
        params = {"sid": "{{memory.session}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["sid"] == "abc123"

    def test_resolve_variables(self, resolver, context):
        params = {"size": "{{variables.page_size}}", "mdl": "{{variables.model}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["size"] == 10
        assert resolved["mdl"] == "gpt-4"

    def test_resolve_metadata(self, resolver, context):
        params = {"tenant": "{{metadata.tenant_id}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["tenant"] == "t-001"

    def test_resolve_node_output(self, resolver, context):
        params = {"data": "{{node.prev-node.output.result}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["data"] == "upstream_data"

    def test_resolve_node_output_count(self, resolver, context):
        params = {"n": "{{node.prev-node.output.count}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["n"] == 42

    def test_resolve_whole_node_output(self, resolver, context):
        params = {"all": "{{node.prev-node.output}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["all"]["result"] == "upstream_data"

    def test_string_interpolation(self, resolver, context):
        params = {"msg": "Hello {{input.query}} from {{metadata.env}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["msg"] == "Hello hello from prod"

    def test_no_template_passthrough(self, resolver, context):
        params = {"plain": "no template here", "num": 42}
        resolved = resolver.resolve_params(params, context)
        assert resolved["plain"] == "no template here"
        assert resolved["num"] == 42

    def test_unresolvable_returns_none_for_full_expression(self, resolver, context):
        params = {"x": "{{node.nonexistent.output.field}}"}
        resolved = resolver.resolve_params(params, context)
        assert resolved["x"] is None

    def test_unresolvable_in_string_keeps_original(self, resolver, context):
        params = {"msg": "prefix {{node.ghost.output}} suffix"}
        resolved = resolver.resolve_params(params, context)
        # None in string interpolation → keeps original expression
        assert "prefix" in resolved["msg"]

    def test_nested_dict_params(self, resolver, context):
        params = {"config": {"query": "{{input.query}}", "size": "{{variables.page_size}}"}}
        resolved = resolver.resolve_params(params, context)
        assert resolved["config"]["query"] == "hello"
        assert resolved["config"]["size"] == 10

    def test_list_params(self, resolver, context):
        params = {"items": ["{{input.query}}", "static", "{{memory.session}}"]}
        resolved = resolver.resolve_params(params, context)
        assert resolved["items"] == ["hello", "static", "abc123"]

    def test_empty_params(self, resolver, context):
        assert resolver.resolve_params({}, context) == {}
