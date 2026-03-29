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
AFMX Microsoft Semantic Kernel Adapter
========================================
Wraps Semantic Kernel ``KernelFunction`` objects (plugins, native functions,
prompt functions) as AFMX nodes.

Semantic Kernel (SK) is Microsoft's open-source orchestration SDK with
strong enterprise adoption and deep Azure OpenAI integration.  This adapter
makes every SK function available as an AFMX ``NodeType.FUNCTION`` node,
giving you SK's rich plugin ecosystem with AFMX's deterministic execution,
fault tolerance, cognitive routing, and audit trail.

Mapping
-------
+--------------------------------+------------------+------------------+
| Semantic Kernel object         | AFMX NodeType    | CognitiveLayer   |
+================================+==================+==================+
| KernelFunction (prompt)        | FUNCTION         | REASON (default) |
| KernelPlugin tool (native fn)  | TOOL             | inferred         |
| Kernel.invoke_stream           | FUNCTION         | REASON           |
+--------------------------------+------------------+------------------+

Install::

    pip install afmx[semantic-kernel]
    # or: pip install semantic-kernel>=1.0.0

Usage::

    from semantic_kernel import Kernel
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
    from afmx.adapters.semantic_kernel import SemanticKernelAdapter

    kernel = Kernel()
    kernel.add_service(OpenAIChatCompletion(service_id="gpt4o"))

    adapter = SemanticKernelAdapter(kernel=kernel)

    # Wrap a prompt function
    fn = kernel.add_function(
        plugin_name="summariser",
        function_name="summarise",
        prompt="Summarise: {{$input}}",
    )
    node = adapter.function_node(fn, node_name="summarise")

    # Wrap an entire plugin
    nodes = adapter.plugin_nodes("WebSearch")

    # Use in a matrix
    matrix = ExecutionMatrix(nodes=[node], mode=ExecutionMode.DIAGONAL)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from afmx.adapters.base import AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, Node, NodeConfig, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "sk:"


def _require_sk() -> None:
    try:
        import semantic_kernel  # noqa: F401
    except ImportError:
        raise ImportError(
            "semantic-kernel is required for SemanticKernelAdapter.\n"
            "Install: pip install afmx[semantic-kernel]  "
            "or  pip install semantic-kernel>=1.0.0"
        ) from None


def _infer_layer_from_sk_function(fn: Any) -> CognitiveLayer:
    """
    Infer CognitiveLayer from a Semantic Kernel function's name and description.

    SK prompt functions are typically REASON-tier (complex synthesis).
    Native functions that retrieve/search are RETRIEVE-tier.
    Native functions that write/act are ACT-tier.
    """
    from afmx.adapters.mcp import infer_cognitive_layer

    name = getattr(fn, "name", "") or ""
    desc = getattr(fn, "description", "") or ""
    return infer_cognitive_layer(name, desc)


