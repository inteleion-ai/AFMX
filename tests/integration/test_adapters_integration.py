"""
Integration tests: Adapters → Engine → ExecutionMatrix

Tests the complete pipeline:
  adapter.to_afmx_node() → ExecutionMatrix → AFMXEngine.execute()

No external frameworks required — all framework objects are mocked.
"""
from __future__ import annotations

import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

from afmx.core.executor import HandlerRegistry
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import ExecutionMatrix, ExecutionMode
from afmx.models.node import Node, NodeType
from afmx.models.edge import Edge
from afmx.core.engine import AFMXEngine


# ─── Mock framework injection ─────────────────────────────────────────────────

def _inject_fake_langchain():
    fake = types.ModuleType("langchain")
    fake_tools = types.ModuleType("langchain.tools")
    class FakeBaseTool: pass
    fake_tools.BaseTool = FakeBaseTool
    fake.tools = fake_tools
    sys.modules.setdefault("langchain", fake)
    sys.modules.setdefault("langchain.tools", fake_tools)


def _inject_fake_langgraph():
    sys.modules.setdefault("langgraph", types.ModuleType("langgraph"))


def _inject_fake_crewai():
    sys.modules.setdefault("crewai", types.ModuleType("crewai"))


def _inject_fake_openai():
    if "openai" not in sys.modules:
        fake = types.ModuleType("openai")
        class FakeAsyncOpenAI:
            def __init__(self, **kw): pass
        fake.AsyncOpenAI = FakeAsyncOpenAI
        sys.modules["openai"] = fake


_inject_fake_langchain()
_inject_fake_langgraph()
_inject_fake_crewai()
_inject_fake_openai()


@pytest.fixture(autouse=True)
def clean_handlers():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()


# ─── Helper ───────────────────────────────────────────────────────────────────

def make_record(matrix: ExecutionMatrix) -> ExecutionRecord:
    return ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
    )


# ─── LangChain adapter → Engine ───────────────────────────────────────────────

class TestLangChainAdapterEngine:
    @pytest.mark.asyncio
    async def test_single_tool_node_executes(self):
        from afmx.adapters.langchain import LangChainAdapter

        adapter = LangChainAdapter()
        tool = MagicMock()
        tool.name = "search"
        tool.ainvoke = AsyncMock(return_value={"results": ["a", "b"]})

        node = adapter.to_afmx_node(tool)
        matrix = ExecutionMatrix(
            name="lc-test",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[node],
            edges=[],
        )
        ctx = ExecutionContext(input="find python tutorials")
        rec = make_record(matrix)

        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 1

    @pytest.mark.asyncio
    async def test_two_tool_chain(self):
        from afmx.adapters.langchain import LangChainAdapter

        adapter = LangChainAdapter()

        tool1 = MagicMock()
        tool1.name = "fetch"
        tool1.ainvoke = AsyncMock(return_value="raw content")

        tool2 = MagicMock()
        tool2.name = "summarise"
        tool2.ainvoke = AsyncMock(return_value={"summary": "short version"})

        n1 = adapter.to_afmx_node(tool1, node_id="n1", node_name="fetch")
        n2 = adapter.to_afmx_node(tool2, node_id="n2", node_name="summarise")

        matrix = ExecutionMatrix(
            name="lc-chain",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[n1, n2],
            edges=[Edge(**{"from": "n1", "to": "n2"})],
        )
        ctx = ExecutionContext(input="https://example.com")
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 2

    @pytest.mark.asyncio
    async def test_tool_failure_marks_failed(self):
        from afmx.adapters.langchain import LangChainAdapter

        adapter = LangChainAdapter()
        bad_tool = MagicMock()
        bad_tool.name = "bad"
        bad_tool.ainvoke = AsyncMock(side_effect=RuntimeError("network down"))

        node = adapter.to_afmx_node(bad_tool)
        matrix = ExecutionMatrix(
            name="fail-test",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[node],
            edges=[],
        )
        ctx = ExecutionContext(input="anything")
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.FAILED
        assert result.failed_nodes == 1


# ─── LangGraph adapter → Engine ───────────────────────────────────────────────

