"""
AFMX OpenAI Adapter
====================
Wraps OpenAI function-calling tools and Assistants API as AFMX nodes.

Two integration modes:

  MODE 1 — Function Tool (Chat Completions + Tool Use)
  ─────────────────────────────────────────────────────
  Wrap a Python function as an OpenAI tool definition.
  AFMX node calls GPT-4o/GPT-4 with the function, parses the tool call,
  executes the function, and returns structured output.

  Usage:
      adapter = OpenAIAdapter(model="gpt-4o")

      def get_weather(city: str) -> dict:
          return {"city": city, "temp": 22, "condition": "sunny"}

      node = adapter.tool_node(
          fn=get_weather,
          description="Get current weather for a city",
          node_id="weather-tool",
      )

  MODE 2 — Assistants API
  ────────────────────────
  Create a new thread, run an Assistant, poll until complete,
  and return the final message.

  Usage:
      node = adapter.assistant_node(
          assistant_id="asst_abc123",
          node_id="ai-assistant",
      )

OpenAI is imported lazily — not required at module load time.
Install: pip install openai>=1.0.0

Environment: set OPENAI_API_KEY before running.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from afmx.adapters.base import AFMXAdapter, AdapterResult
from afmx.core.executor import HandlerRegistry
from afmx.models.node import Node, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "openai:"

# Poll interval and max polls for Assistants API
_ASSISTANT_POLL_INTERVAL = 1.0
_ASSISTANT_MAX_POLLS = 120   # 2 minutes


def _require_openai() -> None:
    try:
        import openai  # noqa: F401
    except ImportError:
        raise ImportError(
            "openai is required for OpenAIAdapter. "
            "Install: pip install openai>=1.0.0"
        )


# ─── Schema helpers ───────────────────────────────────────────────────────────

_PY_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _build_tool_schema(fn: Callable, description: str = "") -> Dict[str, Any]:
    """
    Auto-generate an OpenAI tool definition from a Python function's
    type hints and docstring.

    Produces a dict matching the OpenAI tools[] format:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    sig = inspect.signature(fn)
    hints = {}
    try:
        hints = get_type_hints(fn)
    except Exception:
        pass

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "return":
            continue
        py_type = hints.get(param_name, str)
        json_type = _PY_TO_JSON_TYPE.get(py_type, "string")

        properties[param_name] = {"type": json_type}

        # Parameter with no default = required
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    resolved_description = description or (fn.__doc__ or "").strip().split("\n")[0] or fn.__name__

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": resolved_description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ─── OpenAI Adapter ───────────────────────────────────────────────────────────

