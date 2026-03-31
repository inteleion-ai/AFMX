# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
AFMX Google Agent Development Kit (ADK) Adapter
=================================================
Wraps Google ADK agents and tools as AFMX nodes.

Google launched the Agent Development Kit (ADK) in March 2026 as their
open-source framework for building multi-agent systems.  ADK provides:
- ``BaseAgent`` — programmable agents with structured output
- ``LlmAgent`` — agents backed by Gemini models
- ``Tool`` — function tools with input/output schemas
- Multi-agent orchestration via ``SequentialAgent``, ``ParallelAgent``

This adapter makes every ADK agent and tool executable inside AFMX's
deterministic fabric — gaining retry, fallback, circuit breaker, cognitive
routing, and audit trail.

Mapping
-------
+----------------------------+------------------+---------------------------+
| Google ADK object          | AFMX NodeType    | CognitiveLayer (default)  |
+============================+==================+===========================+
| ``BaseTool`` / ``Tool``    | TOOL             | inferred from name/desc   |
| ``LlmAgent``               | AGENT            | REASON                    |
| ``BaseAgent`` subclass     | AGENT            | REASON                    |
| ``SequentialAgent``        | AGENT            | PLAN                      |
| ``ParallelAgent``          | AGENT            | PLAN                      |
+----------------------------+------------------+---------------------------+

Install::

    pip install afmx[google-adk]
    # or: pip install google-adk>=0.1.0

Usage::

    from google.adk.agents import LlmAgent
    from google.adk.tools import google_search
    from afmx.adapters.google_adk import GoogleADKAdapter

    adapter = GoogleADKAdapter()

    # Wrap a tool
    node = adapter.tool_node(google_search, node_name="search")

    # Wrap an LLM agent
    researcher = LlmAgent(
        name="researcher",
        model="gemini-1.5-pro",
        instruction="You research topics thoroughly.",
        tools=[google_search],
    )
    agent_node = adapter.agent_node(researcher, cognitive_layer="REASON")

    # Build matrix
    matrix = ExecutionMatrix(nodes=[node, agent_node], mode=ExecutionMode.DIAGONAL)

References
----------
- https://google.github.io/adk-docs/
- https://github.com/google/adk-python
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from afmx.adapters.base import AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, Node, NodeConfig, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "google_adk:"


def _require_adk() -> None:
    try:
        import google.adk  # noqa: F401
    except ImportError:
        raise ImportError(
            "google-adk is required for GoogleADKAdapter.\n"
            "Install: pip install afmx[google-adk]  or  pip install google-adk>=0.1.0"
        ) from None


def _detect_adk_node_type(obj: Any) -> NodeType:
    """Detect AFMX NodeType from a Google ADK object."""
    try:
        from google.adk.tools import BaseTool
        if isinstance(obj, BaseTool):
            return NodeType.TOOL
    except ImportError:
        pass
    return NodeType.AGENT


def _infer_adk_layer(obj: Any) -> CognitiveLayer:
    """Infer CognitiveLayer from ADK object type and name."""
    from afmx.adapters.mcp import infer_cognitive_layer

    obj_type = type(obj).__name__.lower()

    # Sequential/Parallel agents are planners
    if "sequential" in obj_type or "parallel" in obj_type:
        return CognitiveLayer.PLAN

    # Convert to str explicitly — attributes on MagicMock objects are truthy
    # but not strings; this guards against test mocks and unusual ADK objects.
    raw_name = getattr(obj, "name", "") or ""
    name = str(raw_name) if not isinstance(raw_name, str) else raw_name

    raw_desc = getattr(obj, "description", None)
    if not isinstance(raw_desc, str):
        raw_desc = getattr(obj, "instruction", None)
    if not isinstance(raw_desc, str):
        raw_desc = ""
    desc: str = raw_desc

    return infer_cognitive_layer(name, desc)


