"""
AFMX Example 04 — Retry + Fallback
Demonstrates a flaky node that fails twice before succeeding,
and a fallback node that activates on terminal failure.

Run:
    python examples/04_retry_fallback.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, RetryPolicy, TimeoutPolicy, ExecutionMode, HandlerRegistry,
)
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Handlers ─────────────────────────────────────────────────────────────────

_call_count = 0

async def flaky_api(inp, ctx, node):
    """Fails on the first 2 attempts, succeeds on the 3rd."""
    global _call_count
    _call_count += 1
    print(f"  🌐 [flaky_api] Attempt #{_call_count}")
    if _call_count < 3:
        raise ConnectionError(f"Connection refused (attempt {_call_count})")
    return {"data": "success_on_attempt_3", "attempt": _call_count}


async def fallback_handler(inp, ctx, node):
    """Activated when flaky_api fails all retries."""
    print("  🔄 [fallback] Primary failed — using cached response")
    return {"data": "cached_fallback_data", "source": "cache"}


async def always_fails(inp, ctx, node):
    """Always raises — triggers fallback."""
    raise RuntimeError("Permanently broken")


HandlerRegistry.register("flaky_api", flaky_api)
HandlerRegistry.register("fallback_handler", fallback_handler)
HandlerRegistry.register("always_fails", always_fails)


# ─── Scenario A: Retry succeeds on 3rd attempt ────────────────────────────────

retry_matrix = ExecutionMatrix(
    name="retry-success",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(
            id="api-node",
            name="flaky_api",
            type=NodeType.FUNCTION,
            handler="flaky_api",
            retry_policy=RetryPolicy(
                retries=3,
                backoff_seconds=0.01,  # Fast in tests
                backoff_multiplier=1.5,
                jitter=False,
            ),
            timeout_policy=TimeoutPolicy(timeout_seconds=10.0),
        ),
    ],
)

# ─── Scenario B: All retries fail → fallback activates ────────────────────────

fallback_matrix = ExecutionMatrix(
    name="fallback-demo",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(
            id="broken-node",
            name="always_fails",
            type=NodeType.FUNCTION,
            handler="always_fails",
            retry_policy=RetryPolicy(retries=2, backoff_seconds=0.01, jitter=False),
            fallback_node_id="fallback-node",
        ),
        Node(
            id="fallback-node",
            name="fallback",
            type=NodeType.FUNCTION,
            handler="fallback_handler",
        ),
    ],
)


async def main():
    print("\n═══════════════════════════════════════════")
    print("  AFMX Example 04 — Retry + Fallback")
    print("═══════════════════════════════════════════\n")

    # Scenario A
    print("  ── Scenario A: Flaky API (succeeds on attempt 3) ──")
    global _call_count
    _call_count = 0

    engine = AFMXEngine()
    ctx = ExecutionContext()
    rec = ExecutionRecord(matrix_id=retry_matrix.id, matrix_name=retry_matrix.name)
    result = await engine.execute(retry_matrix, ctx, rec)

    output = result.node_results.get("api-node", {}).get("output", {})
    attempt = result.node_results.get("api-node", {}).get("attempt", "?")
    print(f"  Status: {result.status} | Succeeded on attempt: {attempt}")
    print(f"  Output: {output}\n")

    # Scenario B
    print("  ── Scenario B: Always fails → fallback activates ──")
    engine2 = AFMXEngine()
    ctx2 = ExecutionContext()
    rec2 = ExecutionRecord(matrix_id=fallback_matrix.id, matrix_name=fallback_matrix.name)
    result2 = await engine2.execute(fallback_matrix, ctx2, rec2)

    fallback_output = result2.node_results.get("fallback-node", {}).get("output", {})
    print(f"  Status: {result2.status}")
    print(f"  Fallback output: {fallback_output}\n")


if __name__ == "__main__":
    asyncio.run(main())