class OpenAIAdapter(AFMXAdapter):
    """
    AFMX adapter for OpenAI function-calling and Assistants API.

    Usage:
        from afmx.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o", api_key="sk-...")

        # Mode 1: Function tool node
        node = adapter.tool_node(fn=my_function, description="Does X")

        # Mode 2: Assistant node
        node = adapter.assistant_node(assistant_id="asst_abc123")
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ):
        """
        Args:
            model:        OpenAI model to use for function calling.
            api_key:      API key (falls back to OPENAI_API_KEY env var).
            organization: Optional org ID.
            max_tokens:   Max tokens for completions.
            temperature:  Sampling temperature (0.0 = deterministic).
        """
        self._model = model
        self._api_key = api_key
        self._organization = organization
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def name(self) -> str:
        return "openai"

    # ─── Node factories ───────────────────────────────────────────────────────

    def tool_node(
        self,
        fn: Callable,
        description: str = "",
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        system_prompt: str = "You are a helpful assistant.",
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> Node:
        """
        Create an AFMX node that calls GPT-4 with a function tool,
        parses the tool call, and executes the Python function.

        Args:
            fn:            Python function to wrap as a tool.
            description:   Tool description for the model.
            system_prompt: System message for the completion.
        """
        _require_openai()
        handler_key = f"{_HANDLER_PREFIX}tool:{fn.__name__}"
        tool_schema = _build_tool_schema(fn, description)

        # Register the handler
        adapter = self

        async def _tool_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await adapter._execute_function_tool(
                node_input=node_input,
                fn=fn,
                tool_schema=tool_schema,
                system_prompt=system_prompt,
            )
            if not result.success:
                raise RuntimeError(f"[OpenAI tool] {result.error}")
            return result.output

        HandlerRegistry.register(handler_key, _tool_handler)

        return self._make_node(
            handler_key=handler_key,
            external_ref=fn,
            node_id=node_id,
            node_name=node_name or fn.__name__,
            node_type=NodeType.TOOL,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config={
                "tool_schema": tool_schema,
                "system_prompt": system_prompt,
            },
        )

    def assistant_node(
        self,
        assistant_id: str,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        additional_instructions: Optional[str] = None,
    ) -> Node:
        """
        Create an AFMX node that runs an OpenAI Assistant.

        The node creates a thread, sends the input as a user message,
        runs the assistant, polls until completion, and returns
        the final message text.

        Args:
            assistant_id:             The OpenAI Assistant ID.
            additional_instructions:  Runtime instruction override.
        """
        _require_openai()
        handler_key = f"{_HANDLER_PREFIX}assistant:{assistant_id}"
        adapter = self

        async def _assistant_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await adapter._execute_assistant(
                node_input=node_input,
                assistant_id=assistant_id,
                additional_instructions=additional_instructions,
            )
            if not result.success:
                raise RuntimeError(f"[OpenAI assistant] {result.error}")
            return result.output

        HandlerRegistry.register(handler_key, _assistant_handler)

        return self._make_node(
            handler_key=handler_key,
            external_ref=assistant_id,
            node_id=node_id,
            node_name=node_name or f"assistant:{assistant_id[:12]}",
            node_type=NodeType.AGENT,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=120.0),
            extra_config={
                "assistant_id": assistant_id,
                "additional_instructions": additional_instructions,
            },
        )

    # ─── Base adapter contract ────────────────────────────────────────────────

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.TOOL,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Generic to_afmx_node — routes to tool_node or assistant_node.
        Pass a callable → tool_node; pass an assistant_id string → assistant_node.
        """
        if callable(external_obj):
            return self.tool_node(
                fn=external_obj,
                node_id=node_id,
                node_name=node_name,
                retry_policy=retry_policy,
                timeout_policy=timeout_policy,
            )
        if isinstance(external_obj, str) and external_obj.startswith("asst_"):
            return self.assistant_node(
                assistant_id=external_obj,
                node_id=node_id,
                node_name=node_name,
                retry_policy=retry_policy,
                timeout_policy=timeout_policy,
            )
        raise TypeError(
            f"OpenAIAdapter.to_afmx_node expects a callable (for function tool) "
            f"or an assistant_id string (for Assistants API). Got: {type(external_obj).__name__}"
        )

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """Generic execute — delegates to specific implementation."""
        _require_openai()
        if callable(external_ref):
            # Can't call _execute_function_tool without the schema —
            # use the registered handler instead (it has the schema captured)
            raise RuntimeError(
                "Use tool_node() or assistant_node() to create nodes — "
                "the handler captures the schema at node creation time."
            )
        return AdapterResult.fail(
            "Call tool_node() or assistant_node() instead of execute() directly."
        )

    def normalize(self, raw_output: Any) -> AdapterResult:
        if isinstance(raw_output, dict):
            return AdapterResult.ok(output=raw_output)
        return AdapterResult.ok(output={"result": str(raw_output)})

    # ─── Mode 1: Function Tool execution ─────────────────────────────────────

    async def _execute_function_tool(
        self,
        node_input: Dict[str, Any],
        fn: Callable,
        tool_schema: Dict[str, Any],
        system_prompt: str,
    ) -> AdapterResult:
        """
        1. Build user message from node_input
        2. Call OpenAI Chat Completions with the tool definition
        3. If the model calls the tool → execute fn with the args
        4. Return the function's output (not the model's text)
        """
        _require_openai()
        import openai

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            organization=self._organization,
        )

        raw_input = node_input.get("input")
        params = node_input.get("params", {})
        user_message = (
            params.get("message")
            or (raw_input if isinstance(raw_input, str) else json.dumps(raw_input))
            or "Please call the provided tool."
        )

        try:
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                tools=[tool_schema],
                tool_choice="auto",
            )

            message = response.choices[0].message

            # Model chose to call the tool
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                raw_args = tool_call.function.arguments
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                # Execute the Python function
                if inspect.iscoroutinefunction(fn):
                    fn_output = await fn(**args)
                else:
                    loop = asyncio.get_running_loop()
                    fn_output = await loop.run_in_executor(None, lambda: fn(**args))

                return AdapterResult.ok(
                    output={
                        "function_called": fn.__name__,
                        "arguments": args,
                        "result": fn_output,
                        "model": self._model,
                        "tokens": response.usage.total_tokens if response.usage else None,
                    }
                )

            # Model chose to respond with text instead of calling the tool
            text_response = message.content or ""
            return AdapterResult.ok(
                output={
                    "function_called": None,
                    "result": text_response,
                    "model": self._model,
                }
            )

        except Exception as exc:
            logger.error(f"[OpenAIAdapter] Function tool error: {exc}", exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    # ─── Mode 2: Assistants API execution ────────────────────────────────────

    async def _execute_assistant(
        self,
        node_input: Dict[str, Any],
        assistant_id: str,
        additional_instructions: Optional[str] = None,
    ) -> AdapterResult:
        """
        1. Create a new thread
        2. Add the input as a user message
        3. Run the assistant
        4. Poll until complete (or failed/cancelled/expired)
        5. Return the last assistant message
        """
        _require_openai()
        import openai

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            organization=self._organization,
        )

        raw_input = node_input.get("input")
        params = node_input.get("params", {})
        user_content = (
            params.get("message")
            or (raw_input if isinstance(raw_input, str) else json.dumps(raw_input))
            or "Continue."
        )

        try:
            # Create thread
            thread = await client.beta.threads.create()

            # Add user message
            await client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_content,
            )

            # Start run
            run_kwargs: Dict[str, Any] = {"assistant_id": assistant_id}
            if additional_instructions:
                run_kwargs["additional_instructions"] = additional_instructions

            run = await client.beta.threads.runs.create(
                thread_id=thread.id,
                **run_kwargs,
            )

            # Poll until terminal state
            terminal_states = {"completed", "failed", "cancelled", "expired"}
            polls = 0

            while run.status not in terminal_states:
                if polls >= _ASSISTANT_MAX_POLLS:
                    return AdapterResult.fail(
                        f"Assistant run timed out after {polls} polls",
                        "TimeoutError",
                    )
                await asyncio.sleep(_ASSISTANT_POLL_INTERVAL)
                run = await client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id,
                )
                polls += 1

            if run.status != "completed":
                return AdapterResult.fail(
                    f"Assistant run ended with status: {run.status}",
                    "AssistantRunError",
                )

            # Retrieve messages — get the last assistant message
            messages = await client.beta.threads.messages.list(
                thread_id=thread.id,
                order="desc",
                limit=5,
            )

            last_message = None
            for msg in messages.data:
                if msg.role == "assistant":
                    last_message = msg
                    break

            if last_message is None:
                return AdapterResult.fail("No assistant message found", "NoResponseError")

            # Extract text content
            text_parts = []
            for content_block in last_message.content:
                if hasattr(content_block, "text"):
                    text_parts.append(content_block.text.value)

            final_text = "\n".join(text_parts)

            return AdapterResult.ok(
                output={
                    "response": final_text,
                    "thread_id": thread.id,
                    "run_id": run.id,
                    "assistant_id": assistant_id,
                    "polls": polls,
                }
            )

        except Exception as exc:
            logger.error(f"[OpenAIAdapter] Assistant error: {exc}", exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)
