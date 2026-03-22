"""
Unit tests for the OpenAI adapter.
All OpenAI API calls are mocked — openai package not required.
"""
from __future__ import annotations

import sys
import types
import json
import pytest
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Build a minimal fake openai package ─────────────────────────────────────

def _install_fake_openai():
    """
    Inject a minimal fake openai module so adapter imports succeed
    without the real package installed.
    """
    if "openai" in sys.modules:
        return  # Already present (real or fake)

    fake_openai = types.ModuleType("openai")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs): pass

    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    sys.modules["openai"] = fake_openai


_install_fake_openai()

from afmx.adapters.openai import OpenAIAdapter, _build_tool_schema
from afmx.adapters.base import AdapterResult
from afmx.core.executor import HandlerRegistry
from afmx.models.node import NodeType
from afmx.models.execution import ExecutionContext


@pytest.fixture(autouse=True)
def clean_registry():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()


# ─── Schema builder ───────────────────────────────────────────────────────────

class TestBuildToolSchema:
    def test_basic_function(self):
        def add(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y

        schema = _build_tool_schema(add, "Adds two numbers")
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "add"
        assert fn["description"] == "Adds two numbers"
        assert "x" in fn["parameters"]["properties"]
        assert "y" in fn["parameters"]["properties"]
        assert fn["parameters"]["properties"]["x"]["type"] == "integer"
        assert "x" in fn["parameters"]["required"]

    def test_optional_param_not_in_required(self):
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}"

        schema = _build_tool_schema(greet)
        required = schema["function"]["parameters"]["required"]
        assert "name" in required
        assert "greeting" not in required

    def test_string_param_type(self):
        def lookup(query: str) -> dict:
            pass

        schema = _build_tool_schema(lookup)
        assert schema["function"]["parameters"]["properties"]["query"]["type"] == "string"

    def test_description_from_docstring(self):
        def my_fn():
            """This is the docstring description."""
            pass

        schema = _build_tool_schema(my_fn)
        assert "docstring" in schema["function"]["description"]

    def test_no_params(self):
        def no_params() -> str:
            pass

        schema = _build_tool_schema(no_params)
        assert schema["function"]["parameters"]["properties"] == {}
        assert schema["function"]["parameters"]["required"] == []


# ─── OpenAIAdapter construction ───────────────────────────────────────────────

class TestOpenAIAdapterConstruction:
    def test_name(self):
        adapter = OpenAIAdapter()
        assert adapter.name == "openai"

    def test_default_model(self):
        adapter = OpenAIAdapter()
        assert adapter._model == "gpt-4o"

    def test_custom_model(self):
        adapter = OpenAIAdapter(model="gpt-4-turbo")
        assert adapter._model == "gpt-4-turbo"


# ─── tool_node ────────────────────────────────────────────────────────────────

class TestToolNode:
    def test_creates_tool_node(self):
        adapter = OpenAIAdapter()

        def get_weather(city: str) -> dict:
            return {"temp": 22}

        node = adapter.tool_node(fn=get_weather, node_id="weather")
        assert node.id == "weather"
        assert node.type == NodeType.TOOL
        assert "get_weather" in node.handler

    def test_registers_handler(self):
        adapter = OpenAIAdapter()

        def my_fn(x: str) -> str:
            return x

        adapter.tool_node(fn=my_fn)
        assert any("my_fn" in k for k in HandlerRegistry.list_registered())

    def test_custom_node_name(self):
        adapter = OpenAIAdapter()

        def search(q: str) -> list:
            pass

        node = adapter.tool_node(fn=search, node_name="web_search_tool")
        assert node.name == "web_search_tool"

    def test_tool_schema_in_config(self):
        adapter = OpenAIAdapter()

        def calculate(n: int) -> int:
            return n * 2

        node = adapter.tool_node(fn=calculate)
        assert "tool_schema" in node.config.params
        schema = node.config.params["tool_schema"]
        assert schema["function"]["name"] == "calculate"


# ─── assistant_node ───────────────────────────────────────────────────────────

class TestAssistantNode:
    def test_creates_agent_node(self):
        adapter = OpenAIAdapter()
        node = adapter.assistant_node(
            assistant_id="asst_test123",
            node_id="my-assistant",
        )
        assert node.id == "my-assistant"
        assert node.type == NodeType.AGENT
        assert "asst_test123" in node.handler

    def test_registers_handler(self):
        adapter = OpenAIAdapter()
        adapter.assistant_node(assistant_id="asst_xyz")
        assert any("asst_xyz" in k for k in HandlerRegistry.list_registered())

    def test_default_timeout_is_120(self):
        adapter = OpenAIAdapter()
        node = adapter.assistant_node(assistant_id="asst_abc")
        assert node.timeout_policy.timeout_seconds == 120.0

    def test_assistant_id_in_config(self):
        adapter = OpenAIAdapter()
        node = adapter.assistant_node(assistant_id="asst_check")
        assert node.config.params["assistant_id"] == "asst_check"


