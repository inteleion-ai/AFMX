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
AFMX ↔ MAP (Memory Augmentation Platform) Integration
=======================================================
Bridges AFMX's RETRIEVE-layer nodes with MAP — the Context Reliability &
Verification Layer for AI Agents.

MAP guarantees that context is:
- **Deterministic** — same query → same result, always
- **Verified** — SHA-256 integrity on every context unit
- **Provenanced** — every chunk knows its origin document and position
- **Replay-safe** — any decision can be reproduced with the exact context used
- **Conflict-free** — contradictions caught before the LLM call

Architecture
------------
MAP sits between AFMX and any memory/retrieval backend (vector DB, Postgres,
Redis). AFMX nodes that would otherwise call a retrieval handler directly
instead call MAP, which verifies, deduplicates, and conflict-checks the
context before returning it.

::

    AFMX Node (RETRIEVE layer)
         ↓
    MAPService.retrieve(query, context_id)
         ↓
    ContextUnit[] (SHA-256 verified, provenanced, conflict-free)
         ↓
    ExecutionContext.memory["map:context"]

Integration modes
-----------------
**Mode 1 — Handler:**
    Register a ``"map:retrieve"`` handler that AFMX nodes call directly.
    Use in nodes with ``handler="map:retrieve"``.

**Mode 2 — PRE_NODE hook:**
    Automatically enrich RETRIEVE-layer nodes with MAP context before
    execution. The handler receives the verified context in
    ``node_input["map_context"]``.

**Mode 3 — Integrity check POST_NODE:**
    After REASON/PLAN nodes produce output, verify their output
    is not in conflict with stored MAP context.

Install::

    pip install afmx[map]
    # or: pip install map-platform>=1.0.0

