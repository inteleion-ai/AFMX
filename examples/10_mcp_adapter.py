# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
AFMX Example 10 — MCP Adapter (Model Context Protocol)
=======================================================
Demonstrates connecting MCP servers to AFMX and executing their tools
inside a Cognitive Matrix.

This example uses mock MCP objects so it runs without a real MCP server
or the ``mcp`` package installed.  Swap the mock for a real call to
``from_server()`` or ``from_config()`` in production.

Contents
--------
1. Basic SSE server discovery and DIAGONAL execution
2. Multi-server desktop config with role assignment
3. Manual tool node construction with infer_cognitive_layer()
4. Standalone tool call via execute()

Run:
    python examples/10_mcp_adapter.py

Production (with real servers):
    pip install afmx[mcp]
    # Then replace the mock sections with real MCPAdapter calls.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)

from afmx import (
    AFMXEngine,
    ExecutionContext,
    ExecutionMatrix,
    ExecutionMode,
    ExecutionRecord,
    HandlerRegistry,
)
from afmx.adapters.mcp import (
    MCPAdapter,
    MCPServerConfig,
    _tool_to_dict,
    infer_cognitive_layer,
)
from afmx.models.node import CognitiveLayer, NodeType, RetryPolicy, TimeoutPolicy
from afmx.observability.events import AFMXEvent, EventBus, EventType

# ─── Helpers ──────────────────────────────────────────────────────────────────

_SECTION = "\n" + "─" * 70 + "\n"


def _section(title: str) -> None:
    print(f"{_SECTION}{title}{_SECTION}")


def _tool(name: str, description: str) -> Dict[str, Any]:
    """Build a minimal MCP tool dict (mirrors the tools/list response shape)."""
    return {
        "name":        name,
        "description": description,
        "inputSchema": {
            "type":       "object",
            "properties": {"input": {"type": "string"}},
            "required":   ["input"],
        },
    }


# ─── Mock MCP tool results ────────────────────────────────────────────────────
# These simulate what real MCP servers return.

_MOCK_FILESYSTEM_TOOLS = [
    _tool("read_file",    "Read the contents of a file at a given path"),
    _tool("write_file",   "Write content to a file at a given path"),
    _tool("list_files",   "List all files in a directory"),
    _tool("search_files", "Search for files matching a pattern"),
    _tool("delete_file",  "Delete a file at a given path"),
]

_MOCK_GITHUB_TOOLS = [
    _tool("search_repositories", "Search GitHub repositories"),
    _tool("create_issue",        "Create an issue in a GitHub repository"),
    _tool("list_pull_requests",  "List pull requests for a repository"),
    _tool("check_ci_status",     "Check CI pipeline status for a commit"),
]

_MOCK_SLACK_TOOLS = [
    _tool("send_message",  "Send a message to a Slack channel"),
    _tool("search_messages", "Search Slack messages"),
    _tool("watch_channel", "Watch a channel for new messages"),
    _tool("export_thread", "Export a thread as a summary report"),
]


# ─── Example 1: Basic SSE server discovery ───────────────────────────────────


