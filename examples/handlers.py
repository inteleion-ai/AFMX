"""
Shared handlers for AFMX examples.
Register these with HandlerRegistry before running examples.
"""


async def echo_handler(inp: dict, ctx, node) -> dict:
    """Returns input back as output — useful for testing pipelines."""
    return {
        "echoed": inp.get("input"),
        "label": inp["params"].get("label", node.name),
        "node_id": node.id,
    }


async def noop_handler(inp: dict, ctx, node) -> dict:
    """Does nothing and succeeds."""
    return {"status": "ok", "node": node.name}


async def fail_handler(inp: dict, ctx, node) -> None:
    """Always raises — useful for testing failure paths."""
    raise RuntimeError(f"Node '{node.name}' intentionally failed")
