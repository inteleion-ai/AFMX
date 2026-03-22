"""
AFMX + Agentability — Full Observability Demo
==============================================
Shows the complete data flow:
  AFMX executes matrices → hooks fire → Agentability records decisions
  → dashboard shows confidence, latency, costs, conflicts

Prerequisites:
    pip install agentability httpx

Run:
    # 1. Start AFMX (in one terminal)
    python3.10 -m afmx serve --reload

    # 2. Enable Agentability in .env  ← ONLY CHANGE NEEDED
    #    AFMX_AGENTABILITY_ENABLED=true
    #    AFMX_AGENTABILITY_DB_PATH=agentability.db

    # 3. Restart AFMX so it picks up the new env

    # 4. Start Agentability platform (in a second terminal)
    cd new_project/agentability/Agentability
    AGENTABILITY_DB=../../agentability.db uvicorn platform.api.main:app --port 8000

    # 5. Start Agentability dashboard (in a third terminal)
    cd new_project/agentability/Agentability/dashboard
    npm run dev    # http://localhost:3000

    # 6. Run this demo (in a fourth terminal)
    python demo_agentability.py

Then open BOTH dashboards side-by-side:
  AFMX:         http://localhost:5173   (or 8100/afmx/ui)
  Agentability: http://localhost:3000
"""
from __future__ import annotations

import asyncio
import time
import httpx

AFMX_URL = "http://localhost:8100"
AGNT_URL = "http://localhost:8000"

BOLD  = "\033[1m";  RESET = "\033[0m"
GREEN = "\033[92m"; RED   = "\033[91m"
CYAN  = "\033[96m"; DIM   = "\033[2m"

def ok(s):  print(f"  {GREEN}✓{RESET}  {s}")
def err(s): print(f"  {RED}✕{RESET}  {s}")
def inf(s): print(f"  {DIM}{s}{RESET}")
def hdr(s): print(f"\n{BOLD}{CYAN}── {s} ──{RESET}")


async def run_matrix(client: httpx.AsyncClient, matrix: dict, inp: dict, tags: list[str]) -> dict:
    r = await client.post("/afmx/execute",
        json={"matrix": matrix, "input": inp, "triggered_by": "agentability-demo", "tags": tags},
        timeout=30.0)
    r.raise_for_status()
    return r.json()


