"""
Unit tests for AFMX Adapters
All external framework dependencies are mocked — tests run without
langchain, langgraph, or crewai being installed.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from afmx.adapters.base import AFMXAdapter, AdapterResult, AdapterNodeConfig
from afmx.adapters.registry import AdapterRegistry
from afmx.core.executor import HandlerRegistry
from afmx.models.node import NodeType, NodeStatus
from afmx.models.execution import ExecutionContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_handler_registry():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()


def make_mock_tool(name: str = "mock_tool", return_val: Any = "tool_result"):
    """Create a minimal mock that looks like a LangChain tool."""
    tool = MagicMock()
    tool.name = name
    tool.invoke = MagicMock(return_value=return_val)
    tool.ainvoke = AsyncMock(return_value=return_val)
    return tool


def make_mock_graph(return_val: Any = {"answer": "42"}):
    """Create a minimal mock that looks like a compiled LangGraph graph."""
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=return_val)
    graph.invoke = MagicMock(return_value=return_val)
    # Give it a minimal nodes/edges structure
    graph.nodes = {"step_one": MagicMock(), "step_two": MagicMock()}
    graph.graph = MagicMock()
    graph.graph.nodes = graph.nodes
    graph.graph.edges = []
    return graph


def make_mock_task(description: str = "analyse data", return_val: Any = "task_done"):
    """Create a minimal mock that looks like a CrewAI task."""
    task = MagicMock()
    task.description = description
    task.expected_output = "analysis results"
    task.agent = MagicMock()
    task.agent.role = "analyst"
    execute_mock = MagicMock(return_value=return_val)
    task.execute_sync = execute_mock
    return task


def make_mock_crew(tasks=None):
    """Create a minimal mock that looks like a CrewAI Crew."""
    crew = MagicMock()
    crew.tasks = tasks or [make_mock_task()]
    crew.process = MagicMock()
    crew.process.value = "sequential"
    return crew


# ─── AdapterResult ────────────────────────────────────────────────────────────

class TestAdapterResult:
    def test_ok_result(self):
        r = AdapterResult.ok(output={"data": 42})
        assert r.success is True
        assert r.output == {"data": 42}
        assert r.error is None

    def test_fail_result(self):
        r = AdapterResult.fail("something broke", "ValueError")
        assert r.success is False
        assert r.error == "something broke"
        assert r.error_type == "ValueError"
        assert r.output is None

    def test_ok_with_metadata(self):
        r = AdapterResult.ok(output="hello", latency=42)
        assert r.metadata["latency"] == 42

    def test_fail_with_metadata(self):
        r = AdapterResult.fail("err", node_id="n1")
        assert r.metadata["node_id"] == "n1"


# ─── AdapterRegistry ──────────────────────────────────────────────────────────

class TestAdapterRegistry:
    def test_register_and_get(self):
        registry = AdapterRegistry()

        class DummyAdapter(AFMXAdapter):
            @property
            def name(self): return "dummy"
            def to_afmx_node(self, *a, **kw): pass
            async def execute(self, *a, **kw): return AdapterResult.ok()

        registry.register(DummyAdapter())
        adapter = registry.get("dummy")
        assert adapter.name == "dummy"

    def test_get_unknown_raises(self):
        registry = AdapterRegistry()
        registry._initialized = True  # Skip auto-load
        with pytest.raises(KeyError, match="not registered"):
            registry.get("nonexistent")

    def test_get_optional_returns_none(self):
        registry = AdapterRegistry()
        registry._initialized = True
        result = registry.get_optional("ghost")
        assert result is None

    def test_has(self):
        registry = AdapterRegistry()

        class DummyAdapter(AFMXAdapter):
            @property
            def name(self): return "testadapter"
            def to_afmx_node(self, *a, **kw): pass
            async def execute(self, *a, **kw): return AdapterResult.ok()

        assert not registry.has("testadapter")
        registry.register(DummyAdapter())
        assert registry.has("testadapter")

    def test_register_decorator(self):
        registry = AdapterRegistry()

        @registry.register_adapter
        class DecoratedAdapter(AFMXAdapter):
            @property
            def name(self): return "decorated"
            def to_afmx_node(self, *a, **kw): pass
            async def execute(self, *a, **kw): return AdapterResult.ok()

        assert registry.has("decorated")

    def test_list_adapters(self):
        registry = AdapterRegistry()
        registry._initialized = True

        class A1(AFMXAdapter):
            @property
            def name(self): return "a1"
            def to_afmx_node(self, *a, **kw): pass
            async def execute(self, *a, **kw): return AdapterResult.ok()

        registry.register(A1())
        listed = registry.list_adapters()
        assert any(a["name"] == "a1" for a in listed)

    def test_deregister(self):
        registry = AdapterRegistry()
        registry._initialized = True

        class A2(AFMXAdapter):
            @property
            def name(self): return "a2"
            def to_afmx_node(self, *a, **kw): pass
            async def execute(self, *a, **kw): return AdapterResult.ok()

        registry.register(A2())
        registry.deregister("a2")
        assert not registry.has("a2")


# ─── LangChain Adapter ────────────────────────────────────────────────────────

class TestLangChainAdapter:
    """Tests LangChain adapter with mocked langchain imports."""

    def _make_adapter_with_mock_langchain(self):
        """Patch langchain so adapter doesn't need it installed."""
        # Create a minimal fake langchain package
        fake_lc = types.ModuleType("langchain")
        fake_tools = types.ModuleType("langchain.tools")

        class FakeBaseTool:
            pass

        fake_tools.BaseTool = FakeBaseTool
        fake_lc.tools = fake_tools
        sys.modules.setdefault("langchain", fake_lc)
        sys.modules.setdefault("langchain.tools", fake_tools)

        from afmx.adapters.langchain import LangChainAdapter
        return LangChainAdapter()

    def test_to_afmx_node_creates_tool_node(self):
        adapter = self._make_adapter_with_mock_langchain()
        tool = make_mock_tool("search")
        node = adapter.to_afmx_node(tool)
        assert node.type == NodeType.TOOL or node.type == NodeType.FUNCTION
        assert "search" in node.handler
        assert node.name == "search"

    def test_to_afmx_node_registers_handler(self):
        adapter = self._make_adapter_with_mock_langchain()
        tool = make_mock_tool("web_search")
        adapter.to_afmx_node(tool)
        assert any("web_search" in k for k in HandlerRegistry.list_registered())

    @pytest.mark.asyncio
    async def test_execute_calls_ainvoke(self):
        adapter = self._make_adapter_with_mock_langchain()
        tool = make_mock_tool("test_tool", return_val="result_data")
        result = await adapter.execute({"input": "query"}, tool)
        assert result.success is True
        assert result.output == "result_data"
        tool.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_returns_fail_on_exception(self):
        adapter = self._make_adapter_with_mock_langchain()
        tool = MagicMock()
        tool.name = "bad_tool"
        tool.ainvoke = AsyncMock(side_effect=RuntimeError("network error"))
        result = await adapter.execute({"input": "x"}, tool)
        assert result.success is False
        assert "network error" in result.error

    def test_normalize_dict_with_output_key(self):
        adapter = self._make_adapter_with_mock_langchain()
        result = adapter.normalize({"output": "final_answer"})
        assert result.output == "final_answer"

    def test_normalize_plain_value(self):
        adapter = self._make_adapter_with_mock_langchain()
        result = adapter.normalize("plain text")
        assert result.output == "plain text"

    @pytest.mark.asyncio
    async def test_make_handler_raises_on_failure(self):
        adapter = self._make_adapter_with_mock_langchain()
        failing_tool = MagicMock()
        failing_tool.name = "fail"
        failing_tool.ainvoke = AsyncMock(side_effect=ValueError("broken"))
        handler = adapter.make_handler(failing_tool)
        with pytest.raises(RuntimeError, match="broken"):
            await handler({"input": "x"}, None, None)

    @pytest.mark.asyncio
    async def test_make_handler_returns_output_on_success(self):
        adapter = self._make_adapter_with_mock_langchain()
        good_tool = make_mock_tool("good", return_val={"answer": 99})
        handler = adapter.make_handler(good_tool)
        output = await handler({"input": "q"}, None, None)
        assert output == {"answer": 99}