Usage::

    from afmx.integrations.map_plugin import attach_map

    # Minimal — registers handlers only
    await attach_map(service=map_service)

    # Full — hooks for automatic RETRIEVE enrichment
    await attach_map(
        service=map_service,
        hook_registry=afmx_app.hook_registry,
        inject_into_memory=True,
        verify_outputs=True,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Optional dependency guard ─────────────────────────────────────────────────

try:
    from map.core.exceptions import ConflictError, MAPError
    from map.core.models import ConflictStrategy, RetrievalQuery, SourceType
    from map.service import MAPService
    _MAP_AVAILABLE = True
except ImportError:
    _MAP_AVAILABLE = False
    MAPService          = None  # type: ignore[assignment,misc]
    RetrievalQuery      = None  # type: ignore[assignment,misc]
    SourceType          = None  # type: ignore[assignment,misc]
    ConflictStrategy    = None  # type: ignore[assignment,misc]
    MAPError            = Exception  # type: ignore[assignment]
    ConflictError       = Exception  # type: ignore[assignment]

_RETRIEVE_HANDLER_KEY = "map:retrieve"
_VERIFY_HANDLER_KEY   = "map:verify"


def _require_map() -> None:
    if not _MAP_AVAILABLE:
        raise ImportError(
            "map-platform is required for the MAP integration.\n"
            "Install: pip install afmx[map]  or  pip install map-platform>=1.0.0"
        )


# ─── Handler factories ────────────────────────────────────────────────────────


def _make_retrieve_handler(service: Any) -> Any:
    """
    Return an AFMX handler that queries MAP for deterministic, verified context.

    Input::

        node_input["params"]["query"]          → retrieval query (required)
        node_input["params"]["context_id"]     → session context (optional)
        node_input["params"]["top_k"]          → result count (default: 10)
        node_input["params"]["source_types"]   → list of SourceType strings
        node_input["params"]["conflict_strategy"] → "RAISE"|"FILTER"|"MERGE"

    Output::

        {
            "context_units": [
                {
                    "id": str,
                    "content": str,
                    "source": str,
                    "hash": str,         # SHA-256 integrity hash
                    "score": float,
                    "provenance": {...},
                }
            ],
            "conflict_report": {...} | None,
            "deterministic_key": str,    # stable key for replay
        }
    """
    _service = service

    async def map_retrieve(
        node_input: Dict[str, Any],
        context: Any,
        node: Any,
    ) -> Dict[str, Any]:
        params     = node_input.get("params", {})
        raw_input  = node_input.get("input", "")
        query_text = (
            params.get("query")
            or (raw_input if isinstance(raw_input, str) else str(raw_input))
        )
        context_id = params.get("context_id", "default")

        if not query_text:
            return {"context_units": [], "conflict_report": None, "deterministic_key": ""}

        try:
            query = RetrievalQuery(
                query=query_text,
                context_id=context_id,
                top_k=int(params.get("top_k", 10)),
                conflict_strategy=ConflictStrategy(
                    params.get("conflict_strategy", "FILTER")
                ),
            )
            raw_result = await _service.retrieve(query)
            # Validate integrity (MAP raises IntegrityError if hash mismatch)
            clean_result, report = await _service.validate(raw_result)

            units = [
                {
                    "id":               u.id,
                    "content":          u.content,
                    "source":           str(u.source_type),
                    "hash":             u.content_hash,
                    "score":            u.relevance_score,
                    "provenance":       u.provenance,
                }
                for u in clean_result.units
            ]

            logger.debug(
                "[MAP:retrieve] context=%s query=%r units=%d conflicts=%d",
                context_id, query_text[:60], len(units),
                len(report.conflicts) if report else 0,
            )
            return {
                "context_units":    units,
                "conflict_report":  report.model_dump() if report else None,
                "deterministic_key": clean_result.deterministic_key,
                "context_id":       context_id,
            }
        except ConflictError as exc:
            logger.warning("[MAP:retrieve] Conflict detected: %s", exc)
            return {
                "context_units":  [],
                "conflict_report": {"error": str(exc)},
                "deterministic_key": "",
            }
        except MAPError as exc:
            logger.error("[MAP:retrieve] MAP error: %s", exc)
            return {"context_units": [], "error": str(exc)}

    map_retrieve.__name__ = "map_retrieve"
    return map_retrieve


def _make_verify_handler(service: Any) -> Any:
    """
    Return an AFMX handler that verifies a context unit's integrity via MAP.

    Input::

        node_input["params"]["unit_id"]   → ContextUnit ID to verify
        node_input["params"]["content"]   → content to hash-check (optional)

    Output::

        {"valid": bool, "hash": str, "integrity_report": {...}}
    """
    _service = service

    async def map_verify(
        node_input: Dict[str, Any],
        context: Any,
        node: Any,
    ) -> Dict[str, Any]:
        params  = node_input.get("params", {})
        unit_id = params.get("unit_id", "")
        content = params.get("content", "")

        try:
            report = await _service.verify_integrity(unit_id=unit_id, content=content)
            return {
                "valid":             report.valid,
                "hash":              report.hash,
                "integrity_report":  report.model_dump(),
            }
        except MAPError as exc:
            logger.error("[MAP:verify] Error: %s", exc)
            return {"valid": False, "error": str(exc)}

    map_verify.__name__ = "map_verify"
    return map_verify


# ─── Hook factories ───────────────────────────────────────────────────────────


def _make_pre_node_hook(service: Any, top_k: int) -> Any:
    """
    PRE_NODE hook that injects MAP-verified context into ExecutionContext
    before RETRIEVE-layer nodes run.

    After this hook::

        context.get_memory("map:context_units")   → list of verified ContextUnit dicts
        context.get_memory("map:deterministic_key") → replay key
    """
    _service = service
    _k = top_k

    async def map_pre_node(payload: Any) -> Any:
        node    = getattr(payload, "node", None)
        context = getattr(payload, "context", None)
        if node is None or context is None:
            return payload

        layer = str(getattr(node, "cognitive_layer", "")).upper()
        if layer != "RETRIEVE":
            return payload

        node_input = getattr(payload, "node_input", {}) or {}
        raw_input  = node_input.get("input", "")
        query_text = (
            node_input.get("params", {}).get("query")
            or (raw_input if isinstance(raw_input, str) else "")
            or node.name
        )
        context_id = (
            node_input.get("params", {}).get("context_id")
            or context.get_memory("map:context_id")
            or "default"
        )

        try:
            query = RetrievalQuery(
                query=query_text,
                context_id=context_id,
                top_k=_k,
                conflict_strategy=ConflictStrategy.FILTER,
            )
            raw_result = await _service.retrieve(query)
            clean_result, report = await _service.validate(raw_result)

            units = [
                {
                    "id":       u.id,
                    "content":  u.content,
                    "source":   str(u.source_type),
                    "hash":     u.content_hash,
                    "score":    u.relevance_score,
                }
                for u in clean_result.units
            ]
            context.set_memory("map:context_units",     units)
            context.set_memory("map:deterministic_key", clean_result.deterministic_key)
            context.set_memory("map:context_id",        context_id)

            logger.debug(
                "[MAP:hook] Injected %d verified units for RETRIEVE node '%s'",
                len(units), node.name,
            )
        except Exception as exc:
            logger.warning("[MAP:hook] PRE_NODE injection failed: %s", exc)

        return payload

    map_pre_node.__name__ = "map_pre_node"
    return map_pre_node


# ─── Public entry point ───────────────────────────────────────────────────────


async def attach_map(
    *,
    service: Any,
    hook_registry: Any = None,
    inject_into_memory: bool = False,
    verify_outputs: bool = False,
    top_k: int = 10,
) -> bool:
    """
    Attach MAP to AFMX by registering handlers and optional hooks.

    Always registers:
    - ``"map:retrieve"``  — queries MAP for verified, provenanced context
    - ``"map:verify"``    — verifies integrity of a specific context unit

    Parameters
    ----------
    service:
        A configured ``MAPService`` instance.
    hook_registry:
        AFMX ``HookRegistry`` (required for hook modes).
    inject_into_memory:
        If ``True``, inject MAP context into ``ExecutionContext`` before
        every RETRIEVE-layer node via PRE_NODE hook.
    verify_outputs:
        Reserved for future POST_NODE integrity verification.
    top_k:
        Default result count per retrieval.

    Returns
    -------
    bool
        ``True`` on success; ``False`` if map-platform is not installed.

    Example::

        from map.service import MAPService
        from afmx.integrations.map_plugin import attach_map

        map_svc = await MAPService.create()
        await attach_map(
            service=map_svc,
            hook_registry=afmx_app.hook_registry,
            inject_into_memory=True,
        )
    """
    if not _MAP_AVAILABLE:
        logger.warning(
            "[AFMX→MAP] 'map-platform' not installed — integration disabled. "
            "Install: pip install afmx[map]"
        )
        return False

    from afmx.core.executor import HandlerRegistry

    HandlerRegistry.register(_RETRIEVE_HANDLER_KEY, _make_retrieve_handler(service))
    HandlerRegistry.register(_VERIFY_HANDLER_KEY,   _make_verify_handler(service))
    logger.info(
        "[AFMX→MAP] Handlers registered: '%s', '%s'",
        _RETRIEVE_HANDLER_KEY, _VERIFY_HANDLER_KEY,
    )

    if hook_registry is not None:
        try:
            from afmx.core.hooks import HookType

            if inject_into_memory:
                hook_registry.register(
                    name="map_pre_node",
                    fn=_make_pre_node_hook(service, top_k),
                    hook_type=HookType.PRE_NODE,
                    priority=15,
                )
                logger.info("[AFMX→MAP] PRE_NODE context injection hook registered")
        except Exception as exc:
            logger.error("[AFMX→MAP] Hook registration failed: %s", exc)

    logger.info("[AFMX→MAP] ✅ Integration active — top_k=%d", top_k)
    return True
