"""
AFMX Startup Handlers

Fix: handlers are now registered via BOTH HandlerRegistry (engine lookup)
     AND PluginRegistry (so GET /afmx/plugins returns real data).
     Previously only HandlerRegistry was used, leaving /afmx/plugins empty.

Handler signature (always this exact shape):
    async def my_handler(node_input: dict, context: ExecutionContext, node: Node) -> Any:
        raw_input  = node_input["input"]        # matrix-level input payload
        params     = node_input["params"]        # resolved node config params
        variables  = node_input["variables"]     # runtime variables
        node_outs  = node_input["node_outputs"]  # upstream node results
        memory     = node_input["memory"]        # shared execution memory
        metadata   = node_input["metadata"]      # execution metadata
        return {"result": "your output here"}   # anything JSON-serializable
"""
from __future__ import annotations
import asyncio
import logging

from afmx.core.executor import HandlerRegistry
from afmx.plugins.registry import default_registry

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL HANDLERS — deterministic data transforms
# ─────────────────────────────────────────────────────────────────────────────

async def echo_handler(node_input: dict, context, node) -> dict:
    """Returns input back as-is. Useful for testing and debugging pipelines."""
    return {
        "echo": node_input.get("input"),
        "node": node.name,
        "params": node_input.get("params", {}),
    }


async def upper_handler(node_input: dict, context, node) -> dict:
    """Uppercases string input."""
    raw = node_input.get("input", "")
    text = raw if isinstance(raw, str) else str(raw)
    return {"result": text.upper(), "original": text}


async def concat_handler(node_input: dict, context, node) -> dict:
    """Concatenates upstream node outputs into one string."""
    node_outputs = node_input.get("node_outputs", {})
    parts = []
    for nid, out in node_outputs.items():
        if isinstance(out, dict) and "result" in out:
            parts.append(str(out["result"]))
        else:
            parts.append(str(out))
    return {"result": " | ".join(parts), "parts": parts}


async def multiply_handler(node_input: dict, context, node) -> dict:
    """Multiplies input value by a factor set in params."""
    factor = node_input.get("params", {}).get("factor", 2)
    value = node_input.get("input", 1)
    if isinstance(value, dict):
        value = value.get("value", 1)
    return {"result": value * factor, "factor": factor}


async def summarize_handler(node_input: dict, context, node) -> dict:
    """Simulates an AI summarization step with a 100ms delay."""
    await asyncio.sleep(0.1)
    raw = node_input.get("input", "")
    text = raw if isinstance(raw, str) else str(raw)
    summary = text[:80] + ("..." if len(text) > 80 else "")
    return {"summary": summary, "original_length": len(text), "summary_length": len(summary)}


async def validate_handler(node_input: dict, context, node) -> dict:
    """Validates that required fields exist in input."""
    params = node_input.get("params", {})
    required_fields = params.get("required_fields", [])
    raw_input = node_input.get("input", {})
    data = raw_input if isinstance(raw_input, dict) else {}
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    return {"valid": True, "checked_fields": required_fields, "data": data}


async def enrich_handler(node_input: dict, context, node) -> dict:
    """Enriches data with metadata from context."""
    params = node_input.get("params", {})
    raw_input = node_input.get("input", {})
    data = raw_input if isinstance(raw_input, dict) else {"value": raw_input}
    enriched = {
        **data,
        "enriched": True,
        "tags": params.get("tags", []),
        "source": params.get("source", "afmx"),
        "tenant": node_input.get("metadata", {}).get("tenant_id", "default"),
    }
    return enriched


async def route_handler(node_input: dict, context, node) -> dict:
    """Classifies input to route downstream execution."""
    raw_input = node_input.get("input", "")
    text = str(raw_input).lower()
    if any(w in text for w in ["error", "fail", "broken"]):
        category = "error"
    elif any(w in text for w in ["urgent", "critical", "asap"]):
        category = "urgent"
    else:
        category = "normal"
    return {"category": category, "input": raw_input}


# ─────────────────────────────────────────────────────────────────────────────
# AGENT HANDLERS — simulate AI reasoning nodes
# ─────────────────────────────────────────────────────────────────────────────

async def analyst_agent(node_input: dict, context, node) -> dict:
    """Simulates a data analysis agent."""
    await asyncio.sleep(0.05)
    raw_input = node_input.get("input", {})
    return {
        "analysis": f"Analyzed: {raw_input}",
        "confidence": 0.87,
        "recommendations": ["action_a", "action_b"],
        "agent": "analyst",
    }


async def writer_agent(node_input: dict, context, node) -> dict:
    """Simulates a content writing agent."""
    await asyncio.sleep(0.05)
    node_outputs = node_input.get("node_outputs", {})
    analysis = node_outputs.get("analyst") or node_input.get("input", "")
    return {
        "content": f"Report based on: {analysis}",
        "word_count": 42,
        "agent": "writer",
    }


