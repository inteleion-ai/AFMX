#!/usr/bin/env python3.10
"""
AFMX WebSocket Streaming Test
Streams real-time execution events for a matrix execution.

Usage:
    python3.10 scripts/test_ws.py
    python3.10 scripts/test_ws.py --url http://localhost:8100

Requirements:
    pip install httpx websockets
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time

import httpx

DEFAULT_URL = "http://localhost:8100"

# ─── Colours ──────────────────────────────────────────────────────────────────

EVENT_COLORS = {
    "execution.started":   "\033[36m",   # cyan
    "execution.completed": "\033[32m",   # green
    "execution.failed":    "\033[31m",   # red
    "node.started":        "\033[33m",   # yellow
    "node.completed":      "\033[32m",   # green
    "node.failed":         "\033[31m",   # red
    "node.skipped":        "\033[35m",   # magenta
    "node.retrying":       "\033[33m",   # yellow
    "node.fallback":       "\033[34m",   # blue
    "connected":           "\033[36m",   # cyan
    "ping":                "\033[90m",   # grey
    "eof":                 "\033[32m",   # green
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def color_event(event_type: str, msg: str) -> str:
    return f"{EVENT_COLORS.get(event_type, '')}{msg}{RESET}"


async def stream_and_print(ws_url: str, execution_id: str) -> None:
    """Connect to WebSocket and print events as they arrive."""
    try:
        import websockets
    except ImportError:
        print("  websockets not installed. Run: pip install websockets")
        return

    url = f"{ws_url}/afmx/ws/stream/{execution_id}"
    print(f"\n  Connecting to: {url}")

    async with websockets.connect(url) as ws:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                event = json.loads(raw)
                etype = event.get("type", "unknown")
                ts = time.strftime("%H:%M:%S")

                if etype == "ping":
                    print(color_event("ping", f"  [{ts}] ♡ heartbeat"))
                    continue

                if etype == "eof":
                    print(color_event("eof", f"\n  [{ts}] ─── Stream complete (EOF) ───\n"))
                    break

                if etype == "connected":
                    print(color_event("connected",
                          f"  [{ts}] ✓ Connected — streaming execution: {execution_id[:16]}..."))
                    continue

                data = event.get("data", {})
                node_name = data.get("node_name", "")
                node_status = data.get("status", "")
                duration = data.get("duration_ms")
                error = data.get("error", "")
                attempt = data.get("attempt", "")

                line = f"  [{ts}]  {etype:<28}"
                if node_name:
                    line += f"  node={node_name}"
                if node_status:
                    line += f"  status={node_status}"
                if duration is not None:
                    line += f"  {duration:.1f}ms"
                if attempt and attempt > 1:
                    line += f"  attempt={attempt}"
                if error:
                    line += f"  err={error[:50]}"

                print(color_event(etype, line))

            except asyncio.TimeoutError:
                print("  [timeout] No event in 30s — closing")
                break


async def run_ws_test(base_url: str) -> None:
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")

    # ─── Matrix to stream ────────────────────────────────────────────────────
    STREAM_MATRIX = {
        "name": "ws-stream-demo",
        "mode": "SEQUENTIAL",
        "nodes": [
            {"id": "n1", "name": "analyst",   "type": "FUNCTION", "handler": "analyst_agent"},
            {"id": "n2", "name": "writer",    "type": "FUNCTION", "handler": "writer_agent"},
            {"id": "n3", "name": "reviewer",  "type": "FUNCTION", "handler": "reviewer_agent"},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
        ],
    }

    RETRY_MATRIX = {
        "name": "ws-retry-demo",
        "mode": "SEQUENTIAL",
        "nodes": [{
            "id": "n1", "name": "flaky_node", "type": "FUNCTION", "handler": "flaky",
            "retry_policy": {"retries": 3, "backoff_seconds": 0.1, "jitter": False},
        }],
        "edges": [],
    }

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:

        # ── Demo 1: Stream a normal 3-node pipeline ───────────────────────────
        print(f"\n{BOLD}{'═'*55}{RESET}")
        print(f"{BOLD}  Demo 1: Stream a 3-node pipeline in real time{RESET}")
        print(f"{BOLD}{'═'*55}{RESET}")
        print("\n  Step 1: Submit async execution")

        r = await client.post("/afmx/execute/async", json={
            "matrix": STREAM_MATRIX,
            "input": {"topic": "autonomous agent systems"},
            "triggered_by": "ws-test",
        })
        resp = r.json()
        exec_id = resp["execution_id"]
        print(f"  Execution ID : {exec_id}")
        print(f"  Poll URL     : {resp['poll_url']}")
        print(f"  Stream URL   : ws://{base_url.split('//')[1]}/afmx/ws/stream/{exec_id}")
        print("\n  Step 2: Streaming events ↓\n")

        await stream_and_print(ws_url, exec_id)

        # ── Demo 2: Stream retry events ───────────────────────────────────────
        print(f"\n{BOLD}{'═'*55}{RESET}")
        print(f"{BOLD}  Demo 2: Stream retry events (NODE_RETRYING){RESET}")
        print(f"{BOLD}{'═'*55}{RESET}")
        print("\n  Submitting flaky node with retries...\n")

        r = await client.post("/afmx/execute/async", json={
            "matrix": RETRY_MATRIX,
            "input": "retry ws test",
            "triggered_by": "ws-retry-test",
        })
        resp = r.json()
        retry_exec_id = resp["execution_id"]
        print(f"  Execution ID: {retry_exec_id}\n")

        await stream_and_print(ws_url, retry_exec_id)

        # ── Demo 3: Connect BEFORE submitting (race the execution) ────────────
        print(f"\n{BOLD}{'═'*55}{RESET}")
        print(f"{BOLD}  Demo 3: Connect to stream BEFORE execution starts{RESET}")
        print(f"{BOLD}{'═'*55}{RESET}")
        print("\n  Pre-registering execution ID, then connecting WebSocket first...\n")

        r = await client.post("/afmx/execute/async", json={
            "matrix": STREAM_MATRIX,
            "input": {"topic": "streaming before submission"},
            "triggered_by": "ws-race-test",
        })
        pre_id = r.json()["execution_id"]

        # Connect to WebSocket and stream
        print(f"  Execution ID: {pre_id}")
        await stream_and_print(ws_url, pre_id)

    print(f"\n{BOLD}WebSocket streaming tests complete!{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="AFMX WebSocket streaming test")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    print(f"\n{BOLD}AFMX WebSocket Stream Test{RESET}")
    print(f"Server: {args.url}")
    print(f"Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    asyncio.run(run_ws_test(args.url))


if __name__ == "__main__":
    main()