class SemanticKernelAdapter(AFMXAdapter):
    """
    AFMX adapter for Microsoft Semantic Kernel.

    Wraps SK ``KernelFunction`` objects as AFMX nodes. Supports:
    - Prompt functions (template-based LLM calls)
    - Native functions (Python functions registered in SK plugins)
    - Streaming functions (``invoke_stream``)
    - Full SK plugin wrapping (``plugin_nodes``)

    Args:
        kernel: A configured ``semantic_kernel.Kernel`` instance.
        default_service_id: The SK AI service ID to use for invocations.
        max_tokens: Default max tokens for prompt functions.
        temperature: Default temperature for prompt functions.
    """

    def __init__(
        self,
        kernel: Any,
        *,
        default_service_id: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> None:
        _require_sk()
        self._kernel             = kernel
        self._default_service_id = default_service_id
        self._max_tokens         = max_tokens
        self._temperature        = temperature

    @property
    def name(self) -> str:
        return "semantic_kernel"

    # ── AFMXAdapter contract ──────────────────────────────────────────────────

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.FUNCTION,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Wrap a ``KernelFunction`` as an AFMX node.

        Args:
            external_obj: A ``KernelFunction`` instance from ``Kernel.add_function``
                          or ``Kernel.get_function``.
        """
        return self.function_node(
            fn=external_obj,
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config=extra_config or {},
        )

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """Invoke a KernelFunction with the given node_input."""
        _require_sk()
        try:
            result = await self._invoke_function(external_ref, node_input)
            return AdapterResult.ok(output={"result": str(result), "value": result})
        except Exception as exc:
            logger.error("[SK] Execution error: %s", exc, exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    def normalize(self, raw_output: Any) -> AdapterResult:
        if hasattr(raw_output, "value"):
            return AdapterResult.ok(output={"result": str(raw_output.value)})
        return AdapterResult.ok(output={"result": str(raw_output)})

    # ── Public node factories ─────────────────────────────────────────────────

    def function_node(
        self,
        fn: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.FUNCTION,
        cognitive_layer: Optional[CognitiveLayer] = None,
        agent_role: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Wrap a single ``KernelFunction`` as an AFMX node.

        Args:
            fn: ``KernelFunction`` returned by ``kernel.add_function`` or
                ``kernel.get_function(plugin_name, function_name)``.
            cognitive_layer: Override inferred cognitive layer.
            agent_role: Optional matrix role coordinate.

        Returns:
            AFMX ``Node`` with registered handler.
        """
        _require_sk()

        fn_name     = getattr(fn, "name", "sk_function")
        plugin_name = getattr(fn, "plugin_name", "default")
        resolved_name = node_name or f"{plugin_name}.{fn_name}"
        handler_key   = f"{_HANDLER_PREFIX}{plugin_name}.{fn_name}"
        inferred_layer = cognitive_layer or _infer_layer_from_sk_function(fn)

        # Build and register the handler closure
        kernel     = self._kernel
        service_id = self._default_service_id
        max_tokens = self._max_tokens
        temperature = self._temperature

        async def _sk_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await _invoke_kernel_function(
                kernel=kernel,
                fn=fn,
                node_input=node_input,
                service_id=service_id,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return {"result": str(result), "value": result}

        _sk_handler.__name__ = f"sk_{plugin_name}_{fn_name}"
        HandlerRegistry.register(handler_key, _sk_handler)

        # Merge any caller-supplied extra_config params into the node config
        config_params: Dict[str, Any] = {
            "plugin_name":   plugin_name,
            "function_name": fn_name,
            "description":   getattr(fn, "description", ""),
        }
        if extra_config:
            config_params.update(extra_config)

        return Node(
            id=node_id or _generate_id(),
            name=resolved_name,
            type=node_type,
            handler=handler_key,
            cognitive_layer=inferred_layer,
            agent_role=agent_role,
            config=NodeConfig(
                params=config_params,
                tags=["semantic_kernel", plugin_name],
            ),
            retry_policy=retry_policy or RetryPolicy(retries=2),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=60.0),
            metadata={
                "adapter":       "semantic_kernel",
                "plugin_name":   plugin_name,
                "function_name": fn_name,
                "description":   getattr(fn, "description", ""),
            },
        )

    def plugin_nodes(
        self,
        plugin_name: str,
        *,
        agent_role: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> List[Node]:
        """
        Wrap all functions in a Semantic Kernel plugin as AFMX nodes.

        Args:
            plugin_name: Name of the SK plugin (e.g. ``"WebSearch"``).

        Returns:
            List of AFMX nodes, one per function in the plugin.

        Example::

            nodes = adapter.plugin_nodes("WebSearch", agent_role="OPS")
            matrix = ExecutionMatrix(nodes=nodes, mode=ExecutionMode.DIAGONAL)
        """
        _require_sk()
        try:
            plugin = self._kernel.plugins[plugin_name]
        except (KeyError, AttributeError):
            raise ValueError(
                f"Plugin '{plugin_name}' not found in Kernel. "
                f"Add it with kernel.add_plugin() first."
            )

        nodes: List[Node] = []
        for fn_name, fn in plugin.functions.items():
            node = self.function_node(
                fn,
                agent_role=agent_role,
                retry_policy=retry_policy,
                timeout_policy=timeout_policy,
            )
            nodes.append(node)

        logger.info(
            "[SK] Wrapped %d functions from plugin '%s'", len(nodes), plugin_name
        )
        return nodes

    async def _invoke_function(self, fn: Any, node_input: Dict[str, Any]) -> Any:
        return await _invoke_kernel_function(
            kernel=self._kernel,
            fn=fn,
            node_input=node_input,
            service_id=self._default_service_id,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )


# ─── Shared invocation logic ─────────────────────────────────────────────────


async def _invoke_kernel_function(
    *,
    kernel: Any,
    fn: Any,
    node_input: Dict[str, Any],
    service_id: Optional[str],
    max_tokens: int,
    temperature: float,
) -> Any:
    """
    Invoke a SK KernelFunction with arguments derived from AFMX node_input.

    SK functions accept a ``KernelArguments`` dict. We build this from:
    1. ``node_input["params"]``  (highest priority)
    2. ``node_input["input"]`` mapped to ``"input"`` key (SK default variable)
    """
    from semantic_kernel.functions.kernel_arguments import KernelArguments

    params    = node_input.get("params", {})
    raw_input = node_input.get("input")

    args: Dict[str, Any] = {}
    if isinstance(raw_input, str):
        args["input"] = raw_input
    elif isinstance(raw_input, dict):
        args.update(raw_input)

    if isinstance(params, dict):
        args.update(params)

    # Remove AFMX-internal metadata keys
    for internal in ("__model_hint__", "__model_tier__", "__cognitive_layer__", "__agent_role__"):
        args.pop(internal, None)

    kernel_args = KernelArguments(**args)
    result = await kernel.invoke(fn, kernel_args)
    return result


def _generate_id() -> str:
    import uuid
    return str(uuid.uuid4())
