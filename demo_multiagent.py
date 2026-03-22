"""
AFMX Live Demo — Multi-Agent Scenarios
========================================
Fires real matrix executions against the running AFMX server on :8100.
Watch every result appear live in the dashboard at http://localhost:5173

Run:
    python demo_multiagent.py                        # uses http://localhost:8100
    python demo_multiagent.py --url http://host:8100 # remote server
    python demo_multiagent.py --scenario all         # run everything
    python demo_multiagent.py --scenario research    # one scenario only
    python demo_multiagent.py --live                 # stream events via WebSocket

Scenarios (all use handlers already registered in startup_handlers.py):
  1. research_pipeline      — Analyst → Writer → Reviewer (3-agent chain)
  2. parallel_analysis      — Two analysts in parallel → merge → review
  3. conditional_routing    — Route → NLP specialist OR data specialist → writer
  4. retry_and_recovery     — Flaky node retries 3× then fallback kicks in
  5. document_pipeline      — Validate → Enrich → Summarize → Echo (4-stage tool chain)
  6. swarm_review           — 3 specialist agents all review in parallel → aggregator
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx

BASE_URL = "http://localhost:8100"
HEADERS  = {"Content-Type": "application/json"}


# ─── Pretty-print helpers ─────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
PURPLE = "\033[95m"
DIM    = "\033[2m"

def h1(s: str)  -> None: print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}\n  {BOLD}{s}{RESET}\n{'═'*60}")
def h2(s: str)  -> None: print(f"\n{BOLD}  ── {s} ──{RESET}")
def ok(s: str)  -> None: print(f"  {GREEN}✓{RESET}  {s}")
def err(s: str) -> None: print(f"  {RED}✕{RESET}  {s}")
def inf(s: str) -> None: print(f"  {DIM}{s}{RESET}")
def hi(s: str)  -> None: print(f"  {YELLOW}→{RESET}  {s}")


def status_colour(s: str) -> str:
    c = {"COMPLETED": GREEN, "FAILED": RED, "PARTIAL": YELLOW,
         "RUNNING": CYAN, "TIMEOUT": YELLOW}.get(s, DIM)
    return f"{c}{BOLD}{s}{RESET}"


def print_result(result: dict) -> None:
    status = result.get("status", "?")
    dur    = result.get("duration_ms")
    dur_s  = f"{dur:.0f}ms" if dur is not None else "—"
    eid    = result.get("execution_id", "?")[:16]
    c_ok   = result.get("completed_nodes", 0)
    c_fail = result.get("failed_nodes", 0)
    c_skip = result.get("skipped_nodes", 0)

    print(f"\n  Status   : {status_colour(status)}")
    print(f"  ID       : {CYAN}{eid}…{RESET}")
    print(f"  Duration : {dur_s}")
    print(f"  Nodes    : {GREEN}{c_ok} ok{RESET}  {RED}{c_fail} fail{RESET}  {DIM}{c_skip} skip{RESET}")

    if result.get("error"):
        print(f"  {RED}Error    : {result['error']}{RESET}")

    node_results: dict = result.get("node_results", {})
    if node_results:
        print(f"\n  {'Node':<22} {'Status':<12} {'Duration':<10} Output (summary)")
        print(f"  {'─'*22} {'─'*12} {'─'*10} {'─'*30}")
        for nr in node_results.values():
            nstatus  = nr.get("status", "?")
            ndur     = nr.get("duration_ms")
            ndur_s   = f"{ndur:.0f}ms" if ndur is not None else "—"
            nout     = nr.get("output") or {}
            attempt  = nr.get("attempt", 1)
            attempts = f" ×{attempt}" if attempt > 1 else ""
            # Show most meaningful output key
            summary  = _summarize_output(nout)
            nc       = GREEN if nstatus in ("SUCCESS",) else (
                       RED   if nstatus in ("FAILED", "ABORTED") else
                       YELLOW if nstatus in ("FALLBACK", "TIMEOUT") else DIM)
            print(f"  {nr.get('node_name','?'):<22} {nc}{nstatus:<12}{RESET}{attempts:<4} {DIM}{ndur_s:<10}{RESET} {summary}")
    print()


def _summarize_output(out: Any) -> str:
    if not isinstance(out, dict):
        return str(out)[:50] if out is not None else "—"
    # Pick most meaningful key
    for key in ("report", "content", "analysis", "summary", "result",
                "echo", "approved", "recovered", "fallback"):
        if key in out:
            return f"{key}={str(out[key])[:40]}"
    return str(out)[:50]


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

async def post_execute(client: httpx.AsyncClient, payload: dict) -> dict:
    r = await client.post("/afmx/execute", json=payload, timeout=60.0)
    r.raise_for_status()
    return r.json()


async def post_validate(client: httpx.AsyncClient, matrix: dict) -> dict:
    r = await client.post("/afmx/validate", json={"matrix": matrix}, timeout=10.0)
    r.raise_for_status()
    return r.json()


async def get_health(client: httpx.AsyncClient) -> dict:
    r = await client.get("/health", timeout=5.0)
    r.raise_for_status()
    return r.json()


# ─── Scenario 1: Research Pipeline (3-agent chain) ────────────────────────────

async def scenario_research_pipeline(client: httpx.AsyncClient) -> None:
    h1("Scenario 1 — Research Pipeline (3-Agent Chain)")
    inf("analyst_agent → writer_agent → reviewer_agent")
    inf("Each agent receives upstream output via node_outputs")

    matrix = {
        "name": "research-pipeline",
        "mode": "SEQUENTIAL",
        "nodes": [
            {"id": "n1", "name": "analyst",  "type": "AGENT",    "handler": "analyst_agent"},
            {"id": "n2", "name": "writer",   "type": "AGENT",    "handler": "writer_agent"},
            {"id": "n3", "name": "reviewer", "type": "AGENT",    "handler": "reviewer_agent"},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
        ],
    }

    for topic in [
        "The impact of multi-agent AI systems on enterprise automation in 2026",
        "Comparing AFMX, LangGraph, and CrewAI for production agent orchestration",
    ]:
        h2(f"Topic: {topic[:55]}…" if len(topic) > 55 else f"Topic: {topic}")
        try:
            result = await post_execute(client, {
                "matrix":       matrix,
                "input":        {"query": topic, "depth": "deep"},
                "triggered_by": "demo:research_pipeline",
                "tags":         ["demo", "research", "multi-agent"],
            })
            print_result(result)
        except Exception as e:
            err(str(e))


# ─── Scenario 2: Parallel Analysis (fan-out → merge) ──────────────────────────

async def scenario_parallel_analysis(client: httpx.AsyncClient) -> None:
    h1("Scenario 2 — Parallel Analysis Fan-out")
    inf("analyst_a and analyst_b run in PARALLEL, then concat merges, reviewer signs off")
    inf("Tests: parallel execution, node_outputs aggregation")

    matrix = {
        "name": "parallel-analysis",
        "mode": "PARALLEL",
        "nodes": [
            {"id": "analyst-a", "name": "analyst_sentiment", "type": "AGENT",  "handler": "analyst_agent"},
            {"id": "analyst-b", "name": "analyst_entities",  "type": "AGENT",  "handler": "analyst_agent"},
            {"id": "merge",     "name": "merge_results",     "type": "TOOL",   "handler": "concat"},
            {"id": "review",    "name": "reviewer",          "type": "AGENT",  "handler": "reviewer_agent"},
        ],
        "edges": [
            {"from": "analyst-a", "to": "merge"},
            {"from": "analyst-b", "to": "merge"},
            {"from": "merge",     "to": "review"},
        ],
    }

    result = await post_execute(client, {
        "matrix":       matrix,
        "input":        {"document": "AFMX enables deterministic multi-agent execution at scale."},
        "triggered_by": "demo:parallel_analysis",
        "tags":         ["demo", "parallel", "fan-out"],
    })
    print_result(result)


# ─── Scenario 3: Conditional Routing (dynamic path selection) ─────────────────

async def scenario_conditional_routing(client: httpx.AsyncClient) -> None:
    h1("Scenario 3 — Conditional Routing")
    inf("route node classifies input → 'urgent' path OR 'normal' path")
    inf("Tests: EdgeCondition, dynamic graph path selection")

    matrix = {
        "name": "conditional-routing",
        "mode": "SEQUENTIAL",
        "nodes": [
            {"id": "router",   "name": "classifier",      "type": "TOOL",  "handler": "route"},
            {"id": "fast",     "name": "urgent_handler",  "type": "AGENT", "handler": "analyst_agent",
             "metadata": {"path": "urgent"}},
            {"id": "normal",   "name": "standard_handler","type": "AGENT", "handler": "writer_agent",
             "metadata": {"path": "normal"}},
            {"id": "writer",   "name": "final_writer",    "type": "AGENT", "handler": "writer_agent"},
        ],
        "edges": [
            {"from": "router", "to": "fast",   "condition": {"type": "EXPRESSION", "expression": "output['category'] == 'urgent'"}},
            {"from": "router", "to": "normal", "condition": {"type": "EXPRESSION", "expression": "output['category'] != 'urgent'"}},
            {"from": "fast",   "to": "writer"},
            {"from": "normal", "to": "writer"},
        ],
    }

    for case in [
        ("URGENT: production system down, critical failure detected",   "should route → urgent_handler"),
        ("Summarize quarterly AI adoption trends for the board report", "should route → standard_handler"),
    ]:
        h2(f"Case: {case[1]}")
        inf(f"  Input: \"{case[0][:60]}…\"" if len(case[0]) > 60 else f"  Input: \"{case[0]}\"")
        try:
            result = await post_execute(client, {
                "matrix":       matrix,
                "input":        case[0],
                "triggered_by": "demo:conditional_routing",
                "tags":         ["demo", "routing", "conditional"],
            })
            print_result(result)
        except Exception as e:
            err(str(e))


# ─── Scenario 4: Retry + Fallback ─────────────────────────────────────────────

async def scenario_retry_fallback(client: httpx.AsyncClient) -> None:
    h1("Scenario 4 — Retry Logic + Fallback Recovery")
    inf("flaky node fails on attempts 1 & 2, succeeds on attempt 3")
    inf("Tests: RetryPolicy, exponential backoff, recovery")

    matrix_retry = {
        "name": "retry-test",
        "mode": "SEQUENTIAL",
        "nodes": [
            {
                "id": "flaky", "name": "flaky_service", "type": "TOOL", "handler": "flaky",
                "retry_policy": {"retries": 3, "backoff_seconds": 0.1, "backoff_multiplier": 2.0},
            },
            {"id": "writer", "name": "report_writer", "type": "AGENT", "handler": "writer_agent"},
        ],
        "edges": [{"from": "flaky", "to": "writer"}],
    }

    h2("Test A — Flaky service recovers after 2 failures")
    inf("  Watch attempt count in the dashboard node trace")
    result = await post_execute(client, {
        "matrix":       matrix_retry,
        "input":        {"task": "fetch external data"},
        "triggered_by": "demo:retry_fallback",
        "tags":         ["demo", "retry", "fault-tolerance"],
    })
    print_result(result)

    h2("Test B — Always-fail with fallback node")
    matrix_fallback = {
        "name": "fallback-test",
        "mode": "SEQUENTIAL",
        "nodes": [
            {
                "id": "primary",  "name": "primary_service", "type": "TOOL",
                "handler": "always_fail",
                "fallback_node_id": "fallback",
                "retry_policy": {"retries": 1, "backoff_seconds": 0.05},
            },
            {"id": "fallback", "name": "fallback_handler", "type": "TOOL", "handler": "fallback_recovery"},
            {"id": "writer",   "name": "report_writer",    "type": "AGENT","handler": "writer_agent"},
        ],
        "edges": [
            {"from": "primary",  "to": "writer"},
            {"from": "fallback", "to": "writer"},
        ],
    }

    inf("  Primary fails → fallback_handler runs → writer completes")
    result = await post_execute(client, {
        "matrix":       matrix_fallback,
        "input":        {"task": "call unreliable external API"},
        "triggered_by": "demo:retry_fallback",
        "tags":         ["demo", "fallback", "fault-tolerance"],
    })
    print_result(result)


# ─── Scenario 5: Document Processing Pipeline ─────────────────────────────────

async def scenario_document_pipeline(client: httpx.AsyncClient) -> None:
    h1("Scenario 5 — Document Processing Pipeline (4-stage Tool Chain)")
    inf("validate → enrich → summarize → echo")
    inf("Tests: sequential tool chaining, parameter passing, data enrichment")

    matrix = {
        "name": "document-pipeline",
        "mode": "SEQUENTIAL",
        "nodes": [
            {
                "id": "validate", "name": "input_validator", "type": "TOOL",
                "handler": "validate",
                "config": {"params": {"required_fields": ["content", "author"]}},
            },
            {
                "id": "enrich",   "name": "metadata_enricher", "type": "TOOL",
                "handler": "enrich",
                "config": {"params": {"tags": ["processed", "demo"], "source": "afmx-demo"}},
            },
            {"id": "summarize", "name": "ai_summarizer",    "type": "TOOL", "handler": "summarize"},
            {"id": "echo",      "name": "output_formatter", "type": "TOOL", "handler": "echo"},
        ],
        "edges": [
            {"from": "validate",  "to": "enrich"},
            {"from": "enrich",    "to": "summarize"},
            {"from": "summarize", "to": "echo"},
        ],
    }

    for doc in [
        {
            "content": "AFMX is a deterministic multi-agent execution engine built for production. "
                       "It supports retry policies, circuit breakers, conditional routing, "
                       "parallel fan-out, and full audit trails with sub-millisecond hooks.",
            "author":  "Agentdyne9",
            "doc_id":  "DOC-001",
        },
        {
            "content": "This is a second test document that validates the pipeline handles "
                       "multiple concurrent documents correctly with proper enrichment.",
            "author":  "Demo User",
            "doc_id":  "DOC-002",
        },
    ]:
        h2(f"Processing: {doc['doc_id']}")
        result = await post_execute(client, {
            "matrix":       matrix,
            "input":        doc,
            "triggered_by": "demo:document_pipeline",
            "tags":         ["demo", "document", "pipeline"],
        })
        print_result(result)


# ─── Scenario 6: Swarm Review (3 parallel reviewers → aggregator) ─────────────

async def scenario_swarm_review(client: httpx.AsyncClient) -> None:
    h1("Scenario 6 — Agent Swarm Review")
    inf("3 specialist reviewers run in parallel → analyst aggregates → writer produces final report")
    inf("This is the most realistic multi-agent pattern for real production systems")
    inf("Tests: parallel agents, aggregation, upstream output fan-in")

    matrix = {
        "name": "swarm-review",
        "mode": "PARALLEL",
        "nodes": [
            # Input routing
            {"id": "validate",     "name": "input_validator",    "type": "TOOL",  "handler": "validate",
             "config": {"params": {"required_fields": ["proposal"]}}},
            # 3 specialist reviewers — all run in parallel
            {"id": "tech-review",  "name": "technical_reviewer", "type": "AGENT", "handler": "reviewer_agent"},
            {"id": "biz-review",   "name": "business_reviewer",  "type": "AGENT", "handler": "analyst_agent"},
            {"id": "sec-review",   "name": "security_reviewer",  "type": "AGENT", "handler": "reviewer_agent"},
            # Aggregator receives all 3 reviewer outputs
            {"id": "aggregator",   "name": "decision_aggregator","type": "AGENT", "handler": "analyst_agent"},
            # Final report writer
            {"id": "final-writer", "name": "report_writer",      "type": "AGENT", "handler": "writer_agent"},
        ],
        "edges": [
            # Validate → all 3 reviewers in parallel
            {"from": "validate",    "to": "tech-review"},
            {"from": "validate",    "to": "biz-review"},
            {"from": "validate",    "to": "sec-review"},
            # All 3 reviewers → aggregator
            {"from": "tech-review", "to": "aggregator"},
            {"from": "biz-review",  "to": "aggregator"},
            {"from": "sec-review",  "to": "aggregator"},
            # Aggregator → final writer
            {"from": "aggregator",  "to": "final-writer"},
        ],
    }

    proposals = [
        {
            "proposal":    "Deploy GPT-4o as the primary reasoning engine for all customer-facing chatbots",
            "budget_usd":  120_000,
            "timeline":    "Q2 2026",
            "risk_level":  "medium",
        },
        {
            "proposal":    "Migrate the entire data pipeline to a multi-agent AFMX workflow",
            "budget_usd":  250_000,
            "timeline":    "Q3 2026",
            "risk_level":  "high",
        },
    ]

    for i, proposal in enumerate(proposals, 1):
        h2(f"Proposal {i}: {proposal['proposal'][:55]}…")
        inf(f"  Budget: ${proposal['budget_usd']:,}  |  Timeline: {proposal['timeline']}  |  Risk: {proposal['risk_level']}")
        try:
            result = await post_execute(client, {
                "matrix":       matrix,
                "input":        proposal,
                "triggered_by": "demo:swarm_review",
                "tags":         ["demo", "swarm", "review", "parallel"],
                "variables":    {"review_depth": "thorough", "require_consensus": True},
            })
            print_result(result)
        except Exception as e:
            err(str(e))


# ─── Scenario 7: High-volume burst (stress test) ──────────────────────────────

async def scenario_burst(client: httpx.AsyncClient, count: int = 20) -> None:
    h1(f"Scenario 7 — Burst ({count} concurrent executions)")
    inf("Fires all executions simultaneously — tests concurrency manager + dashboard live metrics")

    matrix = {
        "name": "burst-test",
        "mode": "SEQUENTIAL",
        "nodes": [
            {"id": "n1", "name": "enrich",   "type": "TOOL", "handler": "enrich"},
            {"id": "n2", "name": "upper",    "type": "TOOL", "handler": "upper"},
            {"id": "n3", "name": "summarize","type": "TOOL", "handler": "summarize"},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }

    start = time.perf_counter()
    tasks = [
        post_execute(client, {
            "matrix":       matrix,
            "input":        f"Burst job #{i:03d} — testing AFMX concurrency at scale",
            "triggered_by": "demo:burst",
            "tags":         ["demo", "burst", f"job-{i}"],
        })
        for i in range(count)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = (time.perf_counter() - start) * 1000

    completed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "COMPLETED")
    failed    = sum(1 for r in results if isinstance(r, Exception))

    ok(f"Fired {count} executions in {elapsed:.0f}ms")
    ok(f"Completed: {completed}  |  Errored: {failed}")
    inf(f"Throughput: {count / (elapsed / 1000):.1f} executions/sec")


# ─── Main runner ──────────────────────────────────────────────────────────────

ALL_SCENARIOS = {
    "research":   scenario_research_pipeline,
    "parallel":   scenario_parallel_analysis,
    "routing":    scenario_conditional_routing,
    "retry":      scenario_retry_fallback,
    "document":   scenario_document_pipeline,
    "swarm":      scenario_swarm_review,
    "burst":      scenario_burst,
}


async def main(url: str, scenario: str) -> None:
    print(f"\n{BOLD}{PURPLE}")
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   AFMX Multi-Agent Live Demo                ║")
    print("  ║   Dashboard: http://localhost:5173          ║")
    print("  ╚══════════════════════════════════════════════╝")
    print(RESET)

    async with httpx.AsyncClient(base_url=url, headers=HEADERS) as client:

        # ── Health check ──────────────────────────────────────────────────────
        h2("Checking AFMX server")
        try:
            health = await get_health(client)
            ok(f"Server: {health.get('status')}  |  v{health.get('version')}  |  "
               f"store={health.get('store_backend')}  |  "
               f"uptime={health.get('uptime_seconds', 0):.0f}s")
        except Exception as e:
            err(f"Cannot reach AFMX at {url} — is the server running?")
            err(f"  Start with: python3.10 -m afmx serve --reload")
            err(f"  Detail: {e}")
            sys.exit(1)

        print()
        inf("All executions will appear in the dashboard in real-time.")
        inf("Open: http://localhost:5173  →  Executions page")
        inf("      http://localhost:5173/stream  →  Live Stream")
        print()

        if scenario == "all":
            for name, fn in ALL_SCENARIOS.items():
                await fn(client)
                await asyncio.sleep(0.3)   # small gap between scenarios
        elif scenario in ALL_SCENARIOS:
            await ALL_SCENARIOS[scenario](client)
        else:
            err(f"Unknown scenario '{scenario}'. Choose: {', '.join(ALL_SCENARIOS)} or 'all'")
            sys.exit(1)

    print(f"\n{GREEN}{BOLD}  Done! Open the dashboard to explore results:{RESET}")
    print(f"  {CYAN}http://localhost:5173{RESET}  — Executions, Overview, Live Stream")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AFMX Multi-Agent Live Demo")
    parser.add_argument("--url",      default="http://localhost:8100",
                        help="AFMX server URL (default: http://localhost:8100)")
    parser.add_argument("--scenario", default="all",
                        choices=[*ALL_SCENARIOS.keys(), "all"],
                        help="Which scenario to run (default: all)")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.scenario))
