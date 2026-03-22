"""
Unit tests for ToolRouter
"""
import pytest
from afmx.core.router import ToolRouter, RoutingRule, RoutingStrategy


async def dummy_handler(inp, ctx, node):
    return "tool_result"


async def search_handler(inp, ctx, node):
    return "search_result"


async def db_handler(inp, ctx, node):
    return "db_result"


class TestToolRouter:
    def test_register_and_direct_resolve(self):
        router = ToolRouter()
        router.register("my_tool", dummy_handler)
        tool = router.resolve(handler_key="my_tool")
        assert tool.key == "my_tool"
        assert tool.handler is dummy_handler

    def test_unknown_key_raises(self):
        router = ToolRouter()
        with pytest.raises(KeyError):
            router.resolve(handler_key="nonexistent")

    def test_set_default_fallback(self):
        router = ToolRouter()
        router.register("default_tool", dummy_handler)
        router.set_default("default_tool")
        tool = router.resolve()
        assert tool.key == "default_tool"

    def test_set_default_unknown_raises(self):
        router = ToolRouter()
        with pytest.raises(KeyError):
            router.set_default("unknown")

    def test_intent_rule_matching(self):
        router = ToolRouter()
        router.register("search_tool", search_handler)
        router.register("db_tool", db_handler)
        router.add_rule(RoutingRule(
            tool_key="search_tool",
            priority=1,
            intent_patterns=[r"search|find|lookup"],
        ))
        router.add_rule(RoutingRule(
            tool_key="db_tool",
            priority=2,
            intent_patterns=[r"database|query|sql"],
        ))
        tool = router.resolve(intent="search for users")
        assert tool.key == "search_tool"

        tool2 = router.resolve(intent="run a SQL query")
        assert tool2.key == "db_tool"

    def test_metadata_rule_matching(self):
        router = ToolRouter()
        router.register("db_tool", db_handler)
        router.add_rule(RoutingRule(
            tool_key="db_tool",
            priority=1,
            metadata_match={"type": "db"},
        ))
        tool = router.resolve(metadata={"type": "db"})
        assert tool.key == "db_tool"

    def test_priority_first_match_wins(self):
        router = ToolRouter()
        router.register("tool_a", dummy_handler)
        router.register("tool_b", db_handler)
        router.add_rule(RoutingRule(
            tool_key="tool_a",
            priority=1,
            intent_patterns=[r"test"],
        ))
        router.add_rule(RoutingRule(
            tool_key="tool_b",
            priority=2,
            intent_patterns=[r"test"],
        ))
        tool = router.resolve(intent="test this")
        assert tool.key == "tool_a"  # Priority 1 wins

    def test_tag_matching(self):
        router = ToolRouter()
        router.register("tagged_tool", dummy_handler, tags=["nlp", "search"])
        tool = router.resolve(tags=["nlp"])
        assert tool.key == "tagged_tool"

    def test_no_match_no_default_raises(self):
        router = ToolRouter()
        with pytest.raises(RuntimeError):
            router.resolve(intent="something unmatched")

    def test_deregister(self):
        router = ToolRouter()
        router.register("tool", dummy_handler)
        router.deregister("tool")
        with pytest.raises((KeyError, RuntimeError)):
            router.resolve(handler_key="tool")

    def test_list_tools(self):
        router = ToolRouter()
        router.register("t1", dummy_handler, description="Tool 1", tags=["a"])
        router.register("t2", db_handler, description="Tool 2")
        tools = router.list_tools()
        assert len(tools) == 2
        keys = [t["key"] for t in tools]
        assert "t1" in keys
        assert "t2" in keys
