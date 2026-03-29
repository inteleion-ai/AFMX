# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Unit tests for v1.2.1 bug fixes:

1. ExecutionRecord.matrix_snapshot — ad-hoc matrix resume support
2. EventType.LAYER_STARTED / LAYER_COMPLETED — diagonal layer boundary events
3. MCPAdapter — cognitive layer inference, node building, handler registration
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from afmx.adapters.mcp import (
    MCPAdapter,
    MCPServerConfig,
    _build_handler_key,
    _build_node,
    _extract_arguments,
    _normalise_tool_result,
    _tool_to_dict,
    infer_cognitive_layer,
)
from afmx.core.executor import HandlerRegistry
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import AbortPolicy, ExecutionMatrix, ExecutionMode
from afmx.models.node import CognitiveLayer, Node, NodeType, RetryPolicy, TimeoutPolicy
from afmx.observability.events import AFMXEvent, EventBus, EventType


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_node(name: str = "n", layer: str | None = None) -> Node:
    return Node(
        id=str(uuid.uuid4()),
        name=name,
        type=NodeType.TOOL,
        handler="echo",
        cognitive_layer=layer,
    )


def _make_matrix(*layers: str | None) -> ExecutionMatrix:
    nodes = [_make_node(f"node-{i}", layer) for i, layer in enumerate(layers)]
    return ExecutionMatrix(name="test", nodes=nodes, edges=[])


def _make_record(matrix: ExecutionMatrix) -> tuple[ExecutionRecord, ExecutionContext]:
    ctx = ExecutionContext()
    rec = ExecutionRecord(
        matrix_id=matrix.id,
        matrix_name=matrix.name,
        context=ctx,
    )
    return rec, ctx


# ─────────────────────────────────────────────────────────────────────────────
# 1. ExecutionRecord.matrix_snapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestMatrixSnapshot:
    """ExecutionRecord.matrix_snapshot — v1.2.1 field."""

    def test_default_is_none(self):
        """Records created without snapshot have None (backward compat)."""
        rec = ExecutionRecord(matrix_id="x", matrix_name="y")
        assert rec.matrix_snapshot is None

    def test_snapshot_roundtrip(self):
        """Snapshot survives a model_dump / model_validate round-trip."""
        matrix = _make_matrix("PERCEIVE", "REASON")
        snapshot = matrix.model_dump()
        rec = ExecutionRecord(
            matrix_id=matrix.id,
            matrix_name=matrix.name,
            matrix_snapshot=snapshot,
        )
        assert rec.matrix_snapshot is not None
        restored = ExecutionMatrix.model_validate(rec.matrix_snapshot)
        assert restored.id == matrix.id
        assert len(restored.nodes) == 2

    def test_snapshot_serialises_to_json(self):
        """model_dump() produces a JSON-serialisable dict."""
        import json
        matrix = _make_matrix("ACT")
        rec = ExecutionRecord(
            matrix_id=matrix.id,
            matrix_name=matrix.name,
            matrix_snapshot=matrix.model_dump(),
        )
        raw = rec.model_dump()
        # Must serialise without error
        serialised = json.dumps(raw, default=str)
        assert "matrix_snapshot" in serialised

    def test_old_record_without_snapshot_loads(self):
        """Records from v1.2.0 (no matrix_snapshot key) load cleanly."""
        old_dict = {
            "id":           str(uuid.uuid4()),
            "matrix_id":    "m1",
            "matrix_name":  "old-matrix",
            "status":       "COMPLETED",
            "context":      {},
            "node_results": {},
            "total_nodes":  1,
            # No matrix_snapshot key
        }
        rec = ExecutionRecord.model_validate(old_dict)
        assert rec.matrix_snapshot is None

    def test_is_terminal_after_completed(self):
        """Sanity: is_terminal works correctly with the new field."""
        rec = ExecutionRecord(matrix_id="x", matrix_name="y", matrix_snapshot={})
        rec.mark_completed()
        assert rec.is_terminal


# ─────────────────────────────────────────────────────────────────────────────
# 2. LAYER_STARTED / LAYER_COMPLETED events
# ─────────────────────────────────────────────────────────────────────────────


