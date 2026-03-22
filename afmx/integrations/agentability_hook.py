"""
AFMX ↔ Agentability Integration
=================================

Bridges AFMX's execution engine with Agentability's observability platform.

Every AFMX node execution becomes an Agentability Decision.
Every AFMX matrix execution becomes an Agentability Session.
Circuit breaker trips become Agentability Conflicts.
Retry attempts are recorded on LLMMetrics (retry_count field).

Architecture
------------
Two complementary channels wire the two systems together:

1. HookRegistry hooks  (PRE_NODE + POST_NODE)
   - The primary channel. Fires synchronously inside NodeExecutor, giving
     access to the full node_input and NodeResult before/after execution.
   - POST_NODE hook records the completed Decision in Agentability.

2. EventBus subscriber  (all events)
   - Secondary channel for events that have no hook equivalent:
       * node.retrying      → annotates retry attempt on the active decision
       * circuit_breaker.open → record_conflict() between competing nodes
       * execution.completed/failed → close the session-level summary

Both channels share a single Tracer instance created at AFMX startup.

Enabling the integration
------------------------
Set environment variables before starting AFMX:

    AFMX_AGENTABILITY_ENABLED=true
    AFMX_AGENTABILITY_DB_PATH=/path/to/agentability.db   # default: agentability.db
    AFMX_AGENTABILITY_API_URL=http://localhost:8000       # optional — HTTP export
    AFMX_AGENTABILITY_API_KEY=your-key                   # optional

Or in .env:
    AFMX_AGENTABILITY_ENABLED=true

The integration is a no-op (zero overhead) when disabled or when the
``agentability`` package is not installed.

Decision → AFMX node type mapping
-----------------------------------
AFMX NodeType   →   Agentability DecisionType
TOOL            →   EXECUTION
AGENT           →   PLANNING
FUNCTION        →   ROUTING
<other>         →   EXECUTION  (safe default)

Session mapping
----------------
Each AFMX ExecutionRecord maps to an Agentability session:
  session_id = afmx_execution_id

This means every Decision recorded within a matrix run shares the same
session_id, allowing Agentability's causal graph and timeline views to
reconstruct the full execution graph.

Node → Agent mapping
---------------------
Each AFMX node is mapped to an Agentability agent_id:
  agent_id = "<matrix_name>.<node_name>"   e.g.  "echo-pipeline.upper"

This gives clean per-node analytics in Agentability's agent views.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

# ── Optional Agentability import ──────────────────────────────────────────────
# The agentability SDK is an optional dependency.  If it is not installed the
# integration is silently disabled so AFMX keeps working normally.

try:
    from agentability import Tracer, DecisionType
    from agentability.models import ConflictType
    _AGENTABILITY_AVAILABLE = True
except ImportError:
    _AGENTABILITY_AVAILABLE = False
    Tracer = None               # type: ignore[assignment,misc]
    DecisionType = None         # type: ignore[assignment]
    ConflictType = None         # type: ignore[assignment]


# ─── Node type → DecisionType mapping ────────────────────────────────────────

_NODE_TYPE_MAP: dict[str, Any] = {}   # populated lazily once SDK is available


def _decision_type_for(node_type: str) -> Any:
    """Map AFMX NodeType string to Agentability DecisionType."""
    global _NODE_TYPE_MAP
    if not _NODE_TYPE_MAP and _AGENTABILITY_AVAILABLE:
        _NODE_TYPE_MAP = {
            "TOOL":     DecisionType.EXECUTION,
            "AGENT":    DecisionType.PLANNING,
            "FUNCTION": DecisionType.ROUTING,
        }
    return _NODE_TYPE_MAP.get(str(node_type).upper(), DecisionType.EXECUTION if _AGENTABILITY_AVAILABLE else None)


# ─── In-flight decision state ─────────────────────────────────────────────────
# Maps  (execution_id, node_id)  →  TracingContext + start_time
# so the POST_NODE hook can close the decision opened by PRE_NODE.

_active: dict[tuple[str, str], dict[str, Any]] = {}


# ─── Hook functions ───────────────────────────────────────────────────────────

def _make_pre_node_hook(tracer: "Tracer"):  # type: ignore[name-defined]
    """Return a PRE_NODE hook closure that opens an Agentability decision."""

    async def agentability_pre_node(payload) -> Any:
        """Open a trace_decision context before the node runs."""
        if payload.node is None or payload.context is None:
            return payload

        execution_id = payload.execution_id
        node = payload.node
        node_input = payload.node_input or {}
        matrix_name = payload.matrix_name or "unknown"

        agent_id = f"{matrix_name}.{node.name}"
        session_id = execution_id
        decision_type = _decision_type_for(str(node.type))

        # Extract useful input — strip internal bookkeeping keys
        clean_input = {
            k: v for k, v in node_input.items()
            if k in ("input", "params", "variables")
        }

        key = (execution_id, node.id)
        state: dict[str, Any] = {
            "agent_id": agent_id,
            "session_id": session_id,
            "decision_type": decision_type,
            "clean_input": clean_input,
            "start_ts": time.time(),
            "ctx": None,          # TracingContext — set below
            "cm": None,           # context manager — set below
        }

        try:
            cm = tracer.trace_decision(
                agent_id=agent_id,
                decision_type=decision_type,
                session_id=session_id,
                input_data=clean_input,
                tags=[str(node.type).lower(), matrix_name],
                metadata={
                    "node_id":      node.id,
                    "node_name":    node.name,
                    "node_type":    str(node.type),
                    "matrix_name":  matrix_name,
                    "execution_id": execution_id,
                },
            )
            ctx = cm.__enter__()
            state["ctx"] = ctx
            state["cm"] = cm
            _active[key] = state
        except Exception as exc:
            logger.warning(
                "[AFMX→Agentability] PRE_NODE hook failed for '%s': %s",
                node.name, exc,
            )

        return payload

    return agentability_pre_node


def _make_post_node_hook(tracer: "Tracer"):  # type: ignore[name-defined]
    """Return a POST_NODE hook closure that closes the Agentability decision."""

    async def agentability_post_node(payload) -> Any:
        """Close the trace_decision context after the node finishes."""
        if payload.node is None:
            return payload

        execution_id = payload.execution_id
        node = payload.node
        result = payload.node_result

        key = (execution_id, node.id)
        state = _active.pop(key, None)
        if state is None:
            return payload   # PRE_NODE never ran — skip silently

        ctx = state.get("ctx")
        cm  = state.get("cm")
        if ctx is None or cm is None:
            return payload

        try:
            # ── Build decision provenance from NodeResult ─────────────────
            success      = result is not None and result.status in ("SUCCESS", "FALLBACK")
            output       = (result.output or {}) if result else {}
            error        = result.error if result else None
            duration_ms  = result.duration_ms if result else None
            attempt      = result.attempt if result else 1
            fallback_used = (result.metadata or {}).get("fallback_used", False) if result else False

            # Confidence heuristic — not stored in AFMX, so we derive one:
            #   1.0 on clean success, 0.5 on fallback, 0.0 on failure
            confidence: float = 1.0 if success and not fallback_used else (
                0.5 if fallback_used else 0.0
            )
            ctx.set_confidence(confidence)

            # Reasoning chain
            reasoning: list[str] = [f"AFMX node '{node.name}' ({node.type}) — attempt {attempt}"]
            if fallback_used:
                reasoning.append(f"Primary node failed; fallback_node executed successfully")
            if error:
                reasoning.append(f"Terminal failure: {error}")

            # Constraints violated = AFMX errors / circuit-breaker trips
            constraints_violated: list[str] = []
            if error:
                constraints_violated.append(error)

            # Constraints checked = retry policy params
            constraints_checked: list[str] = []
            if hasattr(node, "retry_policy") and node.retry_policy:
                rp = node.retry_policy
                constraints_checked.append(
                    f"retry_policy.retries={rp.retries} "
                    f"backoff={rp.backoff_seconds}s"
                )
            if hasattr(node, "timeout_policy") and node.timeout_policy:
                constraints_checked.append(
                    f"timeout={node.timeout_policy.timeout_seconds}s"
                )

            # Record the decision
            tracer.record_decision(
                output=output if isinstance(output, dict) else {"result": output},
                confidence=confidence,
                reasoning=reasoning,
                uncertainties=[error] if error and not success else [],
                constraints_checked=constraints_checked,
                constraints_violated=constraints_violated,
                quality_score=confidence,
                data_sources=[f"afmx.handler.{node.handler}"] if hasattr(node, "handler") else [],
            )

            # Annotate duration in metadata
            if duration_ms is not None:
                ctx.set_metadata("duration_ms", duration_ms)
            ctx.set_metadata("attempt",     attempt)
            ctx.set_metadata("status",      result.status if result else "UNKNOWN")
            ctx.set_metadata("fallback",    fallback_used)

        except Exception as exc:
            logger.warning(
                "[AFMX→Agentability] POST_NODE hook record_decision failed for '%s': %s",
                node.name, exc,
            )
        finally:
            # Always close the context manager so the decision is persisted
            try:
                cm.__exit__(None, None, None)
            except Exception as exc:
                logger.warning(
                    "[AFMX→Agentability] POST_NODE cm.__exit__ failed: %s", exc
                )

        return payload

    return agentability_post_node


# ─── EventBus subscriber ──────────────────────────────────────────────────────

def _make_event_handler(tracer: "Tracer"):  # type: ignore[name-defined]
    """
    Return an EventBus-compatible async callable that handles AFMX events
    not covered by the hook pair (retrying, circuit breaker, conflicts).
    """

    async def on_afmx_event(event) -> None:  # AFMXEvent
        event_type = str(event.type)
        data       = event.data or {}
        exec_id    = event.execution_id or ""

        # ── node.retrying — record a synthetic LLM call to track retry cost ──
        if event_type == "node.retrying":
            node_id   = data.get("node_id", "unknown")
            attempt   = data.get("attempt", 1)
            error_msg = data.get("error", "")
            delay     = data.get("retry_delay_seconds", 0)
            try:
                tracer.record_llm_call(
                    agent_id=node_id,
                    provider="afmx",
                    model="internal_retry",
                    prompt_tokens=0,
                    completion_tokens=0,
                    latency_ms=delay * 1000,
                    cost_usd=0.0,
                    finish_reason=f"retry_{attempt}",
                    metadata={
                        "retry_attempt": attempt,
                        "error":         error_msg,
                        "execution_id":  exec_id,
                    },
                )
            except Exception as exc:
                logger.debug("[AFMX→Agentability] retry event record failed: %s", exc)

        # ── circuit_breaker.open — record as a conflict between nodes ─────────
        elif event_type == "circuit_breaker.open":
            node_id = data.get("node_id", "unknown")
            try:
                tracer.record_conflict(
                    session_id=exec_id or node_id,
                    conflict_type=ConflictType.RESOURCE_CONFLICT,
                    involved_agents=[node_id, "circuit_breaker"],
                    agent_positions={
                        node_id:          {"state": "failing",  "action": "blocked"},
                        "circuit_breaker":{"state": "open",     "action": "protecting"},
                    },
                    severity=0.8,
                    resolution_strategy="circuit_breaker_isolation",
                    metadata={"execution_id": exec_id},
                )
            except Exception as exc:
                logger.debug("[AFMX→Agentability] circuit breaker conflict failed: %s", exc)

        # ── execution.completed / failed — log summary ────────────────────────
        elif event_type in ("execution.completed", "execution.failed"):
            completed = data.get("completed_nodes", 0)
            failed    = data.get("failed_nodes", 0)
            duration  = data.get("duration_ms", 0)
            logger.info(
                "[AFMX→Agentability] session=%s  %s  nodes=%d/%d  failed=%d  %.1fms",
                exec_id[:12] if exec_id else "—",
                event_type,
                completed,
                completed + failed,
                failed,
                duration or 0,
            )

    return on_afmx_event


# ─── Public entry point ───────────────────────────────────────────────────────

def attach_to_afmx(
    hook_registry,
    event_bus,
    *,
    db_path: str = "agentability.db",
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional["Tracer"]:  # type: ignore[name-defined]
    """
    Attach Agentability observability to a running AFMX instance.

    Parameters
    ----------
    hook_registry   afmx_app.hook_registry
    event_bus       afmx_app.event_bus
    db_path         SQLite path for offline storage (default: agentability.db)
    api_url         Optional Agentability platform URL for live export
    api_key         Optional API key for the platform

    Returns
    -------
    Tracer instance, or None if agentability is not installed / attach failed.

    Called automatically from AFMXApplication.startup() when
    AFMX_AGENTABILITY_ENABLED=true.  Can also be called manually:

        from afmx.integrations.agentability_hook import attach_to_afmx
        tracer = attach_to_afmx(
            afmx_app.hook_registry,
            afmx_app.event_bus,
            db_path="./obs.db",
        )
    """
    if not _AGENTABILITY_AVAILABLE:
        logger.warning(
            "[AFMX→Agentability] 'agentability' package not installed — "
            "observability integration disabled.  "
            "Install with: pip install agentability"
        )
        return None

    try:
        offline = api_url is None
        tracer: Tracer = Tracer(
            offline_mode=offline,
            storage_backend="sqlite",
            database_path=db_path,
            api_endpoint=api_url,
            api_key=api_key,
        )
    except Exception as exc:
        logger.error(
            "[AFMX→Agentability] Failed to create Tracer: %s — "
            "integration disabled.", exc,
        )
        return None

    # ── Register hooks ────────────────────────────────────────────────────────
    try:
        from afmx.core.hooks import HookType

        hook_registry.register(
            name="agentability_pre_node",
            fn=_make_pre_node_hook(tracer),
            hook_type=HookType.PRE_NODE,
            priority=10,    # run first so timing is accurate
        )
        hook_registry.register(
            name="agentability_post_node",
            fn=_make_post_node_hook(tracer),
            hook_type=HookType.POST_NODE,
            priority=990,   # run last so node_result is fully populated
        )
        logger.info("[AFMX→Agentability] PRE_NODE + POST_NODE hooks registered")
    except Exception as exc:
        logger.error(
            "[AFMX→Agentability] Hook registration failed: %s", exc
        )

    # ── Subscribe to EventBus ─────────────────────────────────────────────────
    try:
        event_bus.subscribe_all(_make_event_handler(tracer))
        logger.info("[AFMX→Agentability] EventBus subscriber registered")
    except Exception as exc:
        logger.error(
            "[AFMX→Agentability] EventBus subscription failed: %s", exc
        )

    logger.info(
        "[AFMX→Agentability] ✅ Integration active — "
        "db=%s  api=%s",
        db_path,
        api_url or "offline (SQLite only)",
    )
    return tracer
