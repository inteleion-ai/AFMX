"""
AFMX Example 01 — Sequential Flow
A simple 3-node pipeline: fetch → enrich → summarize.
Demonstrates context passing, variable resolution, and output chaining.

Run:
    cd AFMX
    python examples/01_sequential_flow.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, ExecutionMode,
    HandlerRegistry, EventBus,
)
from afmx.observability.events import LoggingEventHandler
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


# ─── Step 1: Register Handlers ────────────────────────────────────────────────

async def fetch_handler(inp: dict, ctx, node) -> dict:
    """Simulates fetching data from an external source."""
    query = inp["params"].get("query") or inp.get("input", "default")
    print(f"  🔍 [fetch] Searching for: '{query}'")
    await asyncio.sleep(0.05)  # Simulate network call
    return {
        "query": query,
        "results": [
            {"title": f"Result 1 for {query}", "score": 0.95},
            {"title": f"Result 2 for {query}", "score": 0.87},
            {"title": f"Result 3 for {query}", "score": 0.72},
        ],
        "total": 3,
    }


async def enrich_handler(inp: dict, ctx, node) -> dict:
    """Adds metadata to search results using upstream output."""
    # Access the output of the previous node via node_outputs
    fetch_output = inp["node_outputs"].get("fetch-node", {})
    results = fetch_output.get("results", [])
    print(f"  ✨ [enrich] Enriching {len(results)} results...")
    enriched = [
        {**r, "relevance": "HIGH" if r["score"] > 0.9 else "MEDIUM", "source": "web"}
        for r in results
    ]
    return {"enriched": enriched, "count": len(enriched)}


async def summarize_handler(inp: dict, ctx, node) -> dict:
    """Summarizes the enriched results."""
    enrich_output = inp["node_outputs"].get("enrich-node", {})
    enriched = enrich_output.get("enriched", [])
    high_relevance = [r for r in enriched if r.get("relevance") == "HIGH"]
    print(f"  📝 [summarize] Found {len(high_relevance)} high-relevance results")
    return {
        "summary": f"Found {len(enriched)} results, {len(high_relevance)} high-relevance.",
        "top_result": enriched[0]["title"] if enriched else None,
    }


HandlerRegistry.register("fetch_handler", fetch_handler)
HandlerRegistry.register("enrich_handler", enrich_handler)
HandlerRegistry.register("summarize_handler", summarize_handler)


# ─── Step 2: Define the Matrix ────────────────────────────────────────────────

matrix = ExecutionMatrix(
    name="fetch-enrich-summarize",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(
            id="fetch-node",
            name="fetch",
            type=NodeType.FUNCTION,
            handler="fetch_handler",
        ),
        Node(
            id="enrich-node",
            name="enrich",
            type=NodeType.FUNCTION,
            handler="enrich_handler",
        ),
        Node(
            id="summarize-node",
            name="summarize",
            type=NodeType.FUNCTION,
            handler="summarize_handler",
        ),
    ],
    edges=[
        Edge(**{"from": "fetch-node", "to": "enrich-node"}),
        Edge(**{"from": "enrich-node", "to": "summarize-node"}),
    ],
    global_timeout_seconds=30.0,
)


# ─── Step 3: Execute ──────────────────────────────────────────────────────────

async def main():
    print("\n═══════════════════════════════════════════")
    print("  AFMX Example 01 — Sequential Flow")
    print("═══════════════════════════════════════════\n")

    event_bus = EventBus()
    engine = AFMXEngine(event_bus=event_bus)

    context = ExecutionContext(input="autonomous agents 2026")
    record = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)

    print("▶ Executing matrix...\n")
    result = await engine.execute(matrix, context, record)

    print(f"\n{'─' * 45}")
    print(f"  Status       : {result.status}")
    print(f"  Duration     : {result.duration_ms:.1f}ms")
    print(f"  Completed    : {result.completed_nodes}/{result.total_nodes} nodes")

    final_output = result.node_results.get("summarize-node", {}).get("output", {})
    print(f"  Summary      : {final_output.get('summary', 'N/A')}")
    print(f"  Top result   : {final_output.get('top_result', 'N/A')}")
    print(f"{'─' * 45}\n")


if __name__ == "__main__":
    asyncio.run(main())