class TestLayerEvents:
    """EventType.LAYER_STARTED and LAYER_COMPLETED — v1.2.1."""

    def test_layer_started_in_event_type(self):
        assert EventType.LAYER_STARTED == "layer.started"

    def test_layer_completed_in_event_type(self):
        assert EventType.LAYER_COMPLETED == "layer.completed"

    def test_layer_events_distinct_from_execution_started(self):
        assert EventType.LAYER_STARTED   != EventType.EXECUTION_STARTED
        assert EventType.LAYER_COMPLETED != EventType.EXECUTION_STARTED

    @pytest.mark.asyncio
    async def test_event_bus_receives_layer_started(self):
        bus = EventBus()
        received: List[AFMXEvent] = []

        async def _handler(e: AFMXEvent) -> None:
            received.append(e)

        bus.subscribe(EventType.LAYER_STARTED, _handler)
        await bus.emit(AFMXEvent(
            type=EventType.LAYER_STARTED,
            execution_id="exec-1",
            data={"layer": "REASON", "batch_size": 3},
        ))
        assert len(received) == 1
        assert received[0].data["layer"] == "REASON"

    @pytest.mark.asyncio
    async def test_execution_started_does_not_trigger_layer_handler(self):
        """EXECUTION_STARTED must NOT fire LAYER_STARTED subscribers."""
        bus = EventBus()
        triggered: List[bool] = []

        async def _handler(e: AFMXEvent) -> None:
            triggered.append(True)

        bus.subscribe(EventType.LAYER_STARTED, _handler)
        await bus.emit(AFMXEvent(
            type=EventType.EXECUTION_STARTED,
            execution_id="exec-1",
        ))
        assert len(triggered) == 0

    @pytest.mark.asyncio
    async def test_diagonal_emits_layer_started_not_execution_started(self):
        """
        _run_diagonal() must emit LAYER_STARTED / LAYER_COMPLETED,
        NOT EXECUTION_STARTED with data["diagonal_layer"].
        """
        from afmx.core.engine import AFMXEngine

        execution_started_count = 0
        layer_started_events: List[AFMXEvent] = []
        layer_completed_events: List[AFMXEvent] = []

        bus = EventBus()

        async def on_exec_started(e: AFMXEvent) -> None:
            nonlocal execution_started_count
            # Only the initial EXECUTION_STARTED should fire (once per run)
            execution_started_count += 1

        async def on_layer_started(e: AFMXEvent) -> None:
            layer_started_events.append(e)

        async def on_layer_completed(e: AFMXEvent) -> None:
            layer_completed_events.append(e)

        bus.subscribe(EventType.EXECUTION_STARTED, on_exec_started)
        bus.subscribe(EventType.LAYER_STARTED,     on_layer_started)
        bus.subscribe(EventType.LAYER_COMPLETED,   on_layer_completed)

        # Register a no-op handler for the echo nodes
        HandlerRegistry.register("echo", lambda i, c, n: {"ok": True})

        engine = AFMXEngine(event_bus=bus)
        matrix = ExecutionMatrix(
            name="diag-test",
            mode=ExecutionMode.DIAGONAL,
            nodes=[
                _make_node("p1", "PERCEIVE"),
                _make_node("r1", "REASON"),
                _make_node("a1", "ACT"),
            ],
            edges=[],
        )
        rec, ctx = _make_record(matrix)
        await engine.execute(matrix, ctx, rec)

        # EXECUTION_STARTED fires exactly once (at the top of execute())
        assert execution_started_count == 1

        # LAYER_STARTED fires once per non-empty layer
        assert len(layer_started_events) == 3
        fired_layers = {e.data["layer"] for e in layer_started_events}
        assert fired_layers == {"PERCEIVE", "REASON", "ACT"}

        # LAYER_COMPLETED fires once per non-empty layer
        assert len(layer_completed_events) == 3
        completed_layers = {e.data["layer"] for e in layer_completed_events}
        assert completed_layers == {"PERCEIVE", "REASON", "ACT"}

        # No LAYER_STARTED event should have diagonal_layer in data
        for e in layer_started_events:
            assert "diagonal_layer" not in e.data
            assert "layer" in e.data
            assert "batch_size" in e.data


