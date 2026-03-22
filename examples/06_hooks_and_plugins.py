"""
AFMX Example 06 — Hooks + Plugin Registry
Shows decorator-based plugin registration and pre/post node hooks
for input enrichment, audit logging, and alerting.

Run:
    python examples/06_hooks_and_plugins.py
"""
import asyncio, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, ExecutionMode,
)
from afmx.core.hooks import HookRegistry, HookPayload, HookType
from afmx.core.executor import NodeExecutor
from afmx.core.retry import RetryManager
from afmx.core.variable_resolver import VariableResolver
from afmx.plugins.registry import PluginRegistry
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Plugin Registry (decorator-style) ────────────────────────────────────────

registry = PluginRegistry()

@registry.tool("weather_tool", description="Fetch weather data", tags=["geo", "realtime"])
async def weather_tool(inp, ctx, node):
    city = inp["params"].get("city", "unknown")
    print(f"  🌤  [weather_tool] Fetching weather for: {city}")
    await asyncio.sleep(0.03)
    return {"city": city, "temp_c": 28, "condition": "Sunny", "humidity": 62}


@registry.agent("recommendation_agent", description="Suggests activities")
async def recommendation_agent(inp, ctx, node):
    weather = inp["node_outputs"].get("weather-node", {})
    temp    = weather.get("temp_c", 20)
    cond    = weather.get("condition", "Unknown")
    print(f"  🧠 [recommendation_agent] Weather: {temp}°C, {cond}")
    activity = "Go to the beach" if temp > 25 else "Visit a museum"
    return {"activity": activity, "confidence": 0.91}


# ─── Hook Registry ────────────────────────────────────────────────────────────

hooks = HookRegistry()
audit_log = []   # Simulated audit store


@hooks.pre_node("inject_trace_id", priority=10)
async def inject_trace_id(payload: HookPayload) -> HookPayload:
    """Enrich every node's input metadata with a trace ID before execution."""
    if payload.node_input and "metadata" in payload.node_input:
        payload.node_input["metadata"]["trace_id"] = f"trace-{int(time.time()*1000)}"
    return payload


@hooks.post_node("audit_logger", priority=20)
async def audit_node_result(payload: HookPayload) -> HookPayload:
    """Log every node execution outcome to an audit trail."""
    if payload.node_result:
        entry = {
            "node": payload.node.name if payload.node else "?",
            "status": payload.node_result.status,
            "duration_ms": payload.node_result.duration_ms,
            "ts": time.time(),
        }
        audit_log.append(entry)
    return payload


@hooks.post_node("alert_on_failure", priority=30)
async def alert_on_failure(payload: HookPayload) -> HookPayload:
    """Send an alert (simulated) if a node fails."""
    if payload.node_result and payload.node_result.is_terminal_failure:
        print(f"  🚨 [alert] Node '{payload.node.name}' FAILED — alerting on-call!")
    return payload


# ─── Matrix ───────────────────────────────────────────────────────────────────

# Sync plugins to HandlerRegistry
registry.sync_to_handler_registry()

matrix = ExecutionMatrix(
    name="hooks-demo",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(
            id="weather-node",
            name="weather_tool",
            type=NodeType.TOOL,
            handler="weather_tool",
            config={"params": {"city": "Hyderabad"}, "env": {}, "tags": []},
        ),
        Node(
            id="rec-node",
            name="recommendation_agent",
            type=NodeType.AGENT,
            handler="recommendation_agent",
        ),
    ],
    edges=[Edge(**{"from": "weather-node", "to": "rec-node"})],
)


async def main():
    print("\n═══════════════════════════════════════════════")
    print("  AFMX Example 06 — Hooks + Plugin Registry")
    print("═══════════════════════════════════════════════\n")

    retry_manager = RetryManager()
    executor = NodeExecutor(
        retry_manager=retry_manager,
        hook_registry=hooks,
        variable_resolver=VariableResolver(),
    )
    engine  = AFMXEngine(node_executor=executor)
    context = ExecutionContext(input={"user": "raman"})
    record  = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)

    result = await engine.execute(matrix, context, record)

    rec_output = result.node_results.get("rec-node", {}).get("output", {})

    print(f"\n  Status      : {result.status}")
    print(f"  Duration    : {result.duration_ms:.1f}ms")
    print(f"  Activity    : {rec_output.get('activity')}")
    print(f"  Confidence  : {rec_output.get('confidence')}")

    print(f"\n  📋 Audit Log ({len(audit_log)} entries):")
    for entry in audit_log:
        print(f"    • {entry['node']:25s} {entry['status']:10s} {entry['duration_ms']:.1f}ms")

    print(f"\n  🔌 Registered plugins:")
    for p in registry.list_all():
        print(f"    [{p['type']:8s}] {p['key']:25s} — {p['description']}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
