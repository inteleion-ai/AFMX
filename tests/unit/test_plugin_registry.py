"""
Unit tests for PluginRegistry
"""
import pytest
from afmx.plugins.registry import PluginRegistry


async def my_handler(inp, ctx, node): return "ok"


class TestPluginRegistry:

    def test_register_and_get_handler(self):
        reg = PluginRegistry()
        reg.register("my_tool", my_handler, plugin_type="tool")
        handler = reg.get_handler("my_tool")
        assert handler is my_handler

    def test_decorator_tool(self):
        reg = PluginRegistry()

        @reg.tool("decorated_tool", description="A test tool", tags=["x"])
        async def tool_fn(inp, ctx, node): return "tool"

        meta = reg.get("decorated_tool")
        assert meta is not None
        assert meta.plugin_type == "tool"
        assert meta.description == "A test tool"
        assert "x" in meta.tags

    def test_decorator_agent(self):
        reg = PluginRegistry()

        @reg.agent("my_agent")
        async def agent_fn(inp, ctx, node): return "agent"

        assert reg.get("my_agent").plugin_type == "agent"

    def test_decorator_function(self):
        reg = PluginRegistry()

        @reg.function("my_fn")
        async def fn(inp, ctx, node): return "fn"

        assert reg.get("my_fn").plugin_type == "function"

    def test_get_unknown_raises(self):
        reg = PluginRegistry()
        with pytest.raises(KeyError):
            reg.get_handler("ghost")

    def test_disable_raises_on_get(self):
        reg = PluginRegistry()
        reg.register("disabled_tool", my_handler, plugin_type="tool")
        reg.disable("disabled_tool")
        with pytest.raises(RuntimeError):
            reg.get_handler("disabled_tool")

    def test_re_enable(self):
        reg = PluginRegistry()
        reg.register("toggle", my_handler, plugin_type="tool")
        reg.disable("toggle")
        reg.enable("toggle")
        handler = reg.get_handler("toggle")
        assert handler is my_handler

    def test_list_all(self):
        reg = PluginRegistry()
        reg.register("t1", my_handler, plugin_type="tool")
        reg.register("a1", my_handler, plugin_type="agent")
        reg.register("f1", my_handler, plugin_type="function")
        all_plugins = reg.list_all()
        assert len(all_plugins) == 3
        types = {p["type"] for p in all_plugins}
        assert types == {"tool", "agent", "function"}

    def test_list_by_type(self):
        reg = PluginRegistry()
        reg.register("t1", my_handler, plugin_type="tool")
        reg.register("t2", my_handler, plugin_type="tool")
        reg.register("a1", my_handler, plugin_type="agent")
        tools = reg.list_by_type("tool")
        assert len(tools) == 2

    def test_overwrite_warns_and_succeeds(self, caplog):
        reg = PluginRegistry()
        reg.register("dup", my_handler, plugin_type="tool")
        async def new_handler(inp, ctx, node): return "new"
        reg.register("dup", new_handler, plugin_type="tool")
        assert reg.get_handler("dup") is new_handler

    def test_sync_to_handler_registry(self):
        from afmx.core.executor import HandlerRegistry
        HandlerRegistry.clear()
        reg = PluginRegistry()
        reg.register("sync_tool", my_handler, plugin_type="tool")
        reg.sync_to_handler_registry()
        resolved = HandlerRegistry.resolve("sync_tool")
        assert resolved is my_handler