class TestLangGraphAdapterEngine:
    @pytest.mark.asyncio
    async def test_graph_node_executes(self):
        from afmx.adapters.langgraph import LangGraphAdapter

        adapter = LangGraphAdapter()
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"answer": "42", "done": True})

        node = adapter.to_afmx_node(graph, node_name="reasoning")
        matrix = ExecutionMatrix(
            name="lg-test",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[node],
            edges=[],
        )
        ctx = ExecutionContext(input={"question": "What is 6x7?"})
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_translate_graph_and_execute(self):
        from afmx.adapters.langgraph import LangGraphAdapter

        adapter = LangGraphAdapter()

        step1 = AsyncMock(return_value={"step": 1, "done": False})
        step2 = AsyncMock(return_value={"step": 2, "done": True})

        mock_graph = MagicMock()
        mock_graph.nodes = {"step1": step1, "step2": step2}
        mock_graph.graph = MagicMock()
        mock_graph.graph.nodes = mock_graph.nodes
        mock_graph.graph.edges = [
            MagicMock(start="step1", end="step2"),
        ]

        matrix = adapter.translate_graph(mock_graph, matrix_name="lg-translated")
        assert len(matrix.nodes) == 2

        ctx = ExecutionContext(input={"query": "hello"})
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 2


# ─── CrewAI adapter → Engine ──────────────────────────────────────────────────

class TestCrewAIAdapterEngine:
    @pytest.mark.asyncio
    async def test_task_node_executes(self):
        from afmx.adapters.crewai import CrewAIAdapter

        adapter = CrewAIAdapter()
        task = MagicMock()
        task.description = "analyse quarterly data"
        task.expected_output = "report"
        task.agent = MagicMock()
        task.agent.role = "analyst"
        task.execute_sync = MagicMock(return_value="Q3 report complete")

        node = adapter.to_afmx_node(task)
        matrix = ExecutionMatrix(
            name="crew-test",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[node],
            edges=[],
        )
        ctx = ExecutionContext(input="run Q3 analysis")
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 1

    @pytest.mark.asyncio
    async def test_crew_translation_executes(self):
        from afmx.adapters.crewai import CrewAIAdapter

        adapter = CrewAIAdapter()
        tasks = []
        for i in range(3):
            t = MagicMock()
            t.description = f"step {i}"
            t.expected_output = "done"
            t.agent = MagicMock()
            t.agent.role = f"agent_{i}"
            t.execute_sync = MagicMock(return_value=f"result_{i}")
            tasks.append(t)

        crew = MagicMock()
        crew.tasks = tasks
        crew.process = MagicMock()
        crew.process.value = "sequential"

        matrix = adapter.translate_crew(crew, matrix_name="crew-3tasks")
        assert len(matrix.nodes) == 3

        ctx = ExecutionContext(input="start crew")
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 3


# ─── Adapter registry → Engine ────────────────────────────────────────────────

class TestAdapterRegistryIntegration:
    def test_registry_has_all_builtins(self):
        from afmx.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        adapters = registry.list_adapters()
        names = {a["name"] for a in adapters}
        assert "langchain" in names
        assert "langgraph" in names
        assert "crewai" in names
        assert "openai" in names

    def test_registry_get_langchain(self):
        from afmx.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        adapter = registry.get("langchain")
        assert adapter.name == "langchain"

    def test_registry_get_optional_missing(self):
        from afmx.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        result = registry.get_optional("totally_fake_framework")
        assert result is None

    def test_custom_adapter_registration(self):
        from afmx.adapters.base import AFMXAdapter, AdapterResult
        from afmx.adapters.registry import AdapterRegistry

        registry = AdapterRegistry()
        registry._initialized = True  # Skip auto-loading builtins

        @registry.register_adapter
        class CustomAdapter(AFMXAdapter):
            @property
            def name(self): return "custom_fw"

            def to_afmx_node(self, *a, **kw):
                return None

            async def execute(self, *a, **kw):
                return AdapterResult.ok("done")

        assert registry.has("custom_fw")
        adapter = registry.get("custom_fw")
        assert adapter.name == "custom_fw"

    @pytest.mark.asyncio
    async def test_adapter_node_executes_via_registry(self):
        """Full path: get adapter from registry → create node → execute via engine."""
        from afmx.adapters.registry import AdapterRegistry

        registry = AdapterRegistry()
        adapter = registry.get("langchain")

        tool = MagicMock()
        tool.name = "registry_tool"
        tool.ainvoke = AsyncMock(return_value={"status": "ok"})

        node = adapter.to_afmx_node(tool, node_id="reg_node")
        matrix = ExecutionMatrix(
            name="registry-test",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[node],
        )
        ctx = ExecutionContext(input="test input")
        rec = make_record(matrix)
        result = await AFMXEngine().execute(matrix, ctx, rec)

        assert result.status == ExecutionStatus.COMPLETED
