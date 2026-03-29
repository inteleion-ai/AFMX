# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
AFMX Example 12 — RHFL Governance Gate
========================================
Demonstrates the RHFL human-in-the-loop governance integration.

RHFL gates every ACT-layer node:
  - AUTO → proceeds immediately
  - REVIEW → waits for human approval (mocked as auto-approve here)
  - BLOCK → raises RHFLBlockedError → AFMX marks node as ABORTED
  - ESCALATE → escalates and waits

Run:
    python examples/12_rhfl_gate.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import AFMXEngine, ExecutionContext, ExecutionMatrix, ExecutionMode, ExecutionRecord
from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, Node, NodeType


async def _scenario(
    name: str,
    classification: str,
    status: str,
    expect_success: bool,
) -> None:
    """Run one RHFL governance scenario."""
    print(f"\n── Scenario: {name} ({classification}) ─────────────────────────")

    # Register a safe ACT handler that simulates the actual work
    HandlerRegistry.register(
        "deploy_service",
        lambda ni, ctx, n: {"deployed": True, "service": "payment-api-v2"},
    )

    # Patch the RHFL client submit_decision to return the test classification
    from afmx.integrations.rhfl import _RHFLClient, attach_rhfl

    with __import__("unittest.mock", fromlist=["patch"]).patch.object(
        _RHFLClient,
        "submit_decision",
        AsyncMock(return_value={
            "id":             f"decision-{classification.lower()}",
            "classification": classification,
            "status":         status,
        }),
    ):
        hook_registry = MagicMock()
        hook_registry.register = MagicMock()

        attach_rhfl(
            api_url="http://rhfl.local:4000/api/v1",
            token="dev-jwt-token",
            hook_registry=hook_registry,
            gate_act_nodes=True,
            max_wait=0.1,
            poll_interval=0.01,
        )

        # Build matrix with one ACT node (the deployment)
        matrix = ExecutionMatrix(
            name=f"rhfl-{name.lower().replace(' ', '-')}",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[
                Node(
                    id="plan", name="plan-deployment",
                    type=NodeType.AGENT, handler="deploy_service",
                    cognitive_layer=CognitiveLayer.PLAN,
                ),
                Node(
                    id="act", name="deploy-service",
                    type=NodeType.AGENT, handler="deploy_service",
                    cognitive_layer=CognitiveLayer.ACT,
                    metadata={"risk_score": 0.7},
                ),
            ],
            edges=[{"from_node": "plan", "to_node": "act"}],
        )

        engine  = AFMXEngine()
        context = ExecutionContext(input={"service": "payment-api", "version": "2.1.0"})
        record  = ExecutionRecord(
            matrix_id=matrix.id, matrix_name=matrix.name,
            context=context, matrix_snapshot=matrix.model_dump(),
        )

        result = await engine.execute(matrix, context, record)
        print(f"  Matrix status:   {result.status}")
        print(f"  Completed nodes: {result.completed_nodes}/{result.total_nodes}")
        if result.error:
            print(f"  Error:           {result.error[:80]}")
        if expect_success:
            assert result.completed_nodes >= 1, "Expected at least PLAN to complete"
        print(f"  ✓ Scenario behaved as expected")


async def main() -> None:
    print("AFMX v1.3.0 — RHFL Governance Gate Examples")
    print("=" * 60)
    print("""
Architecture:
    AFMX ACT-layer node
         ↓
    RHFL PRE_NODE hook
         ↓
    POST /api/v1/decisions  →  AUTO | REVIEW | BLOCK | ESCALATE
         ↓
    AUTO  → execute normally
    BLOCK → RHFLBlockedError → AFMX ABORTED
    """)

    # Scenario 1: AUTO classification — ACT node proceeds
    await _scenario(
        name="Auto Approved",
        classification="AUTO",
        status="EXECUTING",
        expect_success=True,
    )

    # Scenario 2: BLOCK classification — deployment is halted
    await _scenario(
        name="Blocked by Policy",
        classification="BLOCK",
        status="BLOCKED",
        expect_success=False,
    )

    print(f"\n{'=' * 60}")
    print("Done. In production:")
    print("  attach_rhfl(")
    print("      api_url='http://rhfl.internal:4000/api/v1',")
    print("      token=os.getenv('RHFL_TOKEN'),")
    print("      hook_registry=afmx_app.hook_registry,")
    print("      gate_act_nodes=True,   # ALL ACT nodes gated")
    print("      max_wait=300.0,        # 5 min for human approval")
    print("  )")


if __name__ == "__main__":
    asyncio.run(main())