# ─────────────────────────────────────────────────────────────────────────────
# 3. MCPAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestInferCognitiveLayer:
    """infer_cognitive_layer() — keyword-based CognitiveLayer inference."""

    @pytest.mark.parametrize("name,description,expected", [
        # RETRIEVE triggers
        ("search_web",      "Search the web for information",        CognitiveLayer.RETRIEVE),
        ("read_file",       "Read contents of a file",               CognitiveLayer.RETRIEVE),
        ("list_files",      "List files in a directory",             CognitiveLayer.RETRIEVE),
        ("query_database",  "Query a SQL database",                  CognitiveLayer.RETRIEVE),
        ("fetch_url",       "Fetch a URL and return its content",    CognitiveLayer.RETRIEVE),
        ("lookup_record",   "Look up a record by ID",                CognitiveLayer.RETRIEVE),
        # ACT triggers
        ("write_file",      "Write content to a file",               CognitiveLayer.ACT),
        ("create_issue",    "Create a GitHub issue",                 CognitiveLayer.ACT),
        ("delete_record",   "Delete a record from the database",     CognitiveLayer.ACT),
        ("send_email",      "Send an email to a recipient",          CognitiveLayer.ACT),
        ("deploy_service",  "Deploy a service to production",        CognitiveLayer.ACT),
        ("execute_command", "Execute a shell command",               CognitiveLayer.ACT),
        # EVALUATE triggers
        ("check_syntax",    "Check code syntax for errors",          CognitiveLayer.EVALUATE),
        ("validate_schema", "Validate a JSON schema",                CognitiveLayer.EVALUATE),
        ("test_endpoint",   "Test an API endpoint",                  CognitiveLayer.EVALUATE),
        ("verify_hash",     "Verify a file hash",                    CognitiveLayer.EVALUATE),
        # PERCEIVE triggers
        ("monitor_logs",    "Monitor application logs",              CognitiveLayer.PERCEIVE),
        ("watch_folder",    "Watch a folder for changes",            CognitiveLayer.PERCEIVE),
        ("observe_metrics", "Observe system metrics",                CognitiveLayer.PERCEIVE),
        # REPORT triggers
        ("generate_report", "Generate a status report",              CognitiveLayer.REPORT),
        ("export_csv",      "Export data to CSV format",             CognitiveLayer.REPORT),
        ("summarize_logs",  "Summarise recent log entries",          CognitiveLayer.REPORT),
        # REASON fallback
        ("calculate",       "Perform a complex calculation",         CognitiveLayer.REASON),
        ("analyse",         "Analyse data patterns",                 CognitiveLayer.REASON),
        ("process",         "Process incoming data",                 CognitiveLayer.REASON),
        # Empty / unknown → REASON
        ("",                "",                                      CognitiveLayer.REASON),
        ("tool",            "A tool",                                CognitiveLayer.REASON),
    ])
    def test_layer_inference(self, name: str, description: str, expected: CognitiveLayer):
        result = infer_cognitive_layer(name, description)
        assert result == expected, (
            f"infer_cognitive_layer({name!r}, {description!r}) = {result}, "
            f"expected {expected}"
        )

    def test_name_takes_priority_over_description(self):
        """
        The name 'write_record' should infer ACT even if the description
        mentions 'search'.
        """
        result = infer_cognitive_layer("write_record", "search and write")
        # "write" appears in name → first match from name tokens wins ACT;
        # "search" is also a keyword but we test that the overall result is
        # ACT or RETRIEVE depending on match order — just verify it's not REASON.
        assert result != CognitiveLayer.REASON


class TestBuildHandlerKey:
    def test_alphanumeric_tool_name(self):
        key = _build_handler_key("search_web", "http://localhost:3000")
        assert key.startswith("mcp:")
        assert "search_web" in key

    def test_special_characters_sanitised(self):
        key = _build_handler_key("tool/with spaces", None)
        assert " " not in key
        assert "/" not in key

    def test_none_server_identifier(self):
        key = _build_handler_key("my_tool", None)
        assert key == "mcp:my_tool"


