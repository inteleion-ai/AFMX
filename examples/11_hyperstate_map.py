# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
AFMX Example 11 — HyperState + MAP Memory Integrations
========================================================
Demonstrates wiring cognitive memory (HyperState) and verified context
(MAP) into AFMX's RETRIEVE-layer nodes.

Both integrations use mock objects so this runs without real servers.

Run:
    python examples/11_hyperstate_map.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import AFMXEngine, ExecutionContext, ExecutionMatrix, ExecutionMode, ExecutionRecord
from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, Node, NodeType


# ─── Mock HyperState memories ────────────────────────────────────────────────

_MOCK_MEMORIES = [
    {"content": "User is a quantitative finance expert with 10y experience", "score": 0.94},
    {"content": "User prefers Python and uses pandas for data analysis",       "score": 0.87},
    {"content": "User's risk tolerance is moderate, Sharpe ratio target > 1.5", "score": 0.81},
]

_MOCK_SIGNALS = {
    "complexity":        0.7,
    "recommended_model": "premium",
    "context_freshness": 0.92,
}


async def example_hyperstate_retrieve() -> None:
    """
    RETRIEVE-layer node calls HyperState for relevant memories.
    Result is passed to REASON node as context.
    """
    print("\n── Example 1: HyperState RETRIEVE → REASON ─────────────────────")

    import afmx.integrations.hyperstate as hs_module

    # Make hyperstate available without installing it
    hs_module._HYPERSTATE_AVAILABLE = True
    mock_client = AsyncMock()
    mock_client.query.return_value               = _MOCK_MEMORIES
    mock_client.get_routing_signals.return_value = _MOCK_SIGNALS

    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__  = AsyncMock(return_value=False)

    hs_module.AsyncHyperStateClient = MagicMock(return_value=mock_client_cm)

    from afmx.integrations.hyperstate import attach_hyperstate

    ok = attach_hyperstate(
        api_url="http://localhost:8000",
        api_key="hs_demo_key",
        default_context_id="finance-session-001",
        top_k=5,
    )
    print(f"  HyperState attached: {ok}")

    # Register a REASON handler that reads memories from context
    async def analyse_with_memory(node_input: Dict[str, Any], context: Any, node: Any) -> Dict[str, Any]:
        # Fetch memories from the hyperstate:retrieve result
        memories  = context.get_memory("hyperstate:memories") or []
        retrieved = node_input.get("node_outputs", {})

        # In real code: pass memories as context to the LLM
        memory_texts = [m["content"] for m in memories[:3]]
        return {
            "analysis":        "Risk score: 0.42 (MODERATE)",
            "confidence":      0.87,
            "context_used":    memory_texts,
            "routing_signals": _MOCK_SIGNALS,
        }

    HandlerRegistry.register("hyperstate:retrieve", HandlerRegistry._registry.get("hyperstate:retrieve") or
        AsyncMock(return_value={"memories": _MOCK_MEMORIES, "routing_signals": _MOCK_SIGNALS}))
    HandlerRegistry.register("finance_analyser", analyse_with_memory)

    matrix = ExecutionMatrix(
        name="hyperstate-demo",
        mode=ExecutionMode.DIAGONAL,
        nodes=[
            Node(
                id="retrieve", name="retrieve-context",
                type=NodeType.FUNCTION, handler="hyperstate:retrieve",
                cognitive_layer=CognitiveLayer.RETRIEVE, agent_role="QUANT",
                config={"params": {"query": "user risk preferences", "context_id": "finance-session-001"}},
            ),
            Node(
                id="analyse", name="analyse-portfolio",
                type=NodeType.AGENT, handler="finance_analyser",
                cognitive_layer=CognitiveLayer.REASON, agent_role="RISK_MANAGER",
            ),
        ],
        edges=[{"from_node": "retrieve", "to_node": "analyse"}],
    )

    engine  = AFMXEngine()
    context = ExecutionContext(input={"ticker": "AAPL", "portfolio_value": 1_000_000})
    record  = ExecutionRecord(
        matrix_id=matrix.id, matrix_name=matrix.name,
        context=context, matrix_snapshot=matrix.model_dump(),
    )

    result = await engine.execute(matrix, context, record)
    print(f"  Status:          {result.status}")
    print(f"  Completed nodes: {result.completed_nodes}/{result.total_nodes}")

    analyse_result = result.node_results.get("analyse", {})
    if isinstance(analyse_result, dict):
        output = analyse_result.get("output", {})
        if isinstance(output, dict):
            print(f"  Analysis:        {output.get('analysis', '?')}")
            print(f"  Confidence:      {output.get('confidence', '?')}")
            print(f"  Memory used:     {len(output.get('context_used', []))} items")


async def example_map_verified_context() -> None:
    """MAP integration — RETRIEVE node gets SHA-256 verified context."""
    print("\n── Example 2: MAP Verified Context ─────────────────────────────")

    import afmx.integrations.map_plugin as mp

    mp._MAP_AVAILABLE = True

    # Mock MAP data structures
    class MockUnit:
        id             = str(__import__("uuid").uuid4())
        content        = "AAPL Q4 2025 revenue: $124.3B (+5.2% YoY). Strong iPhone demand."
        content_hash   = "sha256:abc123"
        relevance_score = 0.91
        source_type    = "financial_report"
        provenance     = {"document": "AAPL-10Q-2025", "page": 12}

    class MockResult:
        units             = [MockUnit()]
        deterministic_key = "det_key_abc"

    class MockReport:
        valid    = True
        conflicts = []
        def model_dump(self): return {"valid": True, "conflicts": []}

    mp.RetrievalQuery     = MagicMock()
    mp.ConflictStrategy   = MagicMock()
    mp.ConflictStrategy.FILTER = "FILTER"

    mock_service = MagicMock()
    mock_service.retrieve = AsyncMock(return_value=MockResult())
    mock_service.validate = AsyncMock(return_value=(MockResult(), MockReport()))

    from afmx.integrations.map_plugin import attach_map
    ok = await attach_map(service=mock_service)
    print(f"  MAP attached: {ok}")

    # Verify handler is callable
    from afmx.core.executor import HandlerRegistry
    handler = HandlerRegistry.resolve("map:retrieve")
    print(f"  map:retrieve handler registered: {callable(handler)}")

    # Simulate a call
    node_input = {"params": {"query": "AAPL earnings Q4", "context_id": "earnings-session"}}
    result = await handler(node_input, MagicMock(), MagicMock(name="retrieve"))
    print(f"  Context units returned: {len(result.get('context_units', []))}")
    if result.get("context_units"):
        unit = result["context_units"][0]
        print(f"  Unit content:  {unit['content'][:60]}...")
        print(f"  Integrity hash: {unit['hash']}")


async def main() -> None:
    print("AFMX v1.3.0 — HyperState + MAP Memory Examples")
    print("=" * 60)
    await example_hyperstate_retrieve()
    await example_map_verified_context()
    print(f"\n{'=' * 60}")
    print("Done. In production:")
    print("  attach_hyperstate(api_url='http://hyperstate:8000', api_key='hs_...')")
    print("  await attach_map(service=await MAPService.create())")


if __name__ == "__main__":
    asyncio.run(main())
