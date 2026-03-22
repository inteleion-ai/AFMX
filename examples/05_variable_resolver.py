"""
AFMX Example 05 — Variable Resolver
Demonstrates {{template}} expressions in node config params.
Upstream outputs, memory, and variables are all injectable.

Run:
    python examples/05_variable_resolver.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from afmx import (
    AFMXEngine, ExecutionMatrix, ExecutionContext, ExecutionRecord,
    Node, NodeType, Edge, ExecutionMode, HandlerRegistry,
    NodeConfig,
)
from afmx.core.variable_resolver import VariableResolver
from afmx.core.executor import NodeExecutor
from afmx.core.retry import RetryManager
import logging
logging.basicConfig(level=logging.WARNING)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def lookup_user(inp, ctx, node):
    user_id = inp["params"].get("user_id", "unknown")
    print(f"  👤 [lookup_user] Fetching user: '{user_id}'")
    return {
        "id": user_id,
        "name": "Raman",
        "plan": "enterprise",
        "credits": 5000,
    }


async def build_prompt(inp, ctx, node):
    # These params were resolved from {{node.user-node.output.name}} etc.
    name        = inp["params"].get("name", "?")
    plan        = inp["params"].get("plan", "?")
    credits     = inp["params"].get("credits", 0)
    task        = inp["params"].get("task", "?")
    print(f"  🧠 [build_prompt] Building for user='{name}' plan='{plan}'")
    prompt = (
        f"You are assisting {name} (plan: {plan}, credits: {credits}). "
        f"Task: {task}"
    )
    return {"prompt": prompt, "tokens_estimate": len(prompt.split())}


async def execute_agent(inp, ctx, node):
    prompt = inp["params"].get("prompt", "?")
    max_tokens = inp["params"].get("max_tokens", 1000)
    print(f"  🤖 [execute_agent] Running with max_tokens={max_tokens}")
    return {
        "response": f"Agent response to: {prompt[:40]}...",
        "tokens_used": 342,
        "model": "gpt-enterprise",
    }


HandlerRegistry.register("lookup_user",  lookup_user)
HandlerRegistry.register("build_prompt", build_prompt)
HandlerRegistry.register("execute_agent", execute_agent)


# ─── Matrix ───────────────────────────────────────────────────────────────────

matrix = ExecutionMatrix(
    name="variable-resolution-demo",
    mode=ExecutionMode.SEQUENTIAL,
    nodes=[
        Node(
            id="user-node",
            name="lookup_user",
            type=NodeType.FUNCTION,
            handler="lookup_user",
            config=NodeConfig(params={
                # {{variables.user_id}} resolved from ExecutionContext.variables
                "user_id": "{{variables.user_id}}",
            }),
        ),
        Node(
            id="prompt-node",
            name="build_prompt",
            type=NodeType.FUNCTION,
            handler="build_prompt",
            config=NodeConfig(params={
                # Resolved from upstream node output
                "name":    "{{node.user-node.output.name}}",
                "plan":    "{{node.user-node.output.plan}}",
                "credits": "{{node.user-node.output.credits}}",
                # Resolved from execution input
                "task":    "{{input.task}}",
            }),
        ),
        Node(
            id="agent-node",
            name="execute_agent",
            type=NodeType.FUNCTION,
            handler="execute_agent",
            config=NodeConfig(params={
                # Resolved from previous node output
                "prompt":     "{{node.prompt-node.output.prompt}}",
                # Resolved from runtime variables
                "max_tokens": "{{variables.max_tokens}}",
            }),
        ),
    ],
    edges=[
        Edge(**{"from": "user-node",   "to": "prompt-node"}),
        Edge(**{"from": "prompt-node", "to": "agent-node"}),
    ],
)


# ─── Execute ──────────────────────────────────────────────────────────────────

async def main():
    print("\n═══════════════════════════════════════════")
    print("  AFMX Example 05 — Variable Resolver")
    print("═══════════════════════════════════════════\n")

    # Build engine with variable resolver wired into NodeExecutor
    resolver      = VariableResolver()
    retry_manager = RetryManager()
    executor      = NodeExecutor(retry_manager=retry_manager, variable_resolver=resolver)
    engine        = AFMXEngine(node_executor=executor)

    context = ExecutionContext(
        input={"task": "Summarise the latest AI research papers"},
        variables={
            "user_id":    "user_9012",
            "max_tokens": 2048,
        },
    )
    record = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)

    result = await engine.execute(matrix, context, record)

    agent_out = result.node_results.get("agent-node", {}).get("output", {})
    print(f"\n  Status     : {result.status}")
    print(f"  Duration   : {result.duration_ms:.1f}ms")
    print(f"  Response   : {agent_out.get('response')}")
    print(f"  Tokens used: {agent_out.get('tokens_used')}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