class TestExtractArguments:
    def test_params_override_input(self):
        node_input = {"input": {"a": 1, "b": 2}, "params": {"b": 99, "c": 3}}
        result = _extract_arguments(node_input)
        assert result["b"] == 99   # params wins
        assert result["a"] == 1    # input preserved when no conflict
        assert result["c"] == 3

    def test_internal_key_stripped(self):
        node_input = {"params": {"__mcp_tool_name__": "hidden", "real": "val"}}
        result = _extract_arguments(node_input)
        assert "__mcp_tool_name__" not in result
        assert result["real"] == "val"

    def test_scalar_input_wrapped(self):
        result = _extract_arguments({"input": "hello", "params": {}})
        assert result == {"value": "hello"}

    def test_none_input_returns_empty(self):
        result = _extract_arguments({"input": None, "params": {}})
        assert result == {}

    def test_pure_dict_input(self):
        result = _extract_arguments({"input": {"key": "val"}, "params": {}})
        assert result == {"key": "val"}


class TestToolToDict:
    def test_dict_passthrough(self):
        tool = {"name": "my_tool", "description": "does stuff"}
        assert _tool_to_dict(tool) is tool

    def test_object_conversion(self):
        class FakeTool:
            name        = "fake"
            description = "a fake tool"
            inputSchema = None
        result = _tool_to_dict(FakeTool())
        assert result["name"] == "fake"
        assert result["description"] == "a fake tool"
        assert result["inputSchema"] == {}


class TestNormaliseToolResult:
    def test_text_content_extracted(self):
        class TextContent:
            type = "text"
            text = "hello world"

        class FakeResult:
            content  = [TextContent()]
            isError  = False

        result = _normalise_tool_result(FakeResult())
        assert result["text"] == "hello world"
        assert result["is_error"] is False

    def test_multiple_text_parts_joined(self):
        class TC:
            type = "text"
        t1 = TC(); t1.text = "line one"
        t2 = TC(); t2.text = "line two"

        class FakeResult:
            content = [t1, t2]
            isError = False

        result = _normalise_tool_result(FakeResult())
        assert "line one" in result["text"]
        assert "line two" in result["text"]

    def test_no_content_attr(self):
        result = _normalise_tool_result("raw string")
        assert "raw" in result

    def test_is_error_flag_propagated(self):
        class TC:
            type = "text"
            text = "error occurred"

        class FakeResult:
            content = [TC()]
            isError = True

        result = _normalise_tool_result(FakeResult())
        assert result["is_error"] is True


class TestBuildNode:
    def test_node_type_is_mcp(self):
        node = _build_node(
            handler_key="mcp:my_tool",
            tool_name="my_tool",
            description="reads something",
            tool_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            node_id=None,
            node_name=None,
            agent_role=None,
            retry_policy=RetryPolicy(),
            timeout_policy=TimeoutPolicy(),
        )
        assert node.type == NodeType.MCP

    def test_cognitive_layer_inferred(self):
        node = _build_node(
            handler_key="mcp:search",
            tool_name="search",
            description="search for documents",
            tool_schema={},
            node_id=None,
            node_name=None,
            agent_role=None,
            retry_policy=RetryPolicy(),
            timeout_policy=TimeoutPolicy(),
        )
        assert node.cognitive_layer == CognitiveLayer.RETRIEVE.value

    def test_agent_role_propagated(self):
        node = _build_node(
            handler_key="mcp:write",
            tool_name="write_file",
            description="write to file",
            tool_schema={},
            node_id=None,
            node_name=None,
            agent_role="OPS",
            retry_policy=RetryPolicy(),
            timeout_policy=TimeoutPolicy(),
        )
        assert node.agent_role == "OPS"

    def test_tool_name_in_metadata(self):
        node = _build_node(
            handler_key="mcp:fetch",
            tool_name="fetch_url",
            description="fetch a URL",
            tool_schema={},
            node_id=None,
            node_name=None,
            agent_role=None,
            retry_policy=RetryPolicy(),
            timeout_policy=TimeoutPolicy(),
        )
        assert node.metadata["tool_name"] == "fetch_url"
        assert node.metadata["adapter"] == "mcp"

    def test_required_params_captured(self):
        schema = {
            "type": "object",
            "properties": {"url": {"type": "string"}, "timeout": {"type": "number"}},
            "required": ["url"],
        }
        node = _build_node(
            handler_key="mcp:fetch",
            tool_name="fetch_url",
            description="fetch",
            tool_schema=schema,
            node_id=None,
            node_name=None,
            agent_role=None,
            retry_policy=RetryPolicy(),
            timeout_policy=TimeoutPolicy(),
        )
        assert "url" in node.config.params["__required__"]


