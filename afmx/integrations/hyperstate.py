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
AFMX ↔ HyperState Integration
================================
Connects AFMX's RETRIEVE-layer nodes to HyperState — the cognitive memory
layer for multi-agent systems.

HyperState provides temporal, policy-aware, shared memory with routing
intelligence. This integration wires it into AFMX so that any RETRIEVE-layer
node automatically has access to a persistent, multi-session cognitive state.

Two integration modes
---------------------
**Mode 1 — Handler (recommended):**
    Register a HyperState retrieval handler in ``HandlerRegistry`` so any
    node with ``handler="hyperstate:retrieve"`` queries HyperState for context.

    .. code-block:: python

        from afmx.integrations.hyperstate import attach_hyperstate

        attach_hyperstate(
            api_url="http://localhost:8000",
            api_key="hs_your_key",
        )
        # Now any node with handler="hyperstate:retrieve" calls HyperState.

**Mode 2 — PRE_NODE hook:**
    Optionally inject retrieved memory into ``ExecutionContext.memory``
    before every RETRIEVE-layer node runs, so downstream handlers always
    have access to relevant context without being HyperState-aware.

    .. code-block:: python

        attach_hyperstate(
            api_url="http://localhost:8000",
            api_key="hs_your_key",
            hook_registry=afmx_app.hook_registry,
            inject_into_memory=True,
        )

**Mode 3 — POST_NODE memory persistence:**
    Write AGENT-layer node outputs back to HyperState as semantic memories
    so future runs benefit from prior reasoning.

    .. code-block:: python

        attach_hyperstate(
            api_url="http://localhost:8000",
            api_key="hs_your_key",
            hook_registry=afmx_app.hook_registry,
            persist_agent_outputs=True,
        )

Environment variables
---------------------
    AFMX_HYPERSTATE_ENABLED=true
    AFMX_HYPERSTATE_URL=http://localhost:8000
    AFMX_HYPERSTATE_API_KEY=hs_...
    AFMX_HYPERSTATE_CONTEXT_ID=default          # per-deployment context
    AFMX_HYPERSTATE_TOP_K=10                    # results per query

Install::

    pip install afmx[hyperstate]
    # or: pip install hyperstate-sdk>=0.1.0

Routing signals
---------------
HyperState's ``/routing/signals/{context_id}`` endpoint returns signals that
can inform AFMX's ``CognitiveModelRouter``.  When ``use_routing_signals=True``
the integration reads these signals and adjusts the model tier hint in
``ExecutionContext.metadata`` before reasoning nodes execute.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Optional dependency guard ─────────────────────────────────────────────────

try:
    from hyperstate_sdk import AsyncHyperStateClient, HyperStateError
    _HYPERSTATE_AVAILABLE = True
except ImportError:
    _HYPERSTATE_AVAILABLE = False
    AsyncHyperStateClient = None  # type: ignore[assignment,misc]
    HyperStateError = Exception    # type: ignore[assignment,misc]

# Handler key used in HandlerRegistry
_RETRIEVE_HANDLER_KEY = "hyperstate:retrieve"
_STORE_HANDLER_KEY    = "hyperstate:store"


def _require_hyperstate() -> None:
    if not _HYPERSTATE_AVAILABLE:
        raise ImportError(
            "hyperstate-sdk is required for the HyperState integration.\n"
            "Install: pip install afmx[hyperstate]  or  pip install hyperstate-sdk"
        )


# ─── Handler factories ────────────────────────────────────────────────────────


def _make_retrieve_handler(
    api_url: str,
    api_key: str,
    default_context_id: str,
    top_k: int,
) -> Any:
    """
    Return an AFMX-compatible async handler that queries HyperState memory.

    Handler contract::

        node_input["params"]["query"]       → search query (required)
        node_input["params"]["context_id"]  → override context (optional)
        node_input["params"]["top_k"]       → override result count (optional)

    Returns::

        {
            "memories": [{"content": str, "score": float, ...}, ...],
            "routing_signals": {...},   # from HyperState /routing/signals
            "context_id": str,
        }
    """
    _url = api_url
    _key = api_key
    _ctx = default_context_id
    _k   = top_k

    async def hyperstate_retrieve(
        node_input: Dict[str, Any],
        context: Any,
        node: Any,
    ) -> Dict[str, Any]:
        params     = node_input.get("params", {})
        raw_input  = node_input.get("input", "")
        query      = params.get("query") or (
            raw_input if isinstance(raw_input, str) else str(raw_input)
        )
        context_id = params.get("context_id") or _ctx
        top_k      = int(params.get("top_k", _k))

        if not query:
            logger.warning("[HyperState:retrieve] Empty query — returning empty memories")
            return {"memories": [], "routing_signals": {}, "context_id": context_id}

        try:
            async with AsyncHyperStateClient(api_url=_url, api_key=_key) as client:
                memories = await client.query(
                    context_id=context_id,
                    query=query,
                    top_k=top_k,
                    requesting_agent_id=getattr(node, "name", "afmx"),
                )
                signals = await client.get_routing_signals(context_id)

            logger.debug(
                "[HyperState:retrieve] context=%s query=%r results=%d",
                context_id, query[:60], len(memories),
            )
            return {
                "memories":        memories,
                "routing_signals": signals,
                "context_id":      context_id,
                "query":           query,
            }
        except HyperStateError as exc:
            logger.error("[HyperState:retrieve] API error: %s", exc)
            return {
                "memories":        [],
                "routing_signals": {},
                "context_id":      context_id,
                "error":           str(exc),
            }

    hyperstate_retrieve.__name__ = "hyperstate_retrieve"
    return hyperstate_retrieve


