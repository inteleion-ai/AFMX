"""
AFMX Example 07 — Multi-Agent Coordination
Coordinator agent dispatches sub-tasks to specialist agents.
Uses AgentDispatcher with capability + complexity routing.

Topology:
    coordinator ──► nlp_specialist    (complexity > 0.6)
                └──► data_specialist  (complexity <= 0.6)
                └──► writer_agent     (always, final step)

Fix: writer node result output can be None when the node is skipped
     (key exists in node_results but value is None).
     Use `(... or {})` instead of `.get("output", {})`.

Run:
    python examples/07_multi_agent.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, EdgeCondition, EdgeConditionType,
    ExecutionMode, HandlerRegistry,
)
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def coordinator(inp, ctx, node):
    task = inp.get("input", {}).get("task", "")
    complexity = 0.8 if "analyse" in task.lower() else 0.4
    print(f"  🎯 [coordinator] Task='{task}' → complexity={complexity}")
    ctx.set_memory("complexity", complexity)
    ctx.set_memory("task", task)
    return {"task": task, "complexity": complexity, "routed": True}


async def nlp_specialist(inp, ctx, node):
    task = ctx.get_memory("task", "?")
    print(f"  🔬 [nlp_specialist] High-complexity analysis: '{task}'")
    await asyncio.sleep(0.04)
    return {
        "analysis":    f"Deep NLP analysis of: {task}",
        "entities":    ["AI", "research", "2026"],
        "sentiment":   "positive",
        "handled_by":  "nlp_specialist",
    }


async def data_specialist(inp, ctx, node):
    task = ctx.get_memory("task", "?")
    print(f"  📊 [data_specialist] Data task: '{task}'")
    await asyncio.sleep(0.02)
    return {
        "stats":       {"records": 1204, "avg": 42.7},
        "handled_by":  "data_specialist",
    }


async def writer_agent(inp, ctx, node):
    # Grab whichever specialist ran — the other will have output=None (skipped)
    nlp_out  = inp["node_outputs"].get("nlp-node")  or {}
    data_out = inp["node_outputs"].get("data-node") or {}
    content  = nlp_out or data_out
    print(f"  ✍️  [writer_agent] Composing report from: {content.get('handled_by', 'specialist')}")
    return {
        "report":     f"Final report based on: {content.get('handled_by', 'specialist')}",
        "word_count": 420,
    }


for key, fn in [
    ("coordinator_fn", coordinator),
    ("nlp_fn",         nlp_specialist),
    ("data_fn",        data_specialist),
    ("writer_fn",      writer_agent),
]:
    HandlerRegistry.register(key, fn)


# ─── Matrix ───────────────────────────────────────────────────────────────────

matrix = ExecutionMatrix(
    name="multi-agent-coordination",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(id="coord",       name="coordinator",    type=NodeType.FUNCTION, handler="coordinator_fn"),
        Node(id="nlp-node",    name="nlp_specialist", type=NodeType.FUNCTION, handler="nlp_fn"),
        Node(id="data-node",   name="data_specialist",type=NodeType.FUNCTION, handler="data_fn"),
        Node(id="writer-node", name="writer_agent",   type=NodeType.FUNCTION, handler="writer_fn"),
    ],
    edges=[
        # Coordinator → specialist (conditional)
        Edge(**{
            "from": "coord", "to": "nlp-node",
            "condition": EdgeCondition(
                type=EdgeConditionType.EXPRESSION,
                expression="output['complexity'] > 0.6",
            ),
        }),
        Edge(**{
            "from": "coord", "to": "data-node",
            "condition": EdgeCondition(
                type=EdgeConditionType.EXPRESSION,
                expression="output['complexity'] <= 0.6",
            ),
        }),
        # Both specialists feed writer (only the one that ran will have output)
        Edge(**{"from": "nlp-node",  "to": "writer-node"}),
        Edge(**{"from": "data-node", "to": "writer-node"}),
    ],
)


async def run(task: str):
    engine  = AFMXEngine()
    context = ExecutionContext(input={"task": task})
    record  = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result  = await engine.execute(matrix, context, record)

    # FIX: output can be None when a node was skipped (key exists, value is None)
    # Use `or {}` instead of `.get("output", {})` to handle both missing and None
    writer_nr = result.node_results.get("writer-node") or {}
    writer    = writer_nr.get("output") or {}

    print(
        f"  → Status: {result.status} "
        f"| completed={result.completed_nodes} "
        f"| skipped={result.skipped_nodes} "
        f"| report: {writer.get('report', 'N/A')}\n"
    )


async def main():
    print("\n═════════════════════════════════════════════")
    print("  AFMX Example 07 — Multi-Agent Coordination")
    print("═════════════════════════════════════════════\n")

    print("  ── Task A: High complexity (→ nlp_specialist) ──")
    await run("Analyse the impact of LLMs on enterprise AI in 2026")

    print("  ── Task B: Low complexity (→ data_specialist) ──")
    await run("count records in database")


if __name__ == "__main__":
    asyncio.run(main())