# ─── to_afmx_node routing ────────────────────────────────────────────────────

class TestToAfmxNode:
    def test_callable_routes_to_tool_node(self):
        adapter = OpenAIAdapter()

        def my_func(x: str) -> str:
            return x

        node = adapter.to_afmx_node(my_func)
        assert node.type == NodeType.TOOL

    def test_assistant_id_string_routes_to_assistant_node(self):
        adapter = OpenAIAdapter()
        node = adapter.to_afmx_node("asst_abc123")
        assert node.type == NodeType.AGENT

    def test_invalid_type_raises(self):
        adapter = OpenAIAdapter()
        with pytest.raises(TypeError, match="callable"):
            adapter.to_afmx_node(42)


# ─── Function tool execution ─────────────────────────────────────────────────

class TestFunctionToolExecution:
    def _make_mock_response(self, fn_name: str, args: dict):
        """Build a mock OpenAI completion response that calls a tool."""
        tool_call = MagicMock()
        tool_call.function.arguments = json.dumps(args)
        tool_call.function.name = fn_name
        tool_call.id = "call_abc"

        message = MagicMock()
        message.tool_calls = [tool_call]
        message.content = None

        usage = MagicMock()
        usage.total_tokens = 42

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        return response

    @pytest.mark.asyncio
    async def test_tool_executes_function_on_tool_call(self):
        """When model calls the tool, the Python function is executed."""
        results = []

        def get_price(product: str) -> dict:
            results.append(product)
            return {"product": product, "price": 9.99}

        adapter = OpenAIAdapter()
        mock_response = self._make_mock_response("get_price", {"product": "widget"})

        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            schema = _build_tool_schema(get_price)
            result = await adapter._execute_function_tool(
                node_input={"input": "What is the price of widget?"},
                fn=get_price,
                tool_schema=schema,
                system_prompt="You are a pricing assistant.",
            )

        assert result.success is True
        assert result.output["function_called"] == "get_price"
        # fn_output is the dict returned by get_price; it lives at result.output["result"]
        assert result.output["result"]["price"] == 9.99
        assert results == ["widget"]

    @pytest.mark.asyncio
    async def test_tool_returns_text_when_no_tool_call(self):
        """When model responds with text instead of a tool call."""
        def unused(x: str) -> str:
            return x

        adapter = OpenAIAdapter()

        message = MagicMock()
        message.tool_calls = None
        message.content = "I don't need to call any tool."
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        response.usage = None

        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=response)

            schema = _build_tool_schema(unused)
            result = await adapter._execute_function_tool(
                node_input={"input": "Hello"},
                fn=unused,
                tool_schema=schema,
                system_prompt="",
            )

        assert result.success is True
        assert result.output["function_called"] is None
        assert "don't need" in result.output["result"]

    @pytest.mark.asyncio
    async def test_api_error_returns_fail(self):
        def fn(x: str) -> str:
            return x

        adapter = OpenAIAdapter()

        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API rate limit exceeded")
            )

            schema = _build_tool_schema(fn)
            result = await adapter._execute_function_tool(
                node_input={"input": "test"},
                fn=fn,
                tool_schema=schema,
                system_prompt="",
            )

        assert result.success is False
        assert "rate limit" in result.error

    @pytest.mark.asyncio
    async def test_async_function_is_awaited(self):
        """Async Python functions are properly awaited."""
        called_with = []

        async def async_lookup(query: str) -> dict:
            called_with.append(query)
            return {"found": True}

        adapter = OpenAIAdapter()
        mock_response = self._make_mock_response("async_lookup", {"query": "test_query"})

        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            schema = _build_tool_schema(async_lookup)
            result = await adapter._execute_function_tool(
                node_input={"input": "look something up"},
                fn=async_lookup,
                tool_schema=schema,
                system_prompt="",
            )

        assert result.success is True
        assert called_with == ["test_query"]
        # fn_output is {"found": True}, stored at result.output["result"]
        assert result.output["result"] == {"found": True}


# ─── Assistant execution ─────────────────────────────────────────────────────

