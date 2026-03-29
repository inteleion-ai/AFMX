# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
AFMX Example 13 — Enterprise Adapters
========================================
Demonstrates Semantic Kernel, Google ADK, and Amazon Bedrock adapters.
Uses mock objects throughout — no credentials or installs needed.

Run:
    python examples/13_enterprise_adapters.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, NodeType


# ─────────────────────────────────────────────────────────────────────────────
# Semantic Kernel
# ─────────────────────────────────────────────────────────────────────────────


async def example_semantic_kernel() -> None:
    print("\n── Semantic Kernel Adapter ─────────────────────────────────────")

    # Build a mock Kernel
    mock_kernel = MagicMock()

    # Mock the KernelFunction
    mock_fn = MagicMock()
    mock_fn.name        = "summarise"
    mock_fn.plugin_name = "writer"
    mock_fn.description = "Summarise a document"

    # Mock the invoke result
    mock_result = MagicMock()
    mock_result.value = "Executive summary: Strong Q4 performance, revenue up 5.2%."
    mock_kernel.invoke = AsyncMock(return_value=mock_result)

    # Build node (patch the _require_sk guard)
    with patch("afmx.adapters.semantic_kernel._require_sk"):
        with patch("afmx.adapters.semantic_kernel.KernelArguments", dict, create=True):
            from afmx.adapters.semantic_kernel import SemanticKernelAdapter

            adapter = SemanticKernelAdapter(kernel=mock_kernel)
            node    = adapter.function_node(
                mock_fn,
                node_name="sk-summariser",
                cognitive_layer=CognitiveLayer.REASON,
                agent_role="ANALYST",
            )

    print(f"  Node name:        {node.name}")
    print(f"  Node type:        {node.type}")
    print(f"  Cognitive layer:  {node.cognitive_layer}")
    print(f"  Agent role:       {node.agent_role}")
    print(f"  Handler key:      {node.handler}")
    print(f"  Plugin/function:  {node.metadata.get('plugin_name')}/{node.metadata.get('function_name')}")

    # Execute the handler
    handler    = HandlerRegistry.resolve(node.handler)
    node_input = {"input": "Q4 earnings report: Revenue $124.3B, EPS $2.41", "params": {}}
    output     = await handler(node_input, MagicMock(), node)
    print(f"  Output:           {output.get('result', '?')[:70]}...")
    print("  ✓ Semantic Kernel adapter working")


# ─────────────────────────────────────────────────────────────────────────────
# Google ADK
# ─────────────────────────────────────────────────────────────────────────────


async def example_google_adk() -> None:
    print("\n── Google ADK Adapter ──────────────────────────────────────────")

    # Build mock ADK tool
    mock_tool = MagicMock()
    mock_tool.name        = "search_web"
    mock_tool.description = "Search the web for current information"

    # Build mock ADK agent
    mock_agent = MagicMock()
    mock_agent.name                  = "researcher"
    mock_agent.__class__.__name__    = "LlmAgent"
    mock_agent.instruction           = "Research thoroughly and cite sources."

    with patch("afmx.adapters.google_adk._require_adk"):
        from afmx.adapters.google_adk import GoogleADKAdapter

        adapter  = GoogleADKAdapter(app_name="finance-app")
        tool_node  = adapter.tool_node(mock_tool, agent_role="OPS")
        agent_node = adapter.agent_node(mock_agent, agent_role="ANALYST")

    print(f"  Tool node:   {tool_node.name} [{tool_node.cognitive_layer}] type={tool_node.type}")
    print(f"  Agent node:  {agent_node.name} [{agent_node.cognitive_layer}] type={agent_node.type}")

    # Verify tool node layer is RETRIEVE (from 'search_web' keyword)
    assert tool_node.cognitive_layer == CognitiveLayer.RETRIEVE.value, (
        f"Expected RETRIEVE, got {tool_node.cognitive_layer}"
    )
    print("  ✓ CognitiveLayer inferred correctly for ADK tool")

    # Execute tool handler with mock async tool
    mock_tool.__call__ = AsyncMock(return_value={"results": ["Apple revenue $124B"]})
    mock_tool.run_async = AsyncMock(return_value={"results": ["Apple revenue $124B"]})

    handler    = HandlerRegistry.resolve(tool_node.handler)
    node_input = {"input": "AAPL Q4 2025 earnings", "params": {}}
    output     = await handler(node_input, MagicMock(), tool_node)
    print(f"  Tool output: {output}")
    print("  ✓ Google ADK adapter working")