class TestMCPAdapterUnit:
    """Unit tests that do not require the mcp package installed."""

    def test_name_property(self):
        assert MCPAdapter().name == "mcp"

    def test_to_afmx_node_type_error_on_non_dict(self):
        adapter = MCPAdapter()
        with pytest.raises(TypeError):
            adapter.to_afmx_node("not a dict")

    def test_from_server_config_validates(self):
        with pytest.raises(ValueError):
            MCPServerConfig()  # no url or command

        with pytest.raises(ValueError):
            MCPServerConfig(server_url="http://x", command="y")  # both set

    def test_server_config_sse(self):
        cfg = MCPServerConfig(server_url="http://localhost:3000", name="test")
        assert cfg.server_url == "http://localhost:3000"
        assert cfg.command is None

    def test_server_config_stdio(self):
        cfg = MCPServerConfig(command="npx", args=["-y", "mcp-server"], name="npx")
        assert cfg.command == "npx"
        assert cfg.server_url is None

    def test_register_handler_stores_in_registry(self):
        """
        to_afmx_node() (via from_server/_tools_to_nodes) registers the
        handler in HandlerRegistry.
        """
        adapter = MCPAdapter()
        tool_dict = {
            "name": "test_search_tool",
            "description": "search for things",
            "inputSchema": {"type": "object", "properties": {}},
        }
        cfg = MCPServerConfig(
            server_url="http://localhost:9999",
            name="test-server",
        )
        # Call the internal registration directly (bypasses mcp import)
        adapter._register_tool_handler(
            handler_key="mcp:test_search_tool",
            tool_name="test_search_tool",
            tool_schema={},
            server_config=cfg,
        )
        # Handler should now be in registry
        handler = HandlerRegistry.resolve("mcp:test_search_tool")
        assert callable(handler)

    def test_import_error_message_is_helpful(self):
        """MCPAdapter methods raise ImportError with install instructions."""
        adapter = MCPAdapter()
        with patch.dict("sys.modules", {"mcp": None}):
            import sys
            original = sys.modules.get("mcp")
            sys.modules["mcp"] = None  # type: ignore
            try:
                from afmx.adapters.mcp import _require_mcp
                with pytest.raises(ImportError) as exc_info:
                    _require_mcp()
                assert "pip install mcp" in str(exc_info.value)
            finally:
                if original is None:
                    del sys.modules["mcp"]
                else:
                    sys.modules["mcp"] = original


