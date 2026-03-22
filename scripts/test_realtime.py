#!/usr/bin/env python3.10
"""
AFMX Real-Time Python Test Suite
Tests every API endpoint with proper assertions and coloured output.
Runs against the live server at localhost:8100.

Usage:
    python3.10 scripts/test_realtime.py
    python3.10 scripts/test_realtime.py --url http://your-server:8100
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:8100"


# ─── Colours ──────────────────────────────────────────────────────────────────

class C:
    GREEN  = "\033[32m"
    RED    = "\033[31m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


def ok(msg: str)      -> None: print(f"{C.GREEN}  ✓ {msg}{C.RESET}")
def fail(msg: str)    -> None: print(f"{C.RED}  ✗ {msg}{C.RESET}"); sys.exit(1)
def warn(msg: str)    -> None: print(f"{C.YELLOW}  ! {msg}{C.RESET}")
def info(msg: str)    -> None: print(f"    {msg}")
def section(title: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}{'═' * 50}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'═' * 50}{C.RESET}")


def pp(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


# ─── Test state ───────────────────────────────────────────────────────────────

results = {"passed": 0, "failed": 0}

def assert_eq(label: str, actual, expected) -> None:
    if actual == expected:
        ok(label)
        results["passed"] += 1
    else:
        fail(f"{label} — expected {expected!r}, got {actual!r}")
        results["failed"] += 1


def assert_in(label: str, key: str, data: dict) -> None:
    if key in data:
        ok(label)
        results["passed"] += 1
    else:
        fail(f"{label} — key '{key}' missing from: {list(data.keys())}")
        results["failed"] += 1


# ─── Matrix definitions ───────────────────────────────────────────────────────

SINGLE_ECHO = {
    "name": "single-echo",
    "mode": "SEQUENTIAL",
    "nodes": [{"id": "n1", "name": "echo", "type": "FUNCTION", "handler": "echo"}],
    "edges": [],
}

CHAIN_3 = {
    "name": "chain-3",
    "mode": "SEQUENTIAL",
    "nodes": [
        {"id": "n1", "name": "echo",      "type": "FUNCTION", "handler": "echo"},
        {"id": "n2", "name": "uppercase", "type": "FUNCTION", "handler": "upper"},
        {"id": "n3", "name": "summarize", "type": "FUNCTION", "handler": "summarize"},
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
}

PARALLEL_3 = {
    "name": "parallel-3",
    "mode": "PARALLEL",
    "nodes": [
        {"id": "p1", "name": "analyst",  "type": "FUNCTION", "handler": "analyst_agent"},
        {"id": "p2", "name": "enricher", "type": "FUNCTION", "handler": "enrich"},
        {"id": "p3", "name": "echo2",    "type": "FUNCTION", "handler": "echo"},
    ],
    "edges": [],
}

HYBRID_DAG = {
    "name": "hybrid-dag",
    "mode": "HYBRID",
    "nodes": [
        {"id": "root",  "name": "analyst",  "type": "FUNCTION", "handler": "analyst_agent"},
        {"id": "left",  "name": "writer",   "type": "FUNCTION", "handler": "writer_agent"},
        {"id": "right", "name": "reviewer", "type": "FUNCTION", "handler": "reviewer_agent"},
        {"id": "final", "name": "concat",   "type": "FUNCTION", "handler": "concat"},
    ],
    "edges": [
        {"from": "root",  "to": "left"},
        {"from": "root",  "to": "right"},
        {"from": "left",  "to": "final"},
        {"from": "right", "to": "final"},
    ],
}

RETRY_FLOW = {
    "name": "retry-flow",
    "mode": "SEQUENTIAL",
    "nodes": [{
        "id": "n1", "name": "flaky", "type": "FUNCTION", "handler": "flaky",
        "retry_policy": {"retries": 3, "backoff_seconds": 0.1, "jitter": False},
    }],
    "edges": [],
}

CONTINUE_FLOW = {
    "name": "continue-flow",
    "mode": "SEQUENTIAL",
    "abort_policy": "CONTINUE",
    "nodes": [
        {"id": "n1", "name": "ok1",  "type": "FUNCTION", "handler": "echo"},
        {"id": "n2", "name": "fail", "type": "FUNCTION", "handler": "always_fail"},
        {"id": "n3", "name": "ok2",  "type": "FUNCTION", "handler": "upper"},
    ],
    "edges": [],
}

VAR_RESOLVER = {
    "name": "var-resolver",
    "mode": "SEQUENTIAL",
    "nodes": [{
        "id": "n1", "name": "multiply", "type": "FUNCTION", "handler": "multiply",
        "config": {"params": {"factor": "{{variables.factor}}"}},
    }],
    "edges": [],
}

CONDITIONAL_FLOW = {
    "name": "conditional-flow",
    "mode": "SEQUENTIAL",
    "nodes": [
        {"id": "n1", "name": "router",   "type": "FUNCTION", "handler": "route"},
        {"id": "n2", "name": "on-error", "type": "FUNCTION", "handler": "echo"},
        {"id": "n3", "name": "on-ok",    "type": "FUNCTION", "handler": "upper"},
    ],
    "edges": [
        {"from": "n1", "to": "n2",
         "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "error"}},
        {"from": "n1", "to": "n3",
         "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "normal"}},
    ],
}

NAMED_MATRIX = {
    "name": "saved-pipeline",
    "version": "1.0.0",
    "description": "Research pipeline saved by name",
    "tags": ["research", "agents"],
    "definition": {
        "name": "saved-pipeline",
        "mode": "SEQUENTIAL",
        "nodes": [
            {"id": "a", "name": "analyst", "type": "FUNCTION", "handler": "analyst_agent"},
            {"id": "w", "name": "writer",  "type": "FUNCTION", "handler": "writer_agent"},
        ],
        "edges": [{"from": "a", "to": "w"}],
    },
}


# ─── Test functions ───────────────────────────────────────────────────────────

async def run_tests(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as c:

        # ── 1. Health ─────────────────────────────────────────────────────────
        section("1. HEALTH CHECK")
        r = await c.get("/health")
        data = r.json()
        assert_eq("HTTP 200",         r.status_code, 200)
        assert_eq("status=healthy",   data["status"], "healthy")
        assert_in("uptime_seconds",   "uptime_seconds", data)
        assert_in("concurrency",      "concurrency", data)
        info(f"uptime={data['uptime_seconds']}s  store={data.get('store_backend')}")

        r = await c.get("/")
        assert_eq("Root 200",         r.status_code, 200)

        # ── 2. Validate ───────────────────────────────────────────────────────
        section("2. VALIDATE")

        r = await c.post("/afmx/validate", json={"matrix": SINGLE_ECHO})
        data = r.json()
        assert_eq("Validate 200",      r.status_code, 200)
        assert_eq("valid=True",        data["valid"], True)
        assert_eq("node_count=1",      data["node_count"], 1)
        assert_eq("exec order len=1",  len(data["execution_order"]), 1)

        r = await c.post("/afmx/validate", json={"matrix": {
            "nodes": [
                {"id": "a", "name": "a", "type": "FUNCTION", "handler": "h"},
                {"id": "b", "name": "b", "type": "FUNCTION", "handler": "h"},
            ],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
        }})
        data = r.json()
        assert_eq("Cycle invalid",     data["valid"], False)
        assert_eq("Has errors",        len(data["errors"]) > 0, True)

        # ── 3. Execute — single node ──────────────────────────────────────────
        section("3. EXECUTE — SINGLE NODE")

        r = await c.post("/afmx/execute", json={
            "matrix": SINGLE_ECHO,
            "input": {"query": "hello AFMX", "user": "raman"},
            "triggered_by": "py-test",
            "tags": ["test"],
        })
        data = r.json()
        assert_eq("Execute 200",              r.status_code, 200)
        assert_eq("status=COMPLETED",         data["status"], "COMPLETED")
        assert_eq("completed_nodes=1",        data["completed_nodes"], 1)
        assert_eq("failed_nodes=0",           data["failed_nodes"], 0)
        assert_in("execution_id",             "execution_id", data)
        assert_in("node_results",             "node_results", data)
        assert_in("duration_ms",              "duration_ms", data)
        pp(data)

        exec_id = data["execution_id"]
        info(f"Execution ID: {exec_id}")

        # ── 4. Status & Result ────────────────────────────────────────────────
        section("4. STATUS & RESULT LOOKUP")

        r = await c.get(f"/afmx/status/{exec_id}")
        data = r.json()
        assert_eq("Status 200",            r.status_code, 200)
        assert_eq("Status COMPLETED",      data["status"], "COMPLETED")
        assert_eq("ID matches",            data["execution_id"], exec_id)

        r = await c.get(f"/afmx/result/{exec_id}")
        data = r.json()
        assert_eq("Result 200",            r.status_code, 200)
        assert_eq("Node results present",  len(data["node_results"]) > 0, True)

        r = await c.get("/afmx/status/nonexistent-id-xyz-123")
        assert_eq("404 for unknown ID",    r.status_code, 404)

        # ── 5. Sequential chain ───────────────────────────────────────────────
        section("5. SEQUENTIAL CHAIN (echo→upper→summarize)")

        r = await c.post("/afmx/execute", json={
            "matrix": CHAIN_3,
            "input": "The Agent Flow Matrix Execution Engine handles deterministic autonomous agent execution",
            "triggered_by": "py-test",
        })
        data = r.json()
        assert_eq("Chain COMPLETED",       data["status"], "COMPLETED")
        assert_eq("3 nodes done",          data["completed_nodes"], 3)
        pp(data)

        # ── 6. Parallel ───────────────────────────────────────────────────────
        section("6. PARALLEL EXECUTION")

        r = await c.post("/afmx/execute", json={
            "matrix": PARALLEL_3,
            "input": {"query": "parallel test", "user": "afmx"},
        })
        data = r.json()
        assert_eq("Parallel COMPLETED",    data["status"], "COMPLETED")
        assert_eq("3 nodes done",          data["completed_nodes"], 3)
        info(f"Duration: {data['duration_ms']:.1f}ms")

        # ── 7. Hybrid DAG ─────────────────────────────────────────────────────
        section("7. HYBRID DAG (fan-out/fan-in)")

        r = await c.post("/afmx/execute", json={
            "matrix": HYBRID_DAG,
            "input": {"topic": "autonomous agents in production"},
        })
        data = r.json()
        assert_eq("Hybrid COMPLETED",      data["status"], "COMPLETED")
        assert_eq("4 nodes done",          data["completed_nodes"], 4)
        info(f"Duration: {data['duration_ms']:.1f}ms")

        # ── 8. Variable resolver ──────────────────────────────────────────────
        section("8. VARIABLE RESOLVER ({{variables.factor}})")

        r = await c.post("/afmx/execute", json={
            "matrix": VAR_RESOLVER,
            "input": 7,
            "variables": {"factor": 6},
        })
        data = r.json()
        assert_eq("Var resolver COMPLETED", data["status"], "COMPLETED")
        node_out = data["node_results"]["n1"]["output"]
        assert_eq("7 × 6 = 42",            node_out.get("result"), 42)
        info(f"Output: {node_out}")

        # ── 9. Conditional routing ────────────────────────────────────────────
        section("9. CONDITIONAL EDGE ROUTING")

        r = await c.post("/afmx/execute", json={
            "matrix": CONDITIONAL_FLOW,
            "input": "this is a normal request",
        })
        data = r.json()
        assert_eq("Conditional COMPLETED",     data["status"], "COMPLETED")
        assert_eq("At least 1 skipped",        data["skipped_nodes"] >= 1, True)
        info(f"completed={data['completed_nodes']} skipped={data['skipped_nodes']}")

        # ── 10. Retry logic ───────────────────────────────────────────────────
        section("10. RETRY — flaky node (fails twice, succeeds on 3rd)")

        r = await c.post("/afmx/execute", json={
            "matrix": RETRY_FLOW,
            "input": "retry test",
        })
        data = r.json()
        assert_eq("Retry COMPLETED",           data["status"], "COMPLETED")
        attempt = data["node_results"]["n1"]["attempt"]
        assert_eq("Succeeded on attempt 3",    attempt, 3)
        info(f"Attempt: {attempt}")

        # ── 11. CONTINUE policy → PARTIAL ─────────────────────────────────────
        section("11. CONTINUE POLICY → PARTIAL STATUS")

        r = await c.post("/afmx/execute", json={
            "matrix": CONTINUE_FLOW,
            "input": "resilience test",
        })
        data = r.json()
        assert_eq("Status=PARTIAL",            data["status"], "PARTIAL")
        assert_eq("failed_nodes=1",            data["failed_nodes"], 1)
        assert_eq("completed_nodes=2",         data["completed_nodes"], 2)
        info("Matrix ran all nodes despite one failure ✓")

        # ── 12. Async execute + poll ──────────────────────────────────────────
        section("12. ASYNC EXECUTE + POLL")

        r = await c.post("/afmx/execute/async", json={
            "matrix": CHAIN_3,
            "input": "async test input",
            "triggered_by": "async-py-test",
        })
        assert_eq("Async 202",          r.status_code, 202)
        async_data = r.json()
        assert_in("execution_id",       "execution_id", async_data)
        assert_in("poll_url",           "poll_url", async_data)
        assert_in("stream_url",         "stream_url", async_data)

        async_id = async_data["execution_id"]
        info(f"Async ID: {async_id}")

        final_status = None
        for i in range(20):
            await asyncio.sleep(0.3)
            r = await c.get(f"/afmx/status/{async_id}")
            final_status = r.json()["status"]
            if final_status in ("COMPLETED", "FAILED", "PARTIAL"):
                break
        assert_eq("Async COMPLETED",    final_status, "COMPLETED")

        # ── 13. Named matrices ────────────────────────────────────────────────
        section("13. NAMED MATRICES")

        r = await c.post("/afmx/matrices", json=NAMED_MATRIX)
        assert_eq("Save matrix 201",    r.status_code, 201)

        r = await c.get("/afmx/matrices")
        data = r.json()
        assert_eq("List matrices 200",  r.status_code, 200)
        assert_eq("Count >= 1",         data["count"] >= 1, True)

        r = await c.get("/afmx/matrices/saved-pipeline")
        assert_eq("Get matrix 200",     r.status_code, 200)

        r = await c.post("/afmx/matrices/saved-pipeline/execute", json={
            "input": {"topic": "AFMX named matrix test"},
        })
        data = r.json()
        assert_eq("Named execute done", data["status"], "COMPLETED")

        # ── 14. List executions ───────────────────────────────────────────────
        section("14. LIST EXECUTIONS")

        r = await c.get("/afmx/executions?limit=5")
        data = r.json()
        assert_eq("List 200",           r.status_code, 200)
        assert_in("count",              "count", data)
        assert_eq("Has executions",     data["count"] > 0, True)
        info(f"Total executions so far: {data['count']}")

        r = await c.get("/afmx/executions?status_filter=COMPLETED&limit=3")
        data = r.json()
        for ex in data["executions"]:
            assert_eq(f"COMPLETED filter", ex["status"], "COMPLETED")

        r = await c.get("/afmx/executions?status_filter=BADVALUE")
        assert_eq("Invalid filter 400", r.status_code, 400)

        # ── 15. Cancel ────────────────────────────────────────────────────────
        section("15. CANCEL")

        r = await c.post(f"/afmx/cancel/{exec_id}", content=b"{}")
        data = r.json()
        assert_eq("Cancel 200",         r.status_code, 200)
        # Already terminal — should return a terminal message
        assert_in("message",            "message", data)

        # ── 16. Observability endpoints ───────────────────────────────────────
        section("16. OBSERVABILITY")

        r = await c.get("/afmx/concurrency")
        data = r.json()
        assert_eq("Concurrency 200",    r.status_code, 200)
        assert_in("active",             "active", data)
        assert_in("utilization_pct",    "utilization_pct", data)
        info(f"Active: {data['active']}  Peak: {data.get('peak_active')}")

        r = await c.get("/afmx/plugins")
        data = r.json()
        assert_eq("Plugins 200",        r.status_code, 200)
        assert_in("tools",              "tools", data)
        assert_in("functions",          "functions", data)

        r = await c.get("/afmx/adapters")
        data = r.json()
        assert_eq("Adapters 200",       r.status_code, 200)
        assert_in("adapters",           "adapters", data)
        info(f"Adapters: {[a['name'] for a in data['adapters']]}")

        r = await c.get("/afmx/hooks")
        assert_eq("Hooks 200",          r.status_code, 200)

        # ── 17. Error cases ───────────────────────────────────────────────────
        section("17. ERROR CASES")

        r = await c.post("/afmx/execute", json={"matrix": {"nodes": []}, "input": {}})
        assert_eq("Empty nodes 422",    r.status_code, 422)

        r = await c.get("/afmx/status/completely-nonexistent-id-abc")
        assert_eq("Unknown exec 404",   r.status_code, 404)

        r = await c.get("/afmx/result/completely-nonexistent-id-def")
        assert_eq("Unknown result 404", r.status_code, 404)


# ─── Summary ──────────────────────────────────────────────────────────────────

    print(f"\n{C.BOLD}{'═' * 50}{C.RESET}")
    total = results["passed"] + results["failed"]
    if results["failed"] == 0:
        print(f"{C.GREEN}{C.BOLD}  ALL {total} TESTS PASSED ✓{C.RESET}")
    else:
        print(f"{C.RED}{C.BOLD}  {results['failed']} FAILED / {total} total{C.RESET}")
    print(f"{C.BOLD}{'═' * 50}{C.RESET}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AFMX real-time API test suite")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of the AFMX server")
    args = parser.parse_args()

    print(f"\n{C.BOLD}AFMX Real-Time Test Suite{C.RESET}")
    print(f"Server: {C.CYAN}{args.url}{C.RESET}")
    print(f"Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    asyncio.run(run_tests(args.url))


if __name__ == "__main__":
    main()