# ─── LangGraph Adapter ────────────────────────────────────────────────────────

class TestLangGraphAdapter:
    """Tests LangGraph adapter with mocked langgraph imports."""

    def _make_adapter_with_mock_langgraph(self):
        fake_lg = types.ModuleType("langgraph")
        sys.modules.setdefault("langgraph", fake_lg)
        from afmx.adapters.langgraph import LangGraphAdapter
        return LangGraphAdapter()

    def test_to_afmx_node_single_wrap(self):
        adapter = self._make_adapter_with_mock_langgraph()
        graph = make_mock_graph()
        node = adapter.to_afmx_node(graph, node_name="my_graph")
        assert node.type == NodeType.FUNCTION
        assert "my_graph" in node.handler
        assert node.name == "my_graph"

    def test_to_afmx_node_registers_handler(self):
        adapter = self._make_adapter_with_mock_langgraph()
        graph = make_mock_graph()
        adapter.to_afmx_node(graph, node_name="test_graph")
        assert any("test_graph" in k for k in HandlerRegistry.list_registered())

    def test_translate_graph_produces_matrix(self):
        adapter = self._make_adapter_with_mock_langgraph()
        graph = make_mock_graph()
        matrix = adapter.translate_graph(graph, matrix_name="test-matrix")
        assert matrix.name == "test-matrix"
        assert len(matrix.nodes) > 0
        for node in matrix.nodes:
            assert node.type == NodeType.FUNCTION
            assert "langgraph:" in node.handler

    def test_translate_graph_skips_virtual_nodes(self):
        adapter = self._make_adapter_with_mock_langgraph()
        graph = make_mock_graph()
        # Add virtual nodes to mock — they should be excluded
        graph.nodes = {
            "__start__": MagicMock(),
            "my_node": MagicMock(),
            "__end__": MagicMock(),
        }
        graph.graph.nodes = graph.nodes
        matrix = adapter.translate_graph(graph)
        node_ids = [n.id for n in matrix.nodes]
        assert "__start__" not in node_ids
        assert "__end__" not in node_ids
        assert "my_node" in node_ids

    @pytest.mark.asyncio
    async def test_execute_calls_ainvoke(self):
        adapter = self._make_adapter_with_mock_langgraph()
        graph = make_mock_graph({"result": "done"})
        result = await adapter.execute({"input": {"query": "hello"}}, graph)
        assert result.success is True
        assert result.output == {"result": "done"}
        graph.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_returns_fail_on_exception(self):
        adapter = self._make_adapter_with_mock_langgraph()
        bad_graph = MagicMock()
        bad_graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph error"))
        result = await adapter.execute({"input": {}}, bad_graph)
        assert result.success is False
        assert "graph error" in result.error

    def test_normalize_dict_output(self):
        adapter = self._make_adapter_with_mock_langgraph()
        result = adapter.normalize({"state": "final", "answer": 42})
        assert result.output == {"state": "final", "answer": 42}

    def test_translate_graph_empty_raises(self):
        adapter = self._make_adapter_with_mock_langgraph()
        empty_graph = MagicMock()
        # Only virtual nodes
        empty_graph.nodes = {"__start__": MagicMock(), "__end__": MagicMock()}
        empty_graph.graph = MagicMock()
        empty_graph.graph.nodes = empty_graph.nodes
        empty_graph.graph.edges = []
        with pytest.raises(ValueError, match="0 AFMX nodes"):
            adapter.translate_graph(empty_graph)