async def reviewer_agent(node_input: dict, context, node) -> dict:
    """Simulates a review/QA agent."""
    await asyncio.sleep(0.05)
    node_outputs = node_input.get("node_outputs", {})
    return {
        "approved": True,
        "score": 9.2,
        "feedback": "Looks good",
        "reviewed_nodes": list(node_outputs.keys()),
        "agent": "reviewer",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FAULT SIMULATION HANDLERS — for testing retry/fallback/circuit-breaker
# ─────────────────────────────────────────────────────────────────────────────

async def flaky_handler(node_input: dict, context, node) -> dict:
    """Fails on first 2 calls, succeeds on 3rd. Tests retry logic."""
    count = context.get_memory("_flaky_count", 0)
    count += 1
    context.set_memory("_flaky_count", count)
    if count < 3:
        raise ConnectionError(f"Transient failure #{count}")
    return {"recovered": True, "attempt": count}


async def always_fail_handler(node_input: dict, context, node) -> dict:
    """Always raises. Tests failure paths and fallback."""
    raise RuntimeError("Simulated permanent failure — use fallback!")


async def fallback_recovery_handler(node_input: dict, context, node) -> dict:
    """Fallback handler that recovers gracefully."""
    return {"fallback": True, "recovered": True, "message": "Recovered via fallback node"}


async def slow_handler(node_input: dict, context, node) -> dict:
    """Sleeps N seconds. Tests timeout enforcement."""
    params = node_input.get("params", {})
    sleep_seconds = params.get("sleep_seconds", 2.0)
    await asyncio.sleep(sleep_seconds)
    return {"slept_for": sleep_seconds}


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

# Metadata for each handler: (fn, plugin_type, description, tags)
_HANDLERS = [
    # ── Tools ────────────────────────────────────────────────────────────────
    ("echo",              echo_handler,             "tool",     "Returns input back as-is. Useful for testing.",      ["debug", "test"]),
    ("upper",             upper_handler,            "tool",     "Uppercases string input.",                            ["string", "transform"]),
    ("concat",            concat_handler,           "tool",     "Concatenates upstream node outputs.",                 ["string", "merge"]),
    ("multiply",          multiply_handler,         "tool",     "Multiplies input value by params.factor.",            ["math"]),
    ("summarize",         summarize_handler,        "tool",     "Simulates AI summarization (100ms stub).",            ["nlp", "stub"]),
    ("validate",          validate_handler,         "tool",     "Validates required fields in input dict.",            ["validation"]),
    ("enrich",            enrich_handler,           "tool",     "Enriches data with context metadata.",                ["transform"]),
    ("route",             route_handler,            "tool",     "Classifies input for conditional routing.",           ["routing"]),
    # ── Agents ───────────────────────────────────────────────────────────────
    ("analyst_agent",     analyst_agent,            "agent",    "Simulates a data analysis agent (50ms stub).",        ["agent", "analysis"]),
    ("writer_agent",      writer_agent,             "agent",    "Simulates a content writing agent (50ms stub).",      ["agent", "content"]),
    ("reviewer_agent",    reviewer_agent,           "agent",    "Simulates a review/QA agent (50ms stub).",            ["agent", "qa"]),
    # ── Fault simulation ─────────────────────────────────────────────────────
    ("flaky",             flaky_handler,            "tool",     "Fails 2× then succeeds. Tests retry logic.",          ["test", "fault"]),
    ("always_fail",       always_fail_handler,      "tool",     "Always raises. Tests fallback paths.",                ["test", "fault"]),
    ("fallback_recovery", fallback_recovery_handler,"tool",     "Graceful fallback recovery handler.",                 ["test", "fallback"]),
    ("slow",              slow_handler,             "tool",     "Sleeps params.sleep_seconds. Tests timeouts.",        ["test", "timeout"]),
]


def register_all() -> None:
    """
    Register all built-in handlers.

    Dual registration:
      1. HandlerRegistry   — for engine handler lookup during execution
      2. PluginRegistry    — for GET /afmx/plugins discovery
    """
    for key, fn, plugin_type, description, tags in _HANDLERS:
        HandlerRegistry.register(key, fn)
        default_registry.register(
            key=key,
            handler=fn,
            plugin_type=plugin_type,
            description=description,
            tags=tags,
        )

    logger.info(
        f"[startup_handlers] Registered {len(_HANDLERS)} handlers: "
        f"{[h[0] for h in _HANDLERS]}"
    )


# Auto-register when imported
register_all()

# ── Upgrade to realistic agent handlers if available ─────────────────────────
# realistic_handlers.py (project root) overrides the analyst/writer/reviewer
# stubs with versions that produce real confidence scores, reasoning chains,
# token usage, and constraint checking — making both dashboards meaningful.
try:
    import importlib, sys, os
    _root = os.path.dirname(os.path.dirname(__file__))  # project root
    if _root not in sys.path:
        sys.path.insert(0, _root)
    _rh = importlib.import_module("realistic_handlers")
    _rh.register_realistic()
    logger.info("[startup_handlers] Realistic agents loaded — rich dashboard data enabled")
except ImportError:
    logger.debug("[startup_handlers] realistic_handlers.py not found — using stubs (fine for basic testing)")
except Exception as _e:
    logger.warning(f"[startup_handlers] realistic_handlers load failed: {_e}")