async def example_1_sse_discovery() -> None:
    """
    Discover tools from an SSE MCP server and run them in a DIAGONAL matrix.

    In production: replace the mock with a real server URL.
        nodes = await adapter.from_server("http://localhost:3000")
    """
    _section("Example 1 — SSE Server Discovery + DIAGONAL Execution")

    # Register a pass-through handler for demonstration
    HandlerRegistry.register(
        "echo",
        lambda node_input, context, node: {
            "tool":   node.metadata.get("tool_name"),
            "layer":  node.cognitive_layer,
            "result": "ok (mocked)",
        },
    )

    adapter = MCPAdapter()

    # Mock out the actual network call to _discover_tools_sse
    with patch(
        "afmx.adapters.mcp._discover_tools_sse",
        new_callable=AsyncMock,
        return_value=_MOCK_FILESYSTEM_TOOLS,
    ):
        nodes = await adapter.from_server(
            "http://localhost:3000",
            server_name="filesystem",
            default_role="OPS",
        )

    print(f"  Discovered {len(nodes)} tools from filesystem server\n")
    print("  Tool → CognitiveLayer → AgentRole")
    print("  " + "─" * 42)
    for node in nodes:
        print(
            f"  {node.metadata['tool_name']:<24} "
            f"{node.cognitive_layer:<12} "
            f"{node.agent_role or '—'}"
        )

    # Layer summary
    from collections import Counter
    layer_counts = Counter(n.cognitive_layer for n in nodes)
    print(f"\n  Layer distribution: {dict(layer_counts)}")

    # Build and run a DIAGONAL matrix
    matrix = ExecutionMatrix(
        name="mcp-filesystem-demo",
        mode=ExecutionMode.DIAGONAL,
        nodes=nodes,
        edges=[],
    )

    # Override handlers so nodes actually execute (real servers would call the tool)
    for node in nodes:
        HandlerRegistry.register(
            node.handler,
            lambda ni, ctx, n: {
                "tool":   n.metadata.get("tool_name"),
                "layer":  n.cognitive_layer,
                "result": "mocked-ok",
            },
        )

    # Attach a layer observer
    bus = EventBus()
    layer_log: List[str] = []

    async def on_layer(event: AFMXEvent) -> None:
        layer_log.append(
            f"  [{event.type.value.upper():<18}] "
            f"layer={event.data.get('layer', '?'):<12} "
            + (f"batch={event.data.get('batch_size', '?')}"
               if event.type == EventType.LAYER_STARTED
               else f"success={event.data.get('success', '?')} "
                    f"failed={event.data.get('failed', '?')}")
        )

    bus.subscribe(EventType.LAYER_STARTED,   on_layer)
    bus.subscribe(EventType.LAYER_COMPLETED, on_layer)

    engine = AFMXEngine(event_bus=bus)
    ctx = ExecutionContext(input={"path": "/tmp/example"})
    rec = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=ctx,
        matrix_snapshot=matrix.model_dump(),
    )

    result = await engine.execute(matrix, ctx, rec)

    print(f"\n  Execution: {result.status} | "
          f"completed={result.completed_nodes}/{result.total_nodes} | "
          f"duration={result.duration_ms:.0f}ms")

    print("\n  Layer event log:")
    for line in layer_log:
        print(line)


# ─── Example 2: Multi-server desktop config ───────────────────────────────────


async def example_2_desktop_config() -> None:
    """
    Load all servers from a Claude Desktop config dict.
    Demonstrates role assignment per server.
    """
    _section("Example 2 — Claude Desktop Config (Multi-Server)")

    adapter = MCPAdapter()

    call_order: List[str] = []

    async def fake_discover_stdio(cfg: MCPServerConfig) -> List[Dict[str, Any]]:
        call_order.append(cfg.name)
        if cfg.name == "filesystem":
            return _MOCK_FILESYSTEM_TOOLS
        if cfg.name == "github":
            return _MOCK_GITHUB_TOOLS
        if cfg.name == "slack":
            return _MOCK_SLACK_TOOLS
        return []

    with patch("afmx.adapters.mcp._discover_tools_stdio", side_effect=fake_discover_stdio):
        nodes = await adapter.from_desktop_config(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-filesystem", "/"],
                    },
                    "github": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-github"],
                        "env": {"GITHUB_TOKEN": "ghp_xxx"},
                    },
                    "slack": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-slack"],
                    },
                }
            }
        )

    print(f"  Loaded {len(nodes)} tools from {len(call_order)} servers")
    print(f"  Server load order: {call_order}\n")

    # Show the layer distribution across all servers
    from collections import Counter
    layer_counter: Counter = Counter()
    server_counts: Counter = Counter()

    for node in nodes:
        layer_counter[node.cognitive_layer] += 1
        server = node.name.split(":")[0] if ":" in node.name else "unknown"
        server_counts[server] += 1

    print("  Cognitive layer distribution across all servers:")
    for layer, count in sorted(layer_counter.items()):
        bar = "█" * count
        print(f"    {layer:<12} {bar} ({count})")

    print("\n  Tools per server:")
    for server, count in server_counts.items():
        print(f"    {server:<14} {count} tools")


# ─── Example 3: Manual layer inference ────────────────────────────────────────


