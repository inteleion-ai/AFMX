"""
AFMX Example 03 — Conditional Routing
Classifier node outputs a category. Downstream routing activates
only the matching branch.

Topology:
    classify ──► branch_premium  (if category == "premium")
             └──► branch_standard (if category == "standard")
             └──► branch_unknown  (on failure)

Run:
    python examples/03_conditional_routing.py
"""
import asyncio, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, EdgeCondition, EdgeConditionType,
    ExecutionMode, HandlerRegistry, EventBus,
)
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def classify(inp, ctx, node):
    user_type = inp.get("input", {}).get("user_type", "standard")
    print(f"  🔎 [classify] Input user_type: '{user_type}'")
    return {"category": user_type, "score": 0.92}

async def premium_branch(inp, ctx, node):
    print("  💎 [premium_branch] Activated!")
    return {"plan": "PREMIUM", "features": ["unlimited", "priority_support", "analytics"]}

async def standard_branch(inp, ctx, node):
    print("  📦 [standard_branch] Activated!")
    return {"plan": "STANDARD", "features": ["basic", "email_support"]}

async def unknown_branch(inp, ctx, node):
    print("  ❓ [unknown_branch] Activated!")
    return {"plan": "UNKNOWN", "features": []}

for key, fn in [
    ("classify_fn", classify), ("premium_fn", premium_branch),
    ("standard_fn", standard_branch), ("unknown_fn", unknown_branch),
]:
    HandlerRegistry.register(key, fn)


# ─── Matrix ───────────────────────────────────────────────────────────────────

matrix = ExecutionMatrix(
    name="conditional-routing",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(id="classify", name="classify", type=NodeType.FUNCTION, handler="classify_fn"),
        Node(id="premium", name="premium_branch", type=NodeType.FUNCTION, handler="premium_fn"),
        Node(id="standard", name="standard_branch", type=NodeType.FUNCTION, handler="standard_fn"),
        Node(id="unknown", name="unknown_branch", type=NodeType.FUNCTION, handler="unknown_fn"),
    ],
    edges=[
        Edge(**{
            "from": "classify", "to": "premium",
            "condition": EdgeCondition(
                type=EdgeConditionType.ON_OUTPUT,
                output_key="category",
                output_value="premium",
            ),
            "label": "premium path",
        }),
        Edge(**{
            "from": "classify", "to": "standard",
            "condition": EdgeCondition(
                type=EdgeConditionType.ON_OUTPUT,
                output_key="category",
                output_value="standard",
            ),
            "label": "standard path",
        }),
        Edge(**{
            "from": "classify", "to": "unknown",
            "condition": EdgeCondition(
                type=EdgeConditionType.EXPRESSION,
                expression="output.get('category') not in ('premium', 'standard')",
            ),
            "label": "unknown path",
        }),
    ],
)


async def run_scenario(user_type: str):
    print(f"\n  ▶ Scenario: user_type='{user_type}'")
    engine = AFMXEngine()
    context = ExecutionContext(input={"user_type": user_type})
    record = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result = await engine.execute(matrix, context, record)
    print(f"    Status: {result.status} | completed={result.completed_nodes} skipped={result.skipped_nodes}")


async def main():
    print("\n═══════════════════════════════════════════")
    print("  AFMX Example 03 — Conditional Routing")
    print("═══════════════════════════════════════════")

    for user_type in ["premium", "standard", "enterprise"]:
        await run_scenario(user_type)
    print()


if __name__ == "__main__":
    asyncio.run(main())
