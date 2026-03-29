# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Unit tests for v1.3.0 — new adapters and integrations.

Tests are grouped by component and use mock objects throughout so no
external service or optional package installation is required to run them.

Test groups
-----------
1. SemanticKernelAdapter  — function/plugin node construction, handler registration
2. GoogleADKAdapter       — tool/agent node construction, layer inference
3. BedrockAdapter         — model/agent node construction, provider body builders
4. HyperState integration — handler registration, argument extraction
5. MAP integration        — handler registration, graceful missing-package handling
6. RHFL integration       — RHFLBlockedError, RHFLTimeoutError, client logic
7. AdapterRegistry        — lazy loading, _requires_init_args helper
"""
from __future__ import annotations

import sys
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from afmx.adapters.registry import _requires_init_args, AdapterRegistry
from afmx.models.node import CognitiveLayer, NodeType, RetryPolicy, TimeoutPolicy


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _clear_registry_handlers():
    """Clear HandlerRegistry between tests to avoid key collisions."""
    from afmx.core.executor import HandlerRegistry
    # Only clear keys starting with known test prefixes
    keys_to_remove = [
        k for k in list(HandlerRegistry._registry.keys())
        if k.startswith(("sk:", "google_adk:", "bedrock:", "hyperstate:", "map:", "rhfl:"))
    ]
    for k in keys_to_remove:
        HandlerRegistry._registry.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# 1. SemanticKernelAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestSemanticKernelAdapter:
    """SemanticKernelAdapter — unit tests using a mock Kernel."""

    def _make_mock_kernel(self):
        kernel = MagicMock()
        return kernel

    def _make_mock_function(self, name: str = "summarise", plugin: str = "writer") -> MagicMock:
        fn = MagicMock()
        fn.name        = name
        fn.plugin_name = plugin
        fn.description = f"{name} — a test SK function"
        return fn

    def test_adapter_name(self):
        from afmx.adapters.semantic_kernel import SemanticKernelAdapter
        with patch("afmx.adapters.semantic_kernel._require_sk"):
            adapter = SemanticKernelAdapter(kernel=self._make_mock_kernel())
        assert adapter.name == "semantic_kernel"

    def test_function_node_registers_handler(self):
        """function_node() registers handler in HandlerRegistry."""
        from afmx.adapters.semantic_kernel import SemanticKernelAdapter
        from afmx.core.executor import HandlerRegistry

        _clear_registry_handlers()
        with patch("afmx.adapters.semantic_kernel._require_sk"):
            adapter = SemanticKernelAdapter(kernel=self._make_mock_kernel())
            fn = self._make_mock_function("search", "web")
            node = adapter.function_node(fn, node_name="web-search")

        assert node.type   == NodeType.FUNCTION
        assert node.name   == "web-search"
        assert node.handler.startswith("sk:")
        assert HandlerRegistry.resolve(node.handler) is not None

    def test_function_node_layer_inferred_from_name(self):
        """Layer is inferred from function name when not provided."""
        from afmx.adapters.semantic_kernel import SemanticKernelAdapter, _infer_layer_from_sk_function

        fn = MagicMock()
        fn.name        = "search_web"
        fn.description = "search the web for current information"
        layer = _infer_layer_from_sk_function(fn)
        assert layer == CognitiveLayer.RETRIEVE

    def test_function_node_cognitive_layer_override(self):
        """Explicitly supplied cognitive_layer is respected."""
        from afmx.adapters.semantic_kernel import SemanticKernelAdapter

        _clear_registry_handlers()
        with patch("afmx.adapters.semantic_kernel._require_sk"):
            adapter = SemanticKernelAdapter(kernel=self._make_mock_kernel())
            fn   = self._make_mock_function("analyse", "finance")
            node = adapter.function_node(fn, cognitive_layer=CognitiveLayer.EVALUATE)

        assert node.cognitive_layer == CognitiveLayer.EVALUATE.value

    def test_plugin_nodes_raises_on_missing_plugin(self):
        from afmx.adapters.semantic_kernel import SemanticKernelAdapter

        kernel = MagicMock()
        kernel.plugins = {}  # empty — no plugins registered

        with patch("afmx.adapters.semantic_kernel._require_sk"):
            adapter = SemanticKernelAdapter(kernel=kernel)
            with pytest.raises(ValueError, match="Plugin 'NonExistent' not found"):
                adapter.plugin_nodes("NonExistent")

    def test_missing_sk_raises_import_error(self):
        """_require_sk raises ImportError with install instructions."""
        from afmx.adapters.semantic_kernel import _require_sk

        with patch.dict(sys.modules, {"semantic_kernel": None}):
            with pytest.raises(ImportError, match="semantic-kernel"):
                _require_sk()


# ─────────────────────────────────────────────────────────────────────────────
# 2. GoogleADKAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestGoogleADKAdapter:
    """GoogleADKAdapter — unit tests using mock ADK objects."""

    def _make_mock_tool(self, name: str = "search") -> MagicMock:
        tool = MagicMock()
        tool.name        = name
        tool.description = f"{name} tool"
        return tool

    def _make_mock_agent(self, name: str = "researcher", agent_type: str = "LlmAgent") -> MagicMock:
        agent = MagicMock()
        agent.name        = name
        agent.__class__.__name__ = agent_type
        agent.instruction = "You are a helpful researcher."
        return agent

    def test_adapter_name(self):
        from afmx.adapters.google_adk import GoogleADKAdapter
        with patch("afmx.adapters.google_adk._require_adk"):
            adapter = GoogleADKAdapter()
        assert adapter.name == "google_adk"

    def test_tool_node_type(self):
        from afmx.adapters.google_adk import GoogleADKAdapter

        _clear_registry_handlers()
        with patch("afmx.adapters.google_adk._require_adk"):
            adapter = GoogleADKAdapter()
            tool = self._make_mock_tool("read_file")
            node = adapter.tool_node(tool)

        assert node.type == NodeType.TOOL
        assert "google_adk" in node.metadata.get("adapter", "")

    def test_tool_node_layer_inferred(self):
        """'read_file' → RETRIEVE layer."""
        from afmx.adapters.google_adk import GoogleADKAdapter

        _clear_registry_handlers()
        with patch("afmx.adapters.google_adk._require_adk"):
            adapter = GoogleADKAdapter()
            node = adapter.tool_node(self._make_mock_tool("read_file"))

        assert node.cognitive_layer == CognitiveLayer.RETRIEVE.value

    def test_agent_node_type(self):
        from afmx.adapters.google_adk import GoogleADKAdapter

        _clear_registry_handlers()
        with patch("afmx.adapters.google_adk._require_adk"):
            adapter = GoogleADKAdapter()
            agent = self._make_mock_agent("analyst")
            node = adapter.agent_node(agent)

        assert node.type == NodeType.AGENT

    def test_sequential_agent_maps_to_plan(self):
        """SequentialAgent → PLAN layer."""
        from afmx.adapters.google_adk import GoogleADKAdapter, _infer_adk_layer

        agent = MagicMock()
        agent.__class__.__name__ = "SequentialAgent"
        agent.name = "pipeline"
        agent.instruction = ""
        layer = _infer_adk_layer(agent)
        assert layer == CognitiveLayer.PLAN

    def test_to_afmx_node_routes_correctly(self):
        """to_afmx_node routes tool → TOOL, agent → AGENT."""
        from afmx.adapters.google_adk import GoogleADKAdapter, _detect_adk_node_type

        _clear_registry_handlers()
        tool = MagicMock()
        # Simulate BaseTool isinstance check returning True
        with patch("afmx.adapters.google_adk._detect_adk_node_type", return_value=NodeType.TOOL):
            with patch("afmx.adapters.google_adk._require_adk"):
                adapter = GoogleADKAdapter()
                node = adapter.to_afmx_node(tool)
        assert node.type == NodeType.TOOL

    def test_missing_adk_raises_import_error(self):
        from afmx.adapters.google_adk import _require_adk

        with patch.dict(sys.modules, {"google": None, "google.adk": None}):
            with pytest.raises(ImportError, match="google-adk"):
                _require_adk()


# ─────────────────────────────────────────────────────────────────────────────
# 3. BedrockAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestBedrockAdapter:
    """BedrockAdapter — unit tests using mock boto3."""

    def _make_adapter(self) -> "BedrockAdapter":
        from afmx.adapters.bedrock import BedrockAdapter
        mock_session = MagicMock()
        with patch("afmx.adapters.bedrock._require_boto3"):
            adapter = BedrockAdapter.__new__(BedrockAdapter)
            adapter._session = mock_session
            adapter._region  = "us-east-1"
        return adapter

    def test_model_node_type(self):
        adapter = self._make_adapter()
        node = adapter.model_node("anthropic.claude-3-haiku-20240307-v1:0")
        assert node.type    == NodeType.FUNCTION
        assert node.handler.startswith("bedrock:")

    def test_agent_node_type(self):
        node = self._make_adapter().agent_node(
            agent_id="ABCDEF1234",
            agent_alias_id="TSTALIASID",
        )
        assert node.type == NodeType.AGENT
        assert "ABCDEF1234" in node.metadata.get("agent_id", "")

    def test_haiku_maps_to_retrieve_layer(self):
        from afmx.adapters.bedrock import _model_id_to_layer
        layer = _model_id_to_layer("anthropic.claude-3-haiku-20240307-v1:0")
        assert layer == CognitiveLayer.RETRIEVE

    def test_opus_maps_to_reason_layer(self):
        from afmx.adapters.bedrock import _model_id_to_layer
        layer = _model_id_to_layer("anthropic.claude-opus-20240229-v1:0")
        assert layer == CognitiveLayer.REASON

    def test_claude_request_body(self):
        """Anthropic Claude uses Messages API format."""
        from afmx.adapters.bedrock import _build_invoke_body
        body = _build_invoke_body(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            prompt="Hello",
            system_prompt="Be helpful",
            max_tokens=1024,
            temperature=0.0,
        )
        assert "messages" in body
        assert body["messages"][0]["role"] == "user"
        assert body["system"] == "Be helpful"
        assert body["max_tokens"] == 1024

    def test_titan_request_body(self):
        from afmx.adapters.bedrock import _build_invoke_body
        body = _build_invoke_body(
            model_id="amazon.titan-text-express-v1",
            prompt="Hello",
            system_prompt=None,
            max_tokens=512,
            temperature=0.5,
        )
        assert "inputText" in body
        assert "textGenerationConfig" in body

    def test_llama_request_body(self):
        from afmx.adapters.bedrock import _build_invoke_body
        body = _build_invoke_body(
            model_id="meta.llama3-70b-instruct-v1:0",
            prompt="What is RAG?",
            system_prompt=None,
            max_tokens=256,
            temperature=0.0,
        )
        assert "prompt" in body
        assert "max_gen_len" in body

    def test_claude_response_extraction(self):
        from afmx.adapters.bedrock import _extract_response_text
        raw = {"content": [{"text": "Hello from Claude!"}]}
        text = _extract_response_text("anthropic.claude-3-haiku", raw)
        assert text == "Hello from Claude!"

    def test_titan_response_extraction(self):
        from afmx.adapters.bedrock import _extract_response_text
        raw = {"results": [{"outputText": "Hello from Titan!"}]}
        text = _extract_response_text("amazon.titan-text", raw)
        assert text == "Hello from Titan!"

    def test_missing_boto3_raises(self):
        from afmx.adapters.bedrock import _require_boto3
        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ImportError, match="boto3"):
                _require_boto3()


# ─────────────────────────────────────────────────────────────────────────────
# 4. HyperState integration
# ─────────────────────────────────────────────────────────────────────────────


class TestHyperstateIntegration:
    """attach_hyperstate() — unit tests without real HyperState server."""

    def test_returns_false_when_sdk_missing(self):
        """attach_hyperstate returns False if hyperstate-sdk is not installed."""
        import afmx.integrations.hyperstate as hs_module
        original = hs_module._HYPERSTATE_AVAILABLE
        try:
            hs_module._HYPERSTATE_AVAILABLE = False
            result = hs_module.attach_hyperstate(api_url="http://x", api_key="k")
            assert result is False
        finally:
            hs_module._HYPERSTATE_AVAILABLE = original

    def test_registers_handlers_when_available(self):
        """attach_hyperstate registers retrieve + store handlers."""
        from afmx.core.executor import HandlerRegistry
        import afmx.integrations.hyperstate as hs_module

        _clear_registry_handlers()

        # Patch the SDK as available
        original = hs_module._HYPERSTATE_AVAILABLE
        try:
            hs_module._HYPERSTATE_AVAILABLE = True
            hs_module.AsyncHyperStateClient = MagicMock()
            result = hs_module.attach_hyperstate(api_url="http://hs:8000", api_key="hs_test")
            assert result is True
            assert HandlerRegistry.resolve("hyperstate:retrieve") is not None
            assert HandlerRegistry.resolve("hyperstate:store") is not None
        finally:
            hs_module._HYPERSTATE_AVAILABLE = original

    @pytest.mark.asyncio
    async def test_retrieve_handler_returns_empty_on_empty_query(self):
        """Handler returns empty memories when query is empty."""
        import afmx.integrations.hyperstate as hs_module

        mock_client_cls = MagicMock()
        mock_client_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        handler = hs_module._make_retrieve_handler(
            api_url="http://x", api_key="k",
            default_context_id="ctx", top_k=5,
        )
        result = await handler(
            node_input={"params": {"query": ""}, "input": ""},
            context=None,
            node=MagicMock(name="n"),
        )
        assert result["memories"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. MAP integration
# ─────────────────────────────────────────────────────────────────────────────


class TestMAPIntegration:
    """attach_map() — unit tests without real MAP service."""

    @pytest.mark.asyncio
    async def test_returns_false_when_sdk_missing(self):
        import afmx.integrations.map_plugin as mp
        original = mp._MAP_AVAILABLE
        try:
            mp._MAP_AVAILABLE = False
            result = await mp.attach_map(service=MagicMock())
            assert result is False
        finally:
            mp._MAP_AVAILABLE = original

    @pytest.mark.asyncio
    async def test_registers_handlers_when_available(self):
        from afmx.core.executor import HandlerRegistry
        import afmx.integrations.map_plugin as mp

        _clear_registry_handlers()

        original = mp._MAP_AVAILABLE
        try:
            mp._MAP_AVAILABLE = True
            mock_service = MagicMock()
            result = await mp.attach_map(service=mock_service)
            assert result is True
            assert HandlerRegistry.resolve("map:retrieve") is not None
            assert HandlerRegistry.resolve("map:verify") is not None
        finally:
            mp._MAP_AVAILABLE = original


# ─────────────────────────────────────────────────────────────────────────────
# 6. RHFL integration
# ─────────────────────────────────────────────────────────────────────────────


class TestRHFLIntegration:
    """RHFL integration — error types, gate logic, attach_rhfl."""

    def test_blocked_error_attributes(self):
        from afmx.integrations.rhfl import RHFLBlockedError
        err = RHFLBlockedError(
            decision_id="d-123",
            reason="Policy violation",
            classification="BLOCK",
        )
        assert err.decision_id    == "d-123"
        assert err.classification == "BLOCK"
        assert "d-123" in str(err)

    def test_timeout_error_attributes(self):
        from afmx.integrations.rhfl import RHFLTimeoutError
        err = RHFLTimeoutError(decision_id="d-456", waited_seconds=120.0)
        assert err.decision_id    == "d-456"
        assert err.waited_seconds == 120.0

    def test_attach_rhfl_returns_false_without_token(self):
        from afmx.integrations.rhfl import attach_rhfl
        result = attach_rhfl(api_url="http://x", token="")
        assert result is False

    def test_attach_rhfl_registers_handler(self):
        from afmx.core.executor import HandlerRegistry
        from afmx.integrations.rhfl import attach_rhfl

        _clear_registry_handlers()
        result = attach_rhfl(api_url="http://rhfl:4000/api/v1", token="test-jwt-token")
        assert result is True
        assert HandlerRegistry.resolve("rhfl:gate") is not None

    @pytest.mark.asyncio
    async def test_gate_raises_blocked_on_block_classification(self):
        """_gate_through_rhfl raises RHFLBlockedError on BLOCK classification."""
        from afmx.integrations.rhfl import _gate_through_rhfl, RHFLBlockedError, _RHFLClient

        mock_client = MagicMock(spec=_RHFLClient)
        mock_client.submit_decision = AsyncMock(return_value={
            "id":             "d-789",
            "classification": "BLOCK",
            "status":         "BLOCKED",
        })

        with pytest.raises(RHFLBlockedError) as exc_info:
            await _gate_through_rhfl(
                mock_client,
                source="test-node",
                intent="delete prod database",
                payload={},
                risk_score=0.9,
                poll_interval=0.01,
                max_wait=1.0,
            )
        assert exc_info.value.decision_id == "d-789"

    @pytest.mark.asyncio
    async def test_gate_proceeds_on_auto_approved(self):
        """_gate_through_rhfl returns decision dict on AUTO/EXECUTING."""
        from afmx.integrations.rhfl import _gate_through_rhfl, _RHFLClient

        mock_client = MagicMock(spec=_RHFLClient)
        mock_client.submit_decision = AsyncMock(return_value={
            "id":             "d-auto",
            "classification": "AUTO",
            "status":         "EXECUTING",
        })

        result = await _gate_through_rhfl(
            mock_client,
            source="safe-node",
            intent="fetch data",
            payload={},
            risk_score=0.1,
            poll_interval=0.01,
            max_wait=5.0,
        )
        assert result["id"] == "d-auto"

    @pytest.mark.asyncio
    async def test_gate_raises_timeout_when_max_wait_exceeded(self):
        """_gate_through_rhfl raises RHFLTimeoutError when max_wait is 0."""
        from afmx.integrations.rhfl import _gate_through_rhfl, RHFLTimeoutError, _RHFLClient

        mock_client = MagicMock(spec=_RHFLClient)
        mock_client.submit_decision = AsyncMock(return_value={
            "id":             "d-slow",
            "classification": "REVIEW",
            "status":         "PENDING",
        })

        with pytest.raises(RHFLTimeoutError):
            await _gate_through_rhfl(
                mock_client,
                source="node",
                intent="action",
                payload={},
                risk_score=0.5,
                poll_interval=0.001,
                max_wait=0.0,  # zero — times out immediately
            )


# ─────────────────────────────────────────────────────────────────────────────
# 7. AdapterRegistry
# ─────────────────────────────────────────────────────────────────────────────


class TestAdapterRegistry:
    """AdapterRegistry — lazy loading, _requires_init_args."""

    def test_requires_init_args_no_args(self):
        """Adapter with no required args → False."""
        class NoArgs:
            def __init__(self) -> None:
                pass
        assert _requires_init_args(NoArgs) is False

    def test_requires_init_args_with_required(self):
        """Adapter with required args → True."""
        class HasArgs:
            def __init__(self, kernel: Any) -> None:
                self.kernel = kernel
        assert _requires_init_args(HasArgs) is True

    def test_requires_init_args_with_defaults_only(self):
        """Adapter with only default args → False."""
        class DefaultsOnly:
            def __init__(self, region: str = "us-east-1") -> None:
                self.region = region
        assert _requires_init_args(DefaultsOnly) is False

    def test_requires_init_args_mixed(self):
        """Adapter with one required and one default → True."""
        class Mixed:
            def __init__(self, required: str, optional: str = "x") -> None:
                pass
        assert _requires_init_args(Mixed) is True

    def test_registry_get_raises_on_missing(self):
        reg = AdapterRegistry()
        reg._initialized = True  # skip lazy loading
        with pytest.raises(KeyError, match="missing_adapter"):
            reg.get("missing_adapter")

    def test_registry_get_optional_returns_none(self):
        reg = AdapterRegistry()
        reg._initialized = True
        assert reg.get_optional("nothing") is None

    def test_registry_has_returns_false(self):
        reg = AdapterRegistry()
        reg._initialized = True
        assert reg.has("nothing") is False

    def test_registry_register_and_get(self):
        from afmx.adapters.mcp import MCPAdapter

        reg = AdapterRegistry()
        reg._initialized = True
        adapter = MCPAdapter()
        reg.register(adapter)
        assert reg.has("mcp")
        retrieved = reg.get("mcp")
        assert retrieved is adapter

    def test_registry_deregister(self):
        from afmx.adapters.mcp import MCPAdapter

        reg = AdapterRegistry()
        reg._initialized = True
        reg.register(MCPAdapter())
        assert reg.has("mcp")
        reg.deregister("mcp")
        assert not reg.has("mcp")

    def test_registry_decorator(self):
        from afmx.adapters.base import AdapterResult

        reg = AdapterRegistry()
        reg._initialized = True

        @reg.register_adapter
        class _TestAdapter:
            @property
            def name(self) -> str:
                return "test_decorator"
            def to_afmx_node(self, *a, **kw): ...  # noqa: ANN201
            async def execute(self, *a, **kw) -> AdapterResult: ...  # noqa: ANN201
            def normalize(self, raw): ...  # noqa: ANN201

        assert reg.has("test_decorator")