async def check_agentability(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(AGNT_URL + "/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


async def main() -> None:
    print(f"\n{BOLD}  AFMX + Agentability Integration Demo{RESET}")
    print(  f"  {'─'*42}")

    async with httpx.AsyncClient(base_url=AFMX_URL) as client:

        # ── Check AFMX ────────────────────────────────────────────────────────
        hdr("Checking connections")
        try:
            h = (await client.get("/health", timeout=4.0)).json()
            ok(f"AFMX v{h['version']}  |  agentability.connected = "
               f"{h.get('agentability', {}).get('connected', False)}")
            if not h.get("agentability", {}).get("connected"):
                err("Agentability hook NOT connected to AFMX.")
                err("Set AFMX_AGENTABILITY_ENABLED=true in .env and restart AFMX.")
                return
        except Exception as e:
            err(f"AFMX unreachable: {e}"); return

        # ── Check Agentability platform ───────────────────────────────────────
        agnt_alive = await check_agentability(client)
        if agnt_alive:
            ok(f"Agentability platform running at {AGNT_URL}")
        else:
            inf("Agentability platform not running — decisions will be written to SQLite only")
            inf(f"  Start: AGENTABILITY_DB=agentability.db uvicorn platform.api.main:app --port 8000")

        # ── Scenario A: Analyst → Writer → Reviewer ───────────────────────────
        hdr("Scenario A — 3-Agent Research Chain")
        inf("Each agent call becomes a Decision in Agentability with:")
        inf("  - confidence score (analyst=0.87, reviewer=0.92)")
        inf("  - latency_ms (measured by the hook)")
        inf("  - reasoning chain from node metadata")

        result_a = await run_matrix(client,
            matrix={
                "name": "agentability-research", "mode": "SEQUENTIAL",
                "nodes": [
                    {"id": "n1", "name": "analyst",  "type": "AGENT", "handler": "analyst_agent"},
                    {"id": "n2", "name": "writer",   "type": "AGENT", "handler": "writer_agent"},
                    {"id": "n3", "name": "reviewer", "type": "AGENT", "handler": "reviewer_agent"},
                ],
                "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
            },
            inp={"topic": "Production multi-agent systems architecture 2026"},
            tags=["agentability-demo", "research"],
        )
        ok(f"Execution: {result_a['status']}  |  {result_a.get('completed_nodes')}/{result_a.get('total_nodes')} nodes")
        inf(f"  execution_id = {result_a['execution_id']}")
        inf(f"  → In Agentability dashboard, filter Decisions by session_id = {result_a['execution_id'][:16]}…")

        await asyncio.sleep(0.5)

        # ── Scenario B: 5 concurrent research tasks ───────────────────────────
        hdr("Scenario B — 5 Concurrent Research Tasks")
        inf("Fires 5 pipelines at once → Agentability captures all 15 decisions")
        inf("Watch confidence drift and latency trends in Agentability → Agents tab")

        topics = [
            "GPT-5 architecture and enterprise deployment considerations",
            "Cost optimization strategies for production LLM systems",
            "AFMX vs LangGraph vs CrewAI: which to choose in 2026",
            "Multi-modal agent systems for document understanding",
            "Regulatory compliance for AI agents in financial services",
        ]

        matrix = {
            "name": "agentability-burst", "mode": "SEQUENTIAL",
            "nodes": [
                {"id": "n1", "name": "analyst",  "type": "AGENT", "handler": "analyst_agent"},
                {"id": "n2", "name": "writer",   "type": "AGENT", "handler": "writer_agent"},
                {"id": "n3", "name": "reviewer", "type": "AGENT", "handler": "reviewer_agent"},
            ],
            "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
        }

        tasks = [
            run_matrix(client, matrix, {"topic": t}, ["agentability-demo", "burst"])
            for t in topics
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        completed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "COMPLETED")
        ok(f"{completed}/5 pipelines completed  →  ~{completed * 3} decisions recorded in Agentability")

        await asyncio.sleep(0.5)

        # ── Scenario C: Conflict detection ────────────────────────────────────
        hdr("Scenario C — Conflict Detection (Parallel Disagreeing Reviewers)")
        inf("Two reviewers run in parallel on the same proposal — one approves, one flags risk")
        inf("Agentability's conflict detector should log a GOAL_CONFLICT")

        conflict_matrix = {
            "name": "conflict-detection", "mode": "PARALLEL",
            "nodes": [
                {"id": "analyst",      "name": "analyst",        "type": "AGENT", "handler": "analyst_agent"},
                {"id": "approver",     "name": "risk_approver",  "type": "AGENT", "handler": "reviewer_agent"},
                {"id": "challenger",   "name": "risk_challenger","type": "AGENT", "handler": "analyst_agent"},
                {"id": "arbitrator",   "name": "arbitrator",     "type": "AGENT", "handler": "reviewer_agent"},
                {"id": "final-writer", "name": "report_writer",  "type": "AGENT", "handler": "writer_agent"},
            ],
            "edges": [
                {"from": "analyst",    "to": "approver"},
                {"from": "analyst",    "to": "challenger"},
                {"from": "approver",   "to": "arbitrator"},
                {"from": "challenger", "to": "arbitrator"},
                {"from": "arbitrator", "to": "final-writer"},
            ],
        }

        result_c = await run_matrix(client, conflict_matrix,
            {"proposal": "Autonomous agent to execute stock trades without human oversight",
             "risk":     "HIGH", "budget": 500_000},
            ["agentability-demo", "conflict", "parallel-review"],
        )
        ok(f"Conflict scenario: {result_c['status']}  |  "
           f"{result_c.get('completed_nodes')}/{result_c.get('total_nodes')} nodes")
        inf("  → Check Agentability → Conflicts page for detected GOAL_CONFLICT")

        await asyncio.sleep(0.5)

        # ── Scenario D: Retry → confidence drift ──────────────────────────────
        hdr("Scenario D — Retry Chain (confidence drift per attempt)")
        inf("flaky node retries 3× — Agentability shows LLM calls with retry_1, retry_2")

        retry_matrix = {
            "name": "agentability-retry", "mode": "SEQUENTIAL",
            "nodes": [
                {
                    "id": "flaky", "name": "flaky_service", "type": "TOOL", "handler": "flaky",
                    "retry_policy": {"retries": 3, "backoff_seconds": 0.1},
                },
                {"id": "writer", "name": "report_writer", "type": "AGENT", "handler": "writer_agent"},
            ],
            "edges": [{"from": "flaky", "to": "writer"}],
        }

        result_d = await run_matrix(client, retry_matrix,
            {"task": "fetch reliability metrics from unstable microservice"},
            ["agentability-demo", "retry", "fault-tolerance"],
        )
        ok(f"Retry scenario: {result_d['status']}  |  "
           f"attempts={result_d.get('node_results', {}).get('flaky', {}).get('attempt', '?')}")
        inf("  → Check Agentability → Cost & LLM: retry events appear as separate llm_calls")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{GREEN}  All scenarios complete!{RESET}")
    print()
    print(f"  {'What to look at':<32} {'Where'}")
    print(f"  {'─'*32} {'─'*42}")
    rows = [
        ("All executions",         "AFMX dashboard → Executions"),
        ("Node trace + waterfall",  "Click any row → Trace / Waterfall tabs"),
        ("Live stream",             "AFMX → Live Stream (run demo again to watch)"),
        ("Decision provenance",     "Agentability → Decisions  (session_id filter)"),
        ("Agent confidence drift",  "Agentability → Agents  (select analyst_agent)"),
        ("Conflict log",            "Agentability → Conflicts"),
        ("Token cost breakdown",    "Agentability → Cost & LLM"),
    ]
    for label, where in rows:
        print(f"  {label:<32} {CYAN}{where}{RESET}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