# ─────────────────────────────────────────────────────────────────────────────
# Amazon Bedrock
# ─────────────────────────────────────────────────────────────────────────────


async def example_bedrock() -> None:
    print("\n── Amazon Bedrock Adapter ──────────────────────────────────────")

    mock_session = MagicMock()

    with patch("afmx.adapters.bedrock._require_boto3"):
        from afmx.adapters.bedrock import BedrockAdapter, _build_invoke_body, _extract_response_text

        adapter = BedrockAdapter.__new__(BedrockAdapter)
        adapter._session = mock_session
        adapter._region  = "us-east-1"

        # Model node — Claude Haiku (RETRIEVE tier — cheap)
        haiku_node = adapter.model_node(
            "anthropic.claude-3-haiku-20240307-v1:0",
            node_name="haiku-retriever",
            agent_role="OPS",
        )

        # Model node — Claude 3.5 Sonnet (REASON tier — premium)
        sonnet_node = adapter.model_node(
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            node_name="sonnet-analyst",
            cognitive_layer=CognitiveLayer.REASON,
            agent_role="ANALYST",
        )

        # Bedrock Agent node
        agent_node = adapter.agent_node(
            agent_id="RISK_AGENT_001",
            agent_alias_id="TSTALIASID",
            node_name="risk-agent",
            cognitive_layer=CognitiveLayer.REASON,
            agent_role="RISK_MANAGER",
        )

    print(f"  Haiku node:   {haiku_node.name}  [{haiku_node.cognitive_layer}]  (cheap tier)")
    print(f"  Sonnet node:  {sonnet_node.name} [{sonnet_node.cognitive_layer}]  (premium tier)")
    print(f"  Agent node:   {agent_node.name}  [{agent_node.cognitive_layer}]  type={agent_node.type}")

    assert haiku_node.cognitive_layer  == CognitiveLayer.RETRIEVE.value
    assert sonnet_node.cognitive_layer == CognitiveLayer.REASON.value

    # Verify Claude request body structure
    body = _build_invoke_body(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        prompt="What is the risk score for AAPL?",
        system_prompt="You are a risk analyst.",
        max_tokens=512,
        temperature=0.0,
    )
    assert "messages" in body
    assert body["system"] == "You are a risk analyst."
    print("  ✓ Claude request body format correct")

    # Verify response extraction
    raw_response = {"content": [{"text": "Risk score: 0.42 (MODERATE)"}]}
    text = _extract_response_text("anthropic.claude-3-5-sonnet", raw_response)
    assert text == "Risk score: 0.42 (MODERATE)"
    print(f"  ✓ Response extraction: '{text}'")
    print("  ✓ Amazon Bedrock adapter working")


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    print("AFMX v1.3.0 — Enterprise Adapters")
    print("=" * 60)

    await example_semantic_kernel()
    await example_google_adk()
    await example_bedrock()

    print(f"\n{'=' * 60}")
    print("All examples passed. Production install:")
    print()
    print("  pip install afmx[semantic-kernel]  # Microsoft SK")
    print("  pip install afmx[google-adk]       # Google ADK")
    print("  pip install afmx[bedrock]           # AWS Bedrock")
    print("  pip install afmx[adapters]          # All adapters")
    print()
    print("Usage:")
    print("  from afmx.adapters import SemanticKernelAdapter, GoogleADKAdapter, BedrockAdapter")


if __name__ == "__main__":
    asyncio.run(main())