class TestAssistantExecution:
    def _make_mock_client(self, final_text: str = "Here is my response."):
        """Build a complete mock of the Assistants API client."""
        mock_client = AsyncMock()

        mock_thread = MagicMock()
        mock_thread.id = "thread_abc123"
        mock_client.beta.threads.create = AsyncMock(return_value=mock_thread)
        mock_client.beta.threads.messages.create = AsyncMock(return_value=MagicMock())

        mock_run_pending = MagicMock()
        mock_run_pending.id = "run_xyz"
        mock_run_pending.status = "queued"

        mock_run_done = MagicMock()
        mock_run_done.id = "run_xyz"
        mock_run_done.status = "completed"

        mock_client.beta.threads.runs.create = AsyncMock(return_value=mock_run_pending)
        mock_client.beta.threads.runs.retrieve = AsyncMock(return_value=mock_run_done)

        text_block = MagicMock()
        text_block.text = MagicMock()
        text_block.text.value = final_text

        assistant_msg = MagicMock()
        assistant_msg.role = "assistant"
        assistant_msg.content = [text_block]

        messages_page = MagicMock()
        messages_page.data = [assistant_msg]
        mock_client.beta.threads.messages.list = AsyncMock(return_value=messages_page)

        return mock_client

    @pytest.mark.asyncio
    async def test_assistant_returns_response(self):
        adapter = OpenAIAdapter()
        mock_client = self._make_mock_client("The answer is 42.")

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter._execute_assistant(
                node_input={"input": "What is 6 times 7?"},
                assistant_id="asst_test",
            )

        assert result.success is True
        assert result.output["response"] == "The answer is 42."
        assert result.output["assistant_id"] == "asst_test"
        assert "thread_id" in result.output

    @pytest.mark.asyncio
    async def test_assistant_failed_run_returns_fail(self):
        adapter = OpenAIAdapter()
        mock_client = AsyncMock()

        mock_thread = MagicMock()
        mock_thread.id = "thread_fail"
        mock_client.beta.threads.create = AsyncMock(return_value=mock_thread)
        mock_client.beta.threads.messages.create = AsyncMock()

        failed_run = MagicMock()
        failed_run.id = "run_fail"
        failed_run.status = "failed"
        mock_client.beta.threads.runs.create = AsyncMock(return_value=failed_run)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter._execute_assistant(
                node_input={"input": "test"},
                assistant_id="asst_fail",
            )

        assert result.success is False
        assert "failed" in result.error

    @pytest.mark.asyncio
    async def test_assistant_api_error_returns_fail(self):
        adapter = OpenAIAdapter()
        mock_client = AsyncMock()
        mock_client.beta.threads.create = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter._execute_assistant(
                node_input={"input": "test"},
                assistant_id="asst_err",
            )

        assert result.success is False
        assert "timeout" in result.error.lower()


# ─── Handler integration ──────────────────────────────────────────────────────

class TestOpenAIHandlerIntegration:
    @pytest.mark.asyncio
    async def test_tool_handler_callable_executes(self):
        """
        End-to-end: tool_node registers a handler that executes correctly
        via NodeExecutor.

        Data flow:
          1. my_tool(query="hello") returns {"result": "found: hello"}   ← fn_output (dict)
          2. _execute_function_tool stores fn_output at output["result"]
          3. So result.output["result"] == {"result": "found: hello"}    ← the dict
          4. And result.output["result"]["result"] == "found: hello"     ← the string
        """
        from afmx.core.executor import NodeExecutor
        from afmx.core.retry import RetryManager

        captured = []

        def my_tool(query: str) -> dict:
            captured.append(query)
            return {"result": f"found: {query}"}

        adapter = OpenAIAdapter()
        mock_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.arguments = json.dumps({"query": "hello"})
        tool_call.function.name = "my_tool"
        message = MagicMock()
        message.tool_calls = [tool_call]
        message.content = None
        choice = MagicMock()
        choice.message = message
        mock_response.choices = [choice]
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10

        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            node = adapter.tool_node(fn=my_tool, node_id="tool_test")
            executor = NodeExecutor(retry_manager=RetryManager())
            ctx = ExecutionContext(input="search for hello")
            result = await executor.execute(node, ctx)

        from afmx.models.node import NodeStatus
        assert result.status == NodeStatus.SUCCESS
        assert captured == ["hello"]

        # result.output is the full AdapterResult output dict:
        #   {"function_called": "my_tool", "arguments": {...}, "result": <fn_output>, ...}
        # fn_output is {"result": "found: hello"}, so:
        assert result.output["function_called"] == "my_tool"
        assert result.output["result"] == {"result": "found: hello"}
        assert result.output["result"]["result"] == "found: hello"
