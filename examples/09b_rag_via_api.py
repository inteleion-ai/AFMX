"""
AFMX Example 09b — LangChain RAG served via the AFMX REST API
==============================================================
This variant registers the RAG pipeline as a NAMED MATRIX on the running
AFMX server, then executes it via POST /afmx/matrices/langchain-rag/execute.

Real-time streaming is available via WebSocket.

Run the AFMX server first:
    python3.10 -m afmx serve --reload

Then in another terminal:
    python examples/09b_rag_via_api.py --question "What is AFMX?"
    python examples/09b_rag_via_api.py --stream    # WebSocket streaming

Dependencies:
    pip install httpx websockets langchain langchain-openai openai numpy
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Optional

import httpx

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_URL  = os.getenv("AFMX_URL", "http://localhost:8100")
BOLD  = "\033[1m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
RED   = "\033[31m"
DIM   = "\033[2m"
RESET = "\033[0m"


# ─── The RAG Matrix Definition (sent to /afmx/matrices) ──────────────────────
# All handlers are registered inside a custom startup_handlers.py that extends
# the built-in one. See the bottom of this file for the handler registration
# code you need to add to afmx/startup_handlers.py.

RAG_MATRIX_DEFINITION = {
    "name": "langchain-rag-openai",
    "version": "1.0.0",
    "description": "LangChain RAG pipeline: doc_loader → embedder → retriever → generator → formatter",
    "tags": ["rag", "langchain", "openai"],
    "definition": {
        "name":         "langchain-rag-openai",
        "mode":         "SEQUENTIAL",
        "abort_policy": "FAIL_FAST",
        "global_timeout_seconds": 120.0,
        "nodes": [
            {
                "id":      "doc_loader",
                "name":    "Document Loader",
                "type":    "FUNCTION",
                "handler": "rag_doc_loader",
                "config":  {"params": {"chunk_size": 400, "chunk_overlap": 80}},
                "retry_policy": {"retries": 1, "backoff_seconds": 0.5},
                "timeout_policy": {"timeout_seconds": 30.0},
            },
            {
                "id":      "embedder",
                "name":    "OpenAI Embedder (text-embedding-3-small)",
                "type":    "TOOL",
                "handler": "rag_embedder",
                "retry_policy": {"retries": 3, "backoff_seconds": 2.0, "jitter": True},
                "timeout_policy": {"timeout_seconds": 60.0},
            },
            {
                "id":      "retriever",
                "name":    "Cosine Retriever",
                "type":    "TOOL",
                "handler": "rag_retriever",
                "retry_policy": {"retries": 2, "backoff_seconds": 1.0},
                "timeout_policy": {"timeout_seconds": 30.0},
            },
            {
                "id":      "generator",
                "name":    "GPT-4o-mini Answer Generator",
                "type":    "AGENT",
                "handler": "rag_generator",
                "retry_policy": {
                    "retries": 3,
                    "backoff_seconds": 2.0,
                    "backoff_multiplier": 2.0,
                    "max_backoff_seconds": 30.0,
                    "jitter": True,
                },
                "timeout_policy": {"timeout_seconds": 45.0},
                "circuit_breaker": {
                    "enabled": True,
                    "failure_threshold": 5,
                    "recovery_timeout_seconds": 60.0,
                },
            },
            {
                "id":      "formatter",
                "name":    "Response Formatter",
                "type":    "FUNCTION",
                "handler": "rag_formatter",
                "retry_policy": {"retries": 0},
                "timeout_policy": {"timeout_seconds": 5.0},
            },
        ],
        "edges": [
            {"from": "doc_loader", "to": "embedder"},
            {"from": "embedder",   "to": "retriever"},
            {"from": "retriever",  "to": "generator"},
            {"from": "generator",  "to": "formatter"},
        ],
    },
}


# ─── API helpers ──────────────────────────────────────────────────────────────

async def save_matrix(client: httpx.AsyncClient) -> None:
    """Register the RAG matrix definition on the server."""
    r = await client.post("/afmx/matrices", json=RAG_MATRIX_DEFINITION)
    if r.status_code == 201:
        print(f"  {GREEN}✓{RESET} Matrix 'langchain-rag-openai' saved")
    elif r.status_code == 422:
        data = r.json()
        print(f"  {RED}✗{RESET} Matrix validation failed: {data.get('detail')}")
        raise SystemExit(1)
    else:
        # Already exists — that's fine
        pass


async def execute_rag(
    client: httpx.AsyncClient,
    question: str,
    api_key: str,
) -> dict:
    """Execute the RAG pipeline via the REST API."""
    r = await client.post(
        "/afmx/matrices/langchain-rag-openai/execute",
        json={
            "input": {"question": question},
            "metadata": {"openai_api_key": api_key},
            "triggered_by": "example-09b",
            "tags": ["rag", "demo"],
        },
    )
    r.raise_for_status()
    return r.json()


async def get_result(client: httpx.AsyncClient, exec_id: str) -> dict:
    """Poll until terminal status, then return full result."""
    terminal = {"COMPLETED", "FAILED", "ABORTED", "TIMEOUT", "PARTIAL"}
    while True:
        r = await client.get(f"/afmx/status/{exec_id}")
        data = r.json()
        if data["status"] in terminal:
            break
        await asyncio.sleep(0.5)
        print(f"  {DIM}polling... {data['status']}{RESET}", end="\r")

    r = await client.get(f"/afmx/result/{exec_id}")
    return r.json()


# ─── WebSocket streaming ──────────────────────────────────────────────────────

async def stream_execution(exec_id: str) -> None:
    """Connect to WebSocket and print events live."""
    try:
        import websockets
    except ImportError:
        print("  pip install websockets")
        return

    ws_url = BASE_URL.replace("http://", "ws://") + f"/afmx/ws/stream/{exec_id}"
    print(f"  Connecting: {ws_url}")

    NODE_ICONS = {
        "doc_loader": "📄",
        "embedder":   "🔢",
        "retriever":  "🔍",
        "generator":  "🤖",
        "formatter":  "📝",
    }

    async with websockets.connect(ws_url) as ws:
        async for raw in ws:
            event = json.loads(raw)
            etype = event.get("type", "")

            if etype == "eof":
                print(f"\n  {GREEN}Stream ended{RESET}")
                break
            if etype in ("ping", "connected"):
                continue

            data  = event.get("data", {})
            nname = data.get("node_name", "")
            icon  = NODE_ICONS.get(nname, "●")
            ts    = time.strftime("%H:%M:%S")

            colors = {
                "node.started":        YELLOW,
                "node.completed":      GREEN,
                "node.failed":         RED,
                "node.retrying":       YELLOW,
                "execution.completed": GREEN,
                "execution.failed":    RED,
            }
            color = colors.get(etype, DIM)

            extra = ""
            if nname:
                extra += f" · {nname}"
            if "duration_ms" in data:
                extra += f" · {data['duration_ms']:.0f}ms"

            print(f"  {DIM}[{ts}]{RESET} {color}{etype}{RESET}{DIM}{extra}{RESET}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run(args) -> None:
    api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print(f"\n{RED}OPENAI_API_KEY not set{RESET}")
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  AFMX Example 09b — RAG via REST API{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")
    print(f"  Server : {BASE_URL}")
    print(f"  Model  : gpt-4o-mini")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:

        # Health check
        try:
            r = await client.get("/health")
            print(f"  Status : {GREEN}healthy{RESET} (v{r.json().get('version', '?')})")
        except Exception:
            print(f"\n{RED}Server not reachable at {BASE_URL}{RESET}")
            print("  Start it: python3.10 -m afmx serve --reload\n")
            sys.exit(1)

        # Save matrix definition
        await save_matrix(client)

        question = args.question
        print(f"\n{BOLD}Question:{RESET} {question}\n")

        if args.stream:
            # Async execute → stream
            r = await client.post(
                "/afmx/execute/async",
                json={
                    "matrix": RAG_MATRIX_DEFINITION["definition"],
                    "input": {"question": question},
                    "metadata": {"openai_api_key": api_key},
                    "triggered_by": "example-09b-stream",
                },
            )
            resp    = r.json()
            exec_id = resp["execution_id"]
            print(f"  Execution ID : {exec_id}")
            print()
            await stream_execution(exec_id)

            # Get full result
            result = await get_result(client, exec_id)
        else:
            # Named matrix execute (sync)
            t0 = time.perf_counter()
            exec_resp = await execute_rag(client, question, api_key)
            exec_id   = exec_resp["execution_id"]
            result    = await get_result(client, exec_id)
            elapsed   = (time.perf_counter() - t0) * 1000
            print(f"  {GREEN}✓ {result['status']}{RESET} in {elapsed:.0f}ms")

        # Print answer
        if result.get("status") == "COMPLETED":
            formatter_out = result.get("node_results", {}).get(
                "formatter", {}
            ).get("output", {})
            print(f"\n{'─'*65}")
            print(formatter_out.get("markdown", "No answer."))
            print(f"{'─'*65}")
        else:
            print(f"\n{RED}Failed: {result.get('error')}{RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="AFMX RAG pipeline via REST API (Example 09b)"
    )
    parser.add_argument(
        "--question", "-q",
        default="What is AFMX and what makes it different?",
    )
    parser.add_argument("--stream", "-s", action="store_true")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════════
# TO USE THIS VIA THE SERVER API:
#
# 1. Copy the RAG handlers into afmx/startup_handlers.py
#    (or import them from 09_langchain_rag_openai.py in register_all())
#
# 2. In startup_handlers.py register_all(), add:
#
#    import os
#    from examples.09_langchain_rag_openai import (
#        doc_loader_handler,
#        formatter_handler,
#        _build_embedder_node,
#        _build_retriever_node,
#        _build_generator_node,
#    )
#    api_key = os.getenv("OPENAI_API_KEY", "")
#    if api_key:
#        HandlerRegistry.register("rag_doc_loader", doc_loader_handler)
#        HandlerRegistry.register("rag_formatter",  formatter_handler)
#        _build_embedder_node(api_key)   # registers "rag_embedder"
#        _build_retriever_node(api_key)  # registers "rag_retriever"
#        _build_generator_node(api_key)  # registers "rag_generator"
#
# 3. Start the server with OPENAI_API_KEY set:
#    OPENAI_API_KEY=sk-... python3.10 -m afmx serve --reload
#
# 4. Run this script:
#    python examples/09b_rag_via_api.py --question "What is AFMX?"
# ═══════════════════════════════════════════════════════════════════════════════