class GoogleADKAdapter(AFMXAdapter):
    """
    AFMX adapter for Google Agent Development Kit (ADK).

    Supports:
    - ``BaseTool`` / ``Tool`` objects
    - ``LlmAgent`` with Gemini models
    - ``BaseAgent`` subclasses
    - ``SequentialAgent`` and ``ParallelAgent``
    """

    def __init__(
        self,
        *,
        app_name: str = "afmx",
        user_id: str = "afmx-user",
        session_service: Any = None,
    ) -> None:
        """
        Args:
            app_name: ADK app name (used for session management).
            user_id: Default user ID for ADK runner sessions.
            session_service: Optional ADK ``InMemorySessionService`` or custom.
        """
        _require_adk()
        self._app_name       = app_name
        self._user_id        = user_id
        self._session_service = session_service

    @property
    def name(self) -> str:
        return "google_adk"

    # ── AFMXAdapter contract ──────────────────────────────────────────────────

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: Optional[NodeType] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Convert a Google ADK agent or tool to an AFMX node.

        Automatically routes to ``agent_node`` or ``tool_node`` based on type.
        """
        detected = _detect_adk_node_type(external_obj)
        if detected == NodeType.TOOL:
            return self.tool_node(
                external_obj,
                node_id=node_id,
                node_name=node_name,
                retry_policy=retry_policy,
                timeout_policy=timeout_policy,
            )
        return self.agent_node(
            external_obj,
            node_id=node_id,
            node_name=node_name,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
        )

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        detected = _detect_adk_node_type(external_ref)
        if detected == NodeType.TOOL:
            return await self._execute_tool(external_ref, node_input)
        return await self._execute_agent(external_ref, node_input)

    def normalize(self, raw_output: Any) -> AdapterResult:
        if isinstance(raw_output, str):
            return AdapterResult.ok(output={"text": raw_output})
        if isinstance(raw_output, dict):
            return AdapterResult.ok(output=raw_output)
        return AdapterResult.ok(output={"value": str(raw_output)})

    # ── Public node factories ─────────────────────────────────────────────────

    def tool_node(
        self,
        tool: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        cognitive_layer: Optional[CognitiveLayer] = None,
        agent_role: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> Node:
        """
        Wrap a Google ADK ``Tool`` or ``BaseTool`` as an AFMX TOOL node.

        Args:
            tool: ADK Tool object.
            cognitive_layer: Override inferred layer (default: from name/desc).
        """
        _require_adk()
        # Use isinstance guard: MagicMock.name returns a MagicMock, not None,
        # so a plain truthiness check would accept it as the name.
        raw_tool_name = getattr(tool, "name", None)
        tool_name = raw_tool_name if isinstance(raw_tool_name, str) and raw_tool_name \
            else type(tool).__name__.lower()
        handler_key = f"{_HANDLER_PREFIX}tool.{tool_name}"
        layer = cognitive_layer or _infer_adk_layer(tool)

        _tool = tool
        _adapter = self

        async def _adk_tool_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await _adapter._execute_tool(_tool, node_input)
            if not result.success:
                raise RuntimeError(f"[GoogleADK:tool:{tool_name}] {result.error}")
            return result.output

        _adk_tool_handler.__name__ = f"adk_tool_{tool_name}"
        HandlerRegistry.register(handler_key, _adk_tool_handler)

        description = getattr(tool, "description", "") or ""
        return Node(
            id=node_id or str(uuid.uuid4()),
            name=node_name or tool_name,
            type=NodeType.TOOL,
            handler=handler_key,
            cognitive_layer=layer,
            agent_role=agent_role,
            config=NodeConfig(
                params={"tool_name": tool_name, "description": description},
                tags=["google_adk", "tool"],
            ),
            retry_policy=retry_policy or RetryPolicy(retries=2),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=30.0),
            metadata={
                "adapter":    "google_adk",
                "tool_name":  tool_name,
                "description": description,
            },
        )

    def agent_node(
        self,
        agent: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        cognitive_layer: Optional[CognitiveLayer] = None,
        agent_role: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> Node:
        """
        Wrap a Google ADK ``BaseAgent`` / ``LlmAgent`` as an AFMX AGENT node.

        The agent is executed via ADK's ``Runner``, which handles session
        management and multi-turn conversation internally.

        Args:
            agent: ADK agent (``LlmAgent``, ``SequentialAgent``, etc.).
            cognitive_layer: Override inferred layer.
        """
        _require_adk()
        raw_agent_name = getattr(agent, "name", None)
        agent_name = raw_agent_name if isinstance(raw_agent_name, str) and raw_agent_name \
            else type(agent).__name__.lower()
        handler_key = f"{_HANDLER_PREFIX}agent.{agent_name}"
        layer       = cognitive_layer or _infer_adk_layer(agent)

        _agent   = agent
        _adapter = self

        async def _adk_agent_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await _adapter._execute_agent(_agent, node_input)
            if not result.success:
                raise RuntimeError(f"[GoogleADK:agent:{agent_name}] {result.error}")
            return result.output

        _adk_agent_handler.__name__ = f"adk_agent_{agent_name}"
        HandlerRegistry.register(handler_key, _adk_agent_handler)

        instruction = getattr(agent, "instruction", "") or ""
        return Node(
            id=node_id or str(uuid.uuid4()),
            name=node_name or agent_name,
            type=NodeType.AGENT,
            handler=handler_key,
            cognitive_layer=layer,
            agent_role=agent_role,
            config=NodeConfig(
                params={
                    "agent_name":  agent_name,
                    "agent_type":  type(agent).__name__,
                    "instruction": instruction[:256],
                },
                tags=["google_adk", "agent"],
            ),
            retry_policy=retry_policy or RetryPolicy(retries=1),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=120.0),
            metadata={
                "adapter":     "google_adk",
                "agent_name":  agent_name,
                "agent_type":  type(agent).__name__,
                "instruction": instruction[:256],
            },
        )

    # ── Internal execution ────────────────────────────────────────────────────

    async def _execute_tool(
        self,
        tool: Any,
        node_input: Dict[str, Any],
    ) -> AdapterResult:
        """Execute a Google ADK Tool."""
        params    = node_input.get("params", {})
        raw_input = node_input.get("input")

        args: Dict[str, Any] = {}
        if isinstance(raw_input, dict):
            args.update(raw_input)
        elif isinstance(raw_input, str):
            args["query"] = raw_input

        if isinstance(params, dict):
            for k, v in params.items():
                if not k.startswith("__"):
                    args[k] = v

        try:
            # ADK Tool can be async or sync
            if asyncio.iscoroutinefunction(getattr(tool, "run_async", None)):
                output = await tool.run_async(**args)
            elif asyncio.iscoroutinefunction(tool):
                output = await tool(**args)
            else:
                loop = asyncio.get_running_loop()
                if hasattr(tool, "__call__"):
                    output = await loop.run_in_executor(None, lambda: tool(**args))
                else:
                    output = await loop.run_in_executor(None, tool)

            return self.normalize(output)
        except Exception as exc:
            logger.error("[GoogleADK:tool] Error: %s", exc, exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    async def _execute_agent(
        self,
        agent: Any,
        node_input: Dict[str, Any],
    ) -> AdapterResult:
        """Execute a Google ADK Agent via Runner."""
        _require_adk()
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai.types import Content, Part
        except ImportError as exc:
            return AdapterResult.fail(
                f"google-adk packages missing: {exc}. "
                "Install: pip install google-adk>=0.1.0",
                "ImportError",
            )

        params    = node_input.get("params", {})
        raw_input = node_input.get("input", "")
        message   = (
            params.get("message")
            or (raw_input if isinstance(raw_input, str) else str(raw_input))
            or "Continue."
        )
        session_id = params.get("session_id") or str(uuid.uuid4())

        try:
            service = self._session_service or InMemorySessionService()
            await service.create_session(
                app_name=self._app_name,
                user_id=self._user_id,
                session_id=session_id,
            )

            runner = Runner(
                agent=agent,
                app_name=self._app_name,
                session_service=service,
            )

            user_message = Content(role="user", parts=[Part.from_text(message)])
            final_text   = ""

            async for event in runner.run_async(
                user_id=self._user_id,
                session_id=session_id,
                new_message=user_message,
            ):
                if event.is_final_response():
                    final_text = event.content.parts[0].text if event.content else ""
                    break

            return AdapterResult.ok(output={
                "text":       final_text,
                "session_id": session_id,
                "agent":      getattr(agent, "name", type(agent).__name__),
            })
        except Exception as exc:
            logger.error("[GoogleADK:agent] Error: %s", exc, exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)