def _make_store_handler(api_url: str, api_key: str, default_context_id: str) -> Any:
    """
    Return an AFMX-compatible async handler that stores content in HyperState.

    Handler contract::

        node_input["params"]["content"]      → text to store (required)
        node_input["params"]["context_id"]   → context (optional)
        node_input["params"]["memory_type"]  → "semantic"|"episodic"|"policy" (optional)
        node_input["params"]["importance"]   → float 0–1 (optional)
    """
    _url = api_url
    _key = api_key
    _ctx = default_context_id

    async def hyperstate_store(
        node_input: Dict[str, Any],
        context: Any,
        node: Any,
    ) -> Dict[str, Any]:
        params     = node_input.get("params", {})
        content    = params.get("content") or str(node_input.get("input", ""))
        context_id = params.get("context_id") or _ctx

        if not content:
            return {"stored": False, "reason": "empty content"}

        try:
            async with AsyncHyperStateClient(api_url=_url, api_key=_key) as client:
                result = await client.add_memory(
                    context_id=context_id,
                    content=content,
                    memory_type=params.get("memory_type", "semantic"),
                    importance_score=float(params.get("importance", 1.0)),
                    source_agent_id=getattr(node, "name", "afmx"),
                )
            return {"stored": True, "node_id": result.get("id"), "context_id": context_id}
        except HyperStateError as exc:
            logger.error("[HyperState:store] API error: %s", exc)
            return {"stored": False, "error": str(exc)}

    hyperstate_store.__name__ = "hyperstate_store"
    return hyperstate_store


# ─── Hook factories ───────────────────────────────────────────────────────────


def _make_pre_node_hook(
    api_url: str,
    api_key: str,
    default_context_id: str,
    top_k: int,
) -> Any:
    """
    PRE_NODE hook that injects HyperState memory into ExecutionContext
    before any RETRIEVE-layer node runs.

    After this hook, downstream handlers can read::

        context.get_memory("hyperstate:memories")     → list of retrieved memories
        context.get_memory("hyperstate:signals")      → routing signals dict
    """
    _url = api_url
    _key = api_key
    _ctx = default_context_id
    _k   = top_k

    async def hs_pre_node(payload: Any) -> Any:
        node    = getattr(payload, "node", None)
        context = getattr(payload, "context", None)
        if node is None or context is None:
            return payload

        # Only inject for RETRIEVE-layer nodes
        layer = getattr(node, "cognitive_layer", None)
        if str(layer).upper() != "RETRIEVE":
            return payload

        # Derive query from node input or node name
        node_input = getattr(payload, "node_input", {}) or {}
        raw_input  = node_input.get("input", "")
        query      = (
            node_input.get("params", {}).get("query")
            or (raw_input if isinstance(raw_input, str) else "")
            or node.name
        )
        context_id = (
            node_input.get("params", {}).get("context_id")
            or context.get_memory("hyperstate:context_id")
            or _ctx
        )

        try:
            async with AsyncHyperStateClient(api_url=_url, api_key=_key) as client:
                memories = await client.query(
                    context_id=context_id,
                    query=query,
                    top_k=_k,
                    requesting_agent_id=node.name,
                )
                signals = await client.get_routing_signals(context_id)

            context.set_memory("hyperstate:memories", memories)
            context.set_memory("hyperstate:signals", signals)
            context.set_memory("hyperstate:context_id", context_id)
            logger.debug(
                "[HyperState:hook] injected %d memories for node '%s'",
                len(memories), node.name,
            )
        except Exception as exc:
            logger.warning("[HyperState:hook] PRE_NODE injection failed: %s", exc)

        return payload

    hs_pre_node.__name__ = "hyperstate_pre_node"
    return hs_pre_node