# ─── CrewAI Adapter ───────────────────────────────────────────────────────────

class TestCrewAIAdapter:
    """Tests CrewAI adapter with mocked crewai imports."""

    def _make_adapter_with_mock_crewai(self):
        fake_crewai = types.ModuleType("crewai")
        sys.modules.setdefault("crewai", fake_crewai)
        from afmx.adapters.crewai import CrewAIAdapter
        return CrewAIAdapter()

    def test_to_afmx_node_task(self):
        adapter = self._make_adapter_with_mock_crewai()
        task = make_mock_task("process invoices")
        node = adapter.to_afmx_node(task)
        assert node.type == NodeType.FUNCTION
        assert "crewai:" in node.handler
        assert node.name is not None

    def test_to_afmx_node_agent(self):
        adapter = self._make_adapter_with_mock_crewai()
        agent = MagicMock()
        agent.role = "data_analyst"
        node = adapter.to_afmx_node(agent, node_type=NodeType.AGENT)
        assert node.type == NodeType.AGENT

    def test_to_afmx_node_registers_handler(self):
        adapter = self._make_adapter_with_mock_crewai()
        task = make_mock_task("my task")
        adapter.to_afmx_node(task)
        assert len(HandlerRegistry.list_registered()) > 0

    def test_translate_crew_creates_matrix(self):
        adapter = self._make_adapter_with_mock_crewai()
        tasks = [make_mock_task(f"task {i}") for i in range(3)]
        crew = make_mock_crew(tasks)
        matrix = adapter.translate_crew(crew, matrix_name="crew-matrix")
        assert matrix.name == "crew-matrix"
        assert len(matrix.nodes) == 3

    def test_translate_crew_sequential_has_edges(self):
        adapter = self._make_adapter_with_mock_crewai()
        tasks = [make_mock_task(f"t{i}") for i in range(3)]
        crew = make_mock_crew(tasks)
        matrix = adapter.translate_crew(crew)
        # Sequential: 3 nodes → 2 edges
        assert len(matrix.edges) == 2

    def test_translate_crew_no_tasks_raises(self):
        adapter = self._make_adapter_with_mock_crewai()
        empty_crew = MagicMock()
        empty_crew.tasks = []
        with pytest.raises(ValueError, match="no tasks"):
            adapter.translate_crew(empty_crew)

    @pytest.mark.asyncio
    async def test_execute_task_via_execute_sync(self):
        adapter = self._make_adapter_with_mock_crewai()
        task = make_mock_task("analyse", return_val="analysis complete")
        result = await adapter.execute({"input": "data"}, task)
        assert result.success is True
        assert result.output == {"result": "analysis complete"}

    @pytest.mark.asyncio
    async def test_execute_returns_fail_on_exception(self):
        adapter = self._make_adapter_with_mock_crewai()
        bad_task = MagicMock()
        bad_task.execute_sync = MagicMock(side_effect=RuntimeError("task failed"))
        result = await adapter.execute({"input": "x"}, bad_task)
        assert result.success is False
        assert "task failed" in result.error

    def test_normalize_string_wraps_in_result(self):
        adapter = self._make_adapter_with_mock_crewai()
        result = adapter.normalize("Final output string")
        assert result.output == {"result": "Final output string"}

    def test_normalize_dict_passthrough(self):
        adapter = self._make_adapter_with_mock_crewai()
        result = adapter.normalize({"data": [1, 2, 3]})
        assert result.output == {"data": [1, 2, 3]}

    def test_translate_crew_node_metadata(self):
        adapter = self._make_adapter_with_mock_crewai()
        task = make_mock_task("research task")
        task.expected_output = "report"
        crew = make_mock_crew([task])
        matrix = adapter.translate_crew(crew)
        node = matrix.nodes[0]
        assert node.metadata["adapter"] == "crewai"
        assert "task_description" in node.metadata


