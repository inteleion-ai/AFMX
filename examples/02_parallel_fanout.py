"""
AFMX Example 02 — Parallel Fan-Out + Fan-In
Three data sources queried in parallel, results merged by a single aggregator.

Topology:
                   ┌──► source_a ──┐
    start ─────────┼──► source_b ──┼──► aggregate
                   └──► source_c ──┘

Run:
    python examples/02_parallel_fanout.py
"""
import asyncio
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, ExecutionMode, HandlerRegistry, EventBus,
)
import logging
logging.basicConfig(level=logging.WARNING)  # Quiet for this example


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def source_a(inp, ctx, node):
    await asyncio.sleep(0.08)
    return {"source": "A", "data": [1, 2, 3], "latency_ms": 80}

async def source_b(inp, ctx, node):
    await asyncio.sleep(0.12)
    return {"source": "B", "data": [4, 5, 6], "latency_ms": 120}

async def source_c(inp, ctx, node):
    await asyncio.sleep(0.05)
    return {"source": "C", "data": [7, 8, 9], "latency_ms": 50}

async def aggregate(inp, ctx, node):
    outputs = inp["node_outputs"]
    all_data = []
    sources = []
    for key in ["node-a", "node-b", "node-c"]:
        out = outputs.get(key, {})
        all_data.extend(out.get("data", []))
        sources.append(out.get("source", "?"))
    return {
        "merged": all_data,
        "total": len(all_data),
        "sources": sources,
        "sum": sum(all_data),
    }

async def start_node(inp, ctx, node):
    return {"triggered": True, "input": inp.get("input")}

for key, fn in [
    ("start_fn", start_node), ("source_a", source_a),
    ("source_b", source_b), ("source_c", source_c), ("aggregate_fn", aggregate),
]:
    HandlerRegistry.register(key, fn)


# ─── Matrix ───────────────────────────────────────────────────────────────────

matrix = ExecutionMatrix(
    name="fan-out-fan-in",
    mode=ExecutionMode.HYBRID,   # Hybrid = batched parallel
    nodes=[
        Node(id="start", name="start", type=NodeType.FUNCTION, handler="start_fn"),
        Node(id="node-a", name="source_a", type=NodeType.FUNCTION, handler="source_a"),
        Node(id="node-b", name="source_b", type=NodeType.FUNCTION, handler="source_b"),
        Node(id="node-c", name="source_c", type=NodeType.FUNCTION, handler="source_c"),
        Node(id="agg", name="aggregate", type=NodeType.FUNCTION, handler="aggregate_fn"),
    ],
    edges=[
        Edge(**{"from": "start", "to": "node-a"}),
        Edge(**{"from": "start", "to": "node-b"}),
        Edge(**{"from": "start", "to": "node-c"}),
        Edge(**{"from": "node-a", "to": "agg"}),
        Edge(**{"from": "node-b", "to": "agg"}),
        Edge(**{"from": "node-c", "to": "agg"}),
    ],
    max_parallelism=3,
)


async def main():
    print("\n═══════════════════════════════════════════")
    print("  AFMX Example 02 — Parallel Fan-Out/In")
    print("═══════════════════════════════════════════\n")

    engine = AFMXEngine()
    context = ExecutionContext(input="parallel query")
    record = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)

    t0 = time.perf_counter()
    result = await engine.execute(matrix, context, record)
    elapsed = (time.perf_counter() - t0) * 1000

    agg_output = result.node_results.get("agg", {}).get("output", {})

    print(f"  Status      : {result.status}")
    print(f"  Wall time   : {elapsed:.1f}ms  (3 parallel sources)")
    print(f"  Nodes done  : {result.completed_nodes}/{result.total_nodes}")
    print(f"  Merged data : {agg_output.get('merged')}")
    print(f"  Sum         : {agg_output.get('sum')}")
    print(f"  Sources     : {agg_output.get('sources')}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