def _make_post_node_hook(
    api_url: str,
    api_key: str,
    default_context_id: str,
) -> Any:
    """
    POST_NODE hook that persists AGENT-layer node outputs to HyperState
    as semantic memories for future runs.
    """
    _url = api_url
    _key = api_key
    _ctx = default_context_id

    async def hs_post_node(payload: Any) -> Any:
        node    = getattr(payload, "node", None)
        context = getattr(payload, "context", None)
        result  = getattr(payload, "node_result", None)
        if node is None or result is None:
            return payload

        # Only persist AGENT-layer successful outputs
        layer = str(getattr(node, "cognitive_layer", "")).upper()
        if layer not in ("REASON", "PLAN", "EVALUATE"):
            return payload
        if not getattr(result, "is_success", False):
            return payload

        output = getattr(result, "output", None)
        if not output:
            return payload

        # Serialise output to a storable string
        if isinstance(output, str):
            content = output
        elif isinstance(output, dict):
            import json
            content = json.dumps(output, ensure_ascii=False)
        else:
            content = str(output)

        context_id = (
            context.get_memory("hyperstate:context_id")
            if context else _ctx
        ) or _ctx

        try:
            async with AsyncHyperStateClient(api_url=_url, api_key=_key) as client:
                await client.add_memory(
                    context_id=context_id,
                    content=content,
                    memory_type="episodic",
                    node_type="reasoning",
                    importance_score=0.8,
                    source_agent_id=node.name,
                    metadata={
                        "afmx_node":    node.name,
                        "cognitive_layer": layer,
                    },
                )
            logger.debug(
                "[HyperState:hook] persisted output from AGENT node '%s'", node.name
            )
        except Exception as exc:
            logger.warning("[HyperState:hook] POST_NODE persist failed: %s", exc)

        return payload

    hs_post_node.__name__ = "hyperstate_post_node"
    return hs_post_node


# ─── Public entry point ───────────────────────────────────────────────────────


def attach_hyperstate(
    *,
    api_url: str = "http://localhost:8000",
    api_key: str = "",
    default_context_id: str = "afmx-default",
    top_k: int = 10,
    hook_registry: Any = None,
    inject_into_memory: bool = False,
    persist_agent_outputs: bool = False,
    use_routing_signals: bool = False,
) -> bool:
    """
    Attach HyperState to AFMX by registering handlers and optional hooks.

    Always registers two entries in ``HandlerRegistry``:
    - ``"hyperstate:retrieve"``  — queries HyperState for relevant memories
    - ``"hyperstate:store"``     — persists content to HyperState memory

    Optionally (when ``hook_registry`` is provided):
    - ``inject_into_memory=True``      — PRE_NODE hook enriches RETRIEVE-layer nodes
    - ``persist_agent_outputs=True``   — POST_NODE hook writes reasoning outputs back

    Parameters
    ----------
    api_url:
        HyperState API base URL.
    api_key:
        HyperState API key (``hs_...``).
    default_context_id:
        Default memory context for all nodes that don't specify one.
    top_k:
        Number of memory results to retrieve per query.
    hook_registry:
        AFMX ``HookRegistry`` instance (required for hook modes).
    inject_into_memory:
        If ``True``, inject retrieved memories into ``ExecutionContext.memory``
        before every RETRIEVE-layer node.
    persist_agent_outputs:
        If ``True``, persist REASON/PLAN/EVALUATE node outputs to HyperState.
    use_routing_signals:
        If ``True``, log HyperState routing signals (future: inform model tier).

    Returns
    -------
    bool
        ``True`` if the integration was attached successfully; ``False`` if
        ``hyperstate-sdk`` is not installed.

    Example::

        from afmx.integrations.hyperstate import attach_hyperstate

        attach_hyperstate(
            api_url="http://localhost:8000",
            api_key="hs_live_abc123",
            hook_registry=afmx_app.hook_registry,
            inject_into_memory=True,
            persist_agent_outputs=True,
        )
    """
    if not _HYPERSTATE_AVAILABLE:
        logger.warning(
            "[AFMX→HyperState] 'hyperstate-sdk' not installed — integration disabled. "
            "Install: pip install afmx[hyperstate]"
        )
        return False

    from afmx.core.executor import HandlerRegistry

    # Register retrieve handler
    HandlerRegistry.register(
        _RETRIEVE_HANDLER_KEY,
        _make_retrieve_handler(api_url, api_key, default_context_id, top_k),
    )
    # Register store handler
    HandlerRegistry.register(
        _STORE_HANDLER_KEY,
        _make_store_handler(api_url, api_key, default_context_id),
    )
    logger.info(
        "[AFMX→HyperState] Handlers registered: '%s', '%s'",
        _RETRIEVE_HANDLER_KEY, _STORE_HANDLER_KEY,
    )

    # Register hooks if hook_registry provided
    if hook_registry is not None:
        try:
            from afmx.core.hooks import HookType

            if inject_into_memory:
                hook_registry.register(
                    name="hyperstate_pre_node",
                    fn=_make_pre_node_hook(api_url, api_key, default_context_id, top_k),
                    hook_type=HookType.PRE_NODE,
                    priority=20,
                )
                logger.info("[AFMX→HyperState] PRE_NODE memory injection hook registered")

            if persist_agent_outputs:
                hook_registry.register(
                    name="hyperstate_post_node",
                    fn=_make_post_node_hook(api_url, api_key, default_context_id),
                    hook_type=HookType.POST_NODE,
                    priority=950,
                )
                logger.info("[AFMX→HyperState] POST_NODE memory persistence hook registered")

        except Exception as exc:
            logger.error("[AFMX→HyperState] Hook registration failed: %s", exc)

    logger.info(
        "[AFMX→HyperState] ✅ Integration active — url=%s ctx=%s top_k=%d",
        api_url, default_context_id, top_k,
    )
    return True