async def example_3_layer_inference() -> None:
    """
    Demonstrate the infer_cognitive_layer() function directly.
    Useful when building nodes manually or for custom servers.
    """
    _section("Example 3 — CognitiveLayer Inference Rules")

    test_cases = [
        # (tool_name, description)
        ("search_web",       "Search the internet for recent news"),
        ("fetch_url",        "Fetch and parse a URL's content"),
        ("read_database",    "Query a SQL database and return results"),
        ("write_file",       "Write content to a local file"),
        ("create_pr",        "Create a pull request on GitHub"),
        ("delete_records",   "Delete records matching a filter"),
        ("send_notification","Send a push notification to a user"),
        ("validate_schema",  "Validate a JSON document against a schema"),
        ("check_health",     "Check the health status of a service"),
        ("test_endpoint",    "Run integration tests against an API endpoint"),
        ("monitor_metrics",  "Watch system metrics and alert on anomalies"),
        ("observe_errors",   "Subscribe to the error log stream"),
        ("generate_report",  "Produce a PDF summary report"),
        ("export_to_csv",    "Export query results as a CSV file"),
        ("summarize_thread", "Summarise a Slack thread"),
        ("analyse_pattern",  "Analyse patterns in time-series data"),
        ("complex_calc",     "Perform a multi-step calculation"),
        ("process_data",     "Apply transformations to a dataset"),
    ]

    print(f"  {'Tool name':<28} {'Description excerpt':<38} {'→ Layer'}")
    print("  " + "─" * 80)
    for name, desc in test_cases:
        layer = infer_cognitive_layer(name, desc)
        desc_short = desc[:36] + "…" if len(desc) > 36 else desc
        print(f"  {name:<28} {desc_short:<38} {layer.value}")


# ─── Example 4: matrix_snapshot and resume ────────────────────────────────────


async def example_4_snapshot_resume() -> None:
    """
    Show that ad-hoc matrices (never saved to MatrixStore) can be resumed
    because POST /execute now captures matrix_snapshot in the ExecutionRecord.
    """
    _section("Example 4 — Ad-hoc Matrix Snapshot for Resume (v1.2.1 fix)")

    from afmx.models.execution import ExecutionRecord
    from afmx.models.matrix import ExecutionMatrix, ExecutionMode
    from afmx.models.node import Node, NodeType

    HandlerRegistry.register("demo_handler", lambda i, c, n: {"done": True})

    matrix = ExecutionMatrix(
        name="ad-hoc-demo",
        mode=ExecutionMode.SEQUENTIAL,
        nodes=[
            Node(id="n1", name="step-1", type=NodeType.FUNCTION, handler="demo_handler"),
            Node(id="n2", name="step-2", type=NodeType.FUNCTION, handler="demo_handler"),
        ],
        edges=[],
    )

    # Simulate what POST /execute now does
    rec = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=ExecutionContext(),
        matrix_snapshot=matrix.model_dump(),   # v1.2.1: captured at execution time
    )

    print("  ExecutionRecord created with matrix_snapshot:")
    print(f"    matrix_snapshot is None: {rec.matrix_snapshot is None}")
    print(f"    snapshot node count:     {len(rec.matrix_snapshot['nodes'])}")

    # Simulate the resume endpoint's fallback
    restored = ExecutionMatrix.model_validate(rec.matrix_snapshot)
    print(f"    restored matrix name:    {restored.name}")
    print(f"    restored matrix id:      {restored.id}")
    print(f"    restored node ids:       {[n['id'] for n in rec.matrix_snapshot['nodes']]}")

    print("\n  Resume endpoint will now work for this ad-hoc matrix ✓")
    print("  (Previously raised 404: matrix not in MatrixStore)")


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    print("\nAFMX v1.2.1 — MCP Adapter Examples")
    print("=" * 70)

    await example_1_sse_discovery()
    await example_2_desktop_config()
    await example_3_layer_inference()
    await example_4_snapshot_resume()

    print(f"\n{'=' * 70}")
    print("All examples complete.")
    print("\nNext steps:")
    print("  pip install afmx[mcp]")
    print("  # Start a real MCP server, then:")
    print("  # nodes = await MCPAdapter().from_server('http://localhost:3000')")
    print()


if __name__ == "__main__":
    asyncio.run(main())