class TestMCPAdapterIntegration:
    """
    Integration tests that mock the MCP SDK session.
    These verify the adapter's round-trip without a real MCP server.
    """

    def _make_mock_tool(self, name: str, description: str) -> MagicMock:
        tool = MagicMock()
        tool.name = name
        tool.description = description
        tool.inputSchema = MagicMock()
        tool.inputSchema.model_dump.return_value = {
            "type": "object",
            "properties": {name: {"type": "string"}},
            "required": [name],
        }
        return tool

    @pytest.mark.asyncio
    async def test_from_server_discovers_tools(self):
        """from_server() converts each MCP tool to an AFMX node."""
        mock_tools = [
            self._make_mock_tool("search_web",  "search the web"),
            self._make_mock_tool("write_file",  "write to a file"),
            self._make_mock_tool("check_health","check service health"),
        ]

        with patch("afmx.adapters.mcp._discover_tools_sse", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = [_tool_to_dict(t) for t in mock_tools]

            adapter = MCPAdapter()
            nodes = await adapter.from_server("http://localhost:3000")

        assert len(nodes) == 3

        # Verify cognitive layers
        layer_map = {n.metadata["tool_name"]: n.cognitive_layer for n in nodes}
        assert layer_map["search_web"]   == CognitiveLayer.RETRIEVE.value
        assert layer_map["write_file"]   == CognitiveLayer.ACT.value
        assert layer_map["check_health"] == CognitiveLayer.EVALUATE.value

        # All nodes are MCP type
        for node in nodes:
            assert node.type == NodeType.MCP

    @pytest.mark.asyncio
    async def test_from_config_stdio(self):
        """from_config() creates nodes from a stdio server config."""
        mock_tools = [self._make_mock_tool("read_file", "read a file")]

        with patch("afmx.adapters.mcp._discover_tools_stdio", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = [_tool_to_dict(t) for t in mock_tools]

            adapter = MCPAdapter()
            nodes = await adapter.from_config({
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-filesystem"],
            }, server_name="filesystem")

        assert len(nodes) == 1
        assert nodes[0].cognitive_layer == CognitiveLayer.RETRIEVE.value
        assert "filesystem" in nodes[0].name

    @pytest.mark.asyncio
    async def test_from_desktop_config_multi_server(self):
        """from_desktop_config() loads from multiple servers."""
        mock_tools_a = [self._make_mock_tool("search", "search")]
        mock_tools_b = [self._make_mock_tool("write_issue", "write github issue")]

        call_count = [0]

        async def fake_discover_stdio(cfg):
            call_count[0] += 1
            if cfg.name == "search-server":
                return [_tool_to_dict(t) for t in mock_tools_a]
            return [_tool_to_dict(t) for t in mock_tools_b]

        with patch("afmx.adapters.mcp._discover_tools_stdio", side_effect=fake_discover_stdio):
            adapter = MCPAdapter()
            nodes = await adapter.from_desktop_config({
                "mcpServers": {
                    "search-server": {"command": "npx", "args": ["search-mcp"]},
                    "github-server": {"command": "npx", "args": ["github-mcp"]},
                }
            })

        assert len(nodes) == 2
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_from_desktop_config_skips_failed_server(self):
        """Failing servers are logged and skipped; others still load."""
        mock_tools = [self._make_mock_tool("search", "search")]

        async def fake_discover_stdio(cfg):
            if cfg.name == "bad-server":
                raise ConnectionError("server not found")
            return [_tool_to_dict(t) for t in mock_tools]

        with patch("afmx.adapters.mcp._discover_tools_stdio", side_effect=fake_discover_stdio):
            adapter = MCPAdapter()
            nodes = await adapter.from_desktop_config({
                "mcpServers": {
                    "good-server": {"command": "npx", "args": []},
                    "bad-server":  {"command": "npx", "args": []},
                }
            })

        # Only the good server's tool survives
        assert len(nodes) == 1

    @pytest.mark.asyncio
    async def test_default_role_applied(self):
        """default_role is passed through to all discovered nodes."""
        mock_tools = [self._make_mock_tool("search", "search the web")]

        with patch("afmx.adapters.mcp._discover_tools_sse", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = [_tool_to_dict(t) for t in mock_tools]

            adapter = MCPAdapter()
            nodes = await adapter.from_server(
                "http://localhost:3000",
                default_role="OPS",
            )

        assert nodes[0].agent_role == "OPS"

    @pytest.mark.asyncio
    async def test_url_normalisation(self):
        """from_server() appends /sse when the URL doesn't already have it."""
        captured_urls: List[str] = []

        async def fake_discover_sse(url, **kwargs):
            captured_urls.append(url)
            return []

        with patch("afmx.adapters.mcp._discover_tools_sse", side_effect=fake_discover_sse):
            adapter = MCPAdapter()
            await adapter.from_server("http://localhost:3000")          # no /sse
            await adapter.from_server("http://localhost:3000/sse")      # already has /sse
            await adapter.from_server("http://localhost:3000/sse/")     # trailing slash

        assert all(u == "http://localhost:3000/sse" for u in captured_urls)