# ─── Integration: Adapter → HandlerRegistry → NodeExecutor ───────────────────

class TestAdapterEndToEnd:
    """
    Integration tests: adapter creates a node whose handler is registered
    and can be called by NodeExecutor without any real framework installed.
    """

    @pytest.mark.asyncio
    async def test_langchain_adapter_handler_executes_via_registry(self):
        """Handler registered by LangChainAdapter can be resolved and called."""
        fake_lc = types.ModuleType("langchain")
        fake_tools = types.ModuleType("langchain.tools")

        class FakeBaseTool:
            pass

        fake_tools.BaseTool = FakeBaseTool
        fake_lc.tools = fake_tools
        sys.modules.setdefault("langchain", fake_lc)
        sys.modules.setdefault("langchain.tools", fake_tools)

        from afmx.adapters.langchain import LangChainAdapter
        from afmx.core.executor import NodeExecutor
        from afmx.core.retry import RetryManager

        adapter = LangChainAdapter()
        tool = make_mock_tool("e2e_tool", return_val={"answer": "42"})
        node = adapter.to_afmx_node(tool, node_id="e2e", node_name="e2e_node")

        executor = NodeExecutor(retry_manager=RetryManager())
        ctx = ExecutionContext(input="what is the answer?")
        result = await executor.execute(node, ctx)

        assert result.status == NodeStatus.SUCCESS
        assert result.output == {"answer": "42"}
