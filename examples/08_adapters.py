"""
AFMX Example 08 — Adapters (LangChain, LangGraph, CrewAI)
Shows how to wrap external framework objects and execute them through AFMX.

All adapters work WITHOUT those frameworks actually installed.
The example uses mock objects that simulate the real framework interfaces.
To use real frameworks, just swap the mock objects for real ones.

Run:
    python examples/08_adapters.py
"""
from __future__ import annotations
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    ExecutionMode, HandlerRegistry,
)
from afmx.adapters import (
    LangChainAdapter,
    LangGraphAdapter, LangGraphTranslator,
    CrewAIAdapter, CrewAITranslator,
    AdapterRegistry,
)
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Mock Framework Objects ───────────────────────────────────────────────────
# These simulate real LangChain/LangGraph/CrewAI objects.
# In production, replace with actual framework instances.

class MockLangChainTool:
    """Simulates a LangChain BaseTool."""
    name = "mock_search_tool"

    async def ainvoke(self, input_data):
        query = input_data if isinstance(input_data, str) else str(input_data)
        return f"Search results for: {query}"


class MockLangGraphNodeFn:
    """Simulates a LangGraph node function (callable)."""
    __name__ = "mock_classifier"

    async def __call__(self, state):
        messages = state.get("messages", []) if isinstance(state, dict) else []
        return {"classification": "technical", "confidence": 0.92, "messages": messages}


class MockCrewAITask:
    """Simulates a CrewAI Task."""
    description = "Research the latest AI trends and summarize findings"

    class _agent:
        role = "Research Analyst"

    agent = _agent()

    def execute(self):
        return "AI trends report: LLMs continue to dominate, multi-agent systems rising..."


# ─── Demo 1: LangChain Adapter ────────────────────────────────────────────────

async def demo_langchain():
    print("  ── LangChain Adapter ──")
    adapter = LangChainAdapter()
    tool = MockLangChainTool()

    # Register as an AFMX handler
    HandlerRegistry.register("lc_search", adapter.build_handler_for(tool))

    from afmx.models.node import Node, NodeType
    from afmx.models.edge import Edge
    matrix = ExecutionMatrix(
        name="langchain-flow",
        mode=ExecutionMode.SEQUENTIAL,
        nodes=[
            Node(id="n1", name="lc_search", type=NodeType.FUNCTION, handler="lc_search")
        ],
        edges=[],
    )
    ctx = ExecutionContext(input="AFMX agent execution engine")
    rec = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result = await AFMXEngine().execute(matrix, ctx, rec)

    output = result.node_results.get("n1", {}).get("output", {})
    print(f"    Status : {result.status}")
    print(f"    Output : {output}")


# ─── Demo 2: LangGraph Adapter (node list) ────────────────────────────────────

async def demo_langgraph():
    print("  ── LangGraph Adapter ──")

    classifier_fn = MockLangGraphNodeFn()
    async def responder(state):
        cls = state.get("classification", "unknown")
        return {"response": f"Handling {cls} query", "done": True}

    translator = LangGraphTranslator()
    matrix = translator.from_node_list(
        node_fns=[
            ("classify", classifier_fn),
            ("respond", responder),
        ],
        name="langgraph-flow",
    )

    ctx = ExecutionContext(input={"messages": ["What is AFMX?"]})
    ctx.set_memory("__state__", {"messages": ["What is AFMX?"]})
    rec = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result = await AFMXEngine().execute(matrix, ctx, rec)

    print(f"    Status      : {result.status}")
    print(f"    Nodes done  : {result.completed_nodes}/{result.total_nodes}")
    final_state = ctx.get_memory("__state__")
    print(f"    Final state : {final_state}")


# ─── Demo 3: CrewAI Adapter ───────────────────────────────────────────────────

async def demo_crewai():
    print("  ── CrewAI Adapter ──")
    adapter = CrewAIAdapter()
    task = MockCrewAITask()

    # to_afmx_node → build matrix manually
    from afmx.models.node import Node, NodeType
    afmx_node = adapter.to_afmx_node(
        external_obj=task,
        node_id="crew-research",
        node_name="Research Analyst: AI trends",
        node_type=NodeType.FUNCTION,
    )

    # Register the adapter handler for this node's handler key
    async def crew_handler(inp, ctx, node):
        from afmx.models.execution import ExecutionContext as EC
        result = await adapter.execute(node, ctx)
        if not result.success:
            raise RuntimeError(result.error)
        return result.output

    HandlerRegistry.register(afmx_node.handler, crew_handler)

    matrix = ExecutionMatrix(
        name="crewai-flow",
        mode=ExecutionMode.SEQUENTIAL,
        nodes=[afmx_node],
        edges=[],
    )
    ctx = ExecutionContext(input="AI research task")
    rec = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result = await AFMXEngine().execute(matrix, ctx, rec)

    output = result.node_results.get("crew-research", {}).get("output", {})
    print(f"    Status : {result.status}")
    print(f"    Output : {output}")


# ─── Demo 4: Adapter Registry ─────────────────────────────────────────────────

def demo_registry():
    print("  ── Adapter Registry ──")
    registry = AdapterRegistry()
    registry.register(LangChainAdapter())
    registry.register(LangGraphAdapter())
    registry.register(CrewAIAdapter())

    for entry in registry.list_adapters():
        print(f"    [{entry['type']:20s}] {entry['name']}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("\n══════════════════════════════════════════════")
    print("  AFMX Example 08 — Framework Adapters")
    print("══════════════════════════════════════════════\n")

    HandlerRegistry.clear()

    await demo_langchain()
    print()
    await demo_langgraph()
    print()
    await demo_crewai()
    print()
    demo_registry()
    print()


if __name__ == "__main__":
    asyncio.run(main())
