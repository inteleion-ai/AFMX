#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# AFMX Real-Time API Test Suite
# Tests every endpoint against the live server at localhost:8100
# Usage: bash scripts/test_api.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

BASE="http://localhost:8100"
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

pass() { echo -e "${GREEN}  ✓ $1${RESET}"; }
fail() { echo -e "${RED}  ✗ $1${RESET}"; }
section() { echo -e "\n${BOLD}${CYAN}══ $1 ══${RESET}"; }
note() { echo -e "${YELLOW}  → $1${RESET}"; }

# ─── Helper ───────────────────────────────────────────────────────────────────

post() {
    local path="$1"
    local body="$2"
    curl -s -X POST "${BASE}${path}" \
        -H "Content-Type: application/json" \
        -d "$body"
}

get() {
    local path="$1"
    curl -s "${BASE}${path}"
}

pretty() {
    python3 -m json.tool 2>/dev/null || cat
}

# ═══════════════════════════════════════════════════════════════════════════════
section "1. HEALTH CHECK"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}GET /health${RESET}"
HEALTH=$(get "/health")
echo "$HEALTH" | pretty
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))")
[ "$STATUS" = "healthy" ] && pass "Server is healthy" || fail "Server not healthy"

echo -e "\n${BOLD}GET /${RESET}"
get "/" | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "2. VALIDATE — check matrix before execution"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}POST /afmx/validate — valid matrix${RESET}"
post "/afmx/validate" '{
  "matrix": {
    "name": "validate-test",
    "mode": "SEQUENTIAL",
    "nodes": [
      {"id": "n1", "name": "step1", "type": "FUNCTION", "handler": "echo"},
      {"id": "n2", "name": "step2", "type": "FUNCTION", "handler": "upper"}
    ],
    "edges": [{"from": "n1", "to": "n2"}]
  }
}' | pretty

echo -e "\n${BOLD}POST /afmx/validate — invalid (cycle)${RESET}"
post "/afmx/validate" '{
  "matrix": {
    "name": "cycle-test",
    "nodes": [
      {"id": "a", "name": "a", "type": "FUNCTION", "handler": "echo"},
      {"id": "b", "name": "b", "type": "FUNCTION", "handler": "echo"}
    ],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]
  }
}' | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "3. EXECUTE — synchronous executions"
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 3a. Single node ──────────────────────────────────────────────────────────
echo -e "\n${BOLD}Single echo node${RESET}"
RESULT=$(post "/afmx/execute" '{
  "matrix": {
    "name": "single-echo",
    "mode": "SEQUENTIAL",
    "nodes": [{"id": "n1", "name": "echo_node", "type": "FUNCTION", "handler": "echo"}],
    "edges": []
  },
  "input": {"query": "hello AFMX", "user": "raman"},
  "triggered_by": "realtime-test",
  "tags": ["test", "echo"]
}')
echo "$RESULT" | pretty
EXEC_STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
[ "$EXEC_STATUS" = "COMPLETED" ] && pass "Single node COMPLETED" || fail "Expected COMPLETED, got $EXEC_STATUS"

# Save execution_id for later
EXEC_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('execution_id',''))")
note "Execution ID: $EXEC_ID"

# ─── 3b. Sequential chain ─────────────────────────────────────────────────────
echo -e "\n${BOLD}3-node sequential chain: echo → upper → summarize${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "chain-flow",
    "mode": "SEQUENTIAL",
    "nodes": [
      {"id": "n1", "name": "echo_input",  "type": "FUNCTION", "handler": "echo"},
      {"id": "n2", "name": "uppercase",   "type": "FUNCTION", "handler": "upper"},
      {"id": "n3", "name": "summarizer",  "type": "FUNCTION", "handler": "summarize"}
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}]
  },
  "input": "Agent Flow Matrix Execution Engine — production grade deterministic execution for autonomous agents",
  "triggered_by": "realtime-test"
}' | pretty

# ─── 3c. Parallel execution ───────────────────────────────────────────────────
echo -e "\n${BOLD}Parallel fan-out: 3 nodes simultaneously${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "parallel-flow",
    "mode": "PARALLEL",
    "nodes": [
      {"id": "p1", "name": "analyst",   "type": "FUNCTION", "handler": "analyst_agent"},
      {"id": "p2", "name": "enricher",  "type": "FUNCTION", "handler": "enrich"},
      {"id": "p3", "name": "validator", "type": "FUNCTION", "handler": "validate",
       "config": {"params": {"required_fields": ["query"]}}}
    ],
    "edges": []
  },
  "input": {"query": "AI agent orchestration", "priority": "high"},
  "triggered_by": "realtime-test"
}' | pretty

# ─── 3d. Hybrid DAG ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}Hybrid DAG: analyst → [writer + reviewer] → concat${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "hybrid-pipeline",
    "mode": "HYBRID",
    "nodes": [
      {"id": "root",   "name": "analyst",   "type": "FUNCTION", "handler": "analyst_agent"},
      {"id": "left",   "name": "writer",    "type": "FUNCTION", "handler": "writer_agent"},
      {"id": "right",  "name": "reviewer",  "type": "FUNCTION", "handler": "reviewer_agent"},
      {"id": "final",  "name": "concat",    "type": "FUNCTION", "handler": "concat"}
    ],
    "edges": [
      {"from": "root",  "to": "left"},
      {"from": "root",  "to": "right"},
      {"from": "left",  "to": "final"},
      {"from": "right", "to": "final"}
    ]
  },
  "input": {"topic": "Agent execution engines in 2025"},
  "triggered_by": "realtime-test"
}' | pretty

# ─── 3e. Variable resolver ────────────────────────────────────────────────────
echo -e "\n${BOLD}Variable resolver: {{input.text}} in params${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "variable-flow",
    "mode": "SEQUENTIAL",
    "nodes": [
      {
        "id": "n1", "name": "multiplier", "type": "FUNCTION", "handler": "multiply",
        "config": {"params": {"factor": "{{variables.multiplier}}"}}
      }
    ],
    "edges": []
  },
  "input": 7,
  "variables": {"multiplier": 6},
  "triggered_by": "realtime-test"
}' | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "4. RETRY & FAULT TOLERANCE"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}Flaky node with 3 retries (fails twice, succeeds on 3rd)${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "retry-flow",
    "mode": "SEQUENTIAL",
    "nodes": [{
      "id": "n1", "name": "flaky_node", "type": "FUNCTION", "handler": "flaky",
      "retry_policy": {"retries": 3, "backoff_seconds": 0.1, "jitter": false}
    }],
    "edges": []
  },
  "input": "test retry",
  "triggered_by": "realtime-test"
}' | pretty

echo -e "\n${BOLD}CONTINUE policy — one node fails, others still run${RESET}"
post "/afmx/execute" '{
  "matrix": {
    "name": "continue-flow",
    "mode": "SEQUENTIAL",
    "abort_policy": "CONTINUE",
    "nodes": [
      {"id": "n1", "name": "success_1", "type": "FUNCTION", "handler": "echo"},
      {"id": "n2", "name": "fails",     "type": "FUNCTION", "handler": "always_fail"},
      {"id": "n3", "name": "success_2", "type": "FUNCTION", "handler": "upper"}
    ],
    "edges": []
  },
  "input": "resilience test",
  "triggered_by": "realtime-test"
}' | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "5. STATUS & RESULT"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}GET /afmx/status/$EXEC_ID${RESET}"
get "/afmx/status/${EXEC_ID}" | pretty

echo -e "\n${BOLD}GET /afmx/result/$EXEC_ID (full node outputs)${RESET}"
get "/afmx/result/${EXEC_ID}" | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "6. ASYNC EXECUTE + POLL"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}POST /afmx/execute/async — fire and forget${RESET}"
ASYNC_RESP=$(post "/afmx/execute/async" '{
  "matrix": {
    "name": "async-flow",
    "mode": "SEQUENTIAL",
    "nodes": [
      {"id": "n1", "name": "analyst", "type": "FUNCTION", "handler": "analyst_agent"},
      {"id": "n2", "name": "writer",  "type": "FUNCTION", "handler": "writer_agent"}
    ],
    "edges": [{"from": "n1", "to": "n2"}]
  },
  "input": {"task": "summarize AFMX architecture"},
  "triggered_by": "async-test"
}')
echo "$ASYNC_RESP" | pretty

ASYNC_ID=$(echo "$ASYNC_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('execution_id',''))")
note "Async execution ID: $ASYNC_ID"
note "Polling for completion..."

for i in 1 2 3 4 5; do
    sleep 0.5
    POLL=$(get "/afmx/status/${ASYNC_ID}")
    POLL_STATUS=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "UNKNOWN")
    echo "  Poll $i: $POLL_STATUS"
    if [[ "$POLL_STATUS" == "COMPLETED" || "$POLL_STATUS" == "FAILED" ]]; then
        break
    fi
done

echo -e "\n${BOLD}Final result:${RESET}"
get "/afmx/result/${ASYNC_ID}" | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "7. NAMED MATRICES (save → list → execute)"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}POST /afmx/matrices — save a named matrix${RESET}"
post "/afmx/matrices" '{
  "name": "research-pipeline",
  "version": "1.0.0",
  "description": "Analyst → Writer → Reviewer pipeline",
  "tags": ["research", "agents"],
  "definition": {
    "name": "research-pipeline",
    "mode": "SEQUENTIAL",
    "nodes": [
      {"id": "analyst",  "name": "analyst",  "type": "FUNCTION", "handler": "analyst_agent"},
      {"id": "writer",   "name": "writer",   "type": "FUNCTION", "handler": "writer_agent"},
      {"id": "reviewer", "name": "reviewer", "type": "FUNCTION", "handler": "reviewer_agent"}
    ],
    "edges": [{"from": "analyst", "to": "writer"}, {"from": "writer", "to": "reviewer"}]
  }
}' | pretty

echo -e "\n${BOLD}GET /afmx/matrices — list all saved matrices${RESET}"
get "/afmx/matrices" | pretty

echo -e "\n${BOLD}POST /afmx/matrices/research-pipeline/execute${RESET}"
post "/afmx/matrices/research-pipeline/execute" '{
  "input": {"topic": "autonomous agent execution frameworks"},
  "triggered_by": "named-matrix-test"
}' | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "8. LIST EXECUTIONS"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}GET /afmx/executions?limit=5${RESET}"
get "/afmx/executions?limit=5" | pretty

echo -e "\n${BOLD}GET /afmx/executions?status_filter=COMPLETED${RESET}"
get "/afmx/executions?status_filter=COMPLETED&limit=3" | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "9. CONCURRENCY & OBSERVABILITY"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}GET /afmx/concurrency${RESET}"
get "/afmx/concurrency" | pretty

echo -e "\n${BOLD}GET /afmx/plugins${RESET}"
get "/afmx/plugins" | pretty

echo -e "\n${BOLD}GET /afmx/hooks${RESET}"
get "/afmx/hooks" | pretty

echo -e "\n${BOLD}GET /afmx/adapters${RESET}"
get "/afmx/adapters" | pretty

# ═══════════════════════════════════════════════════════════════════════════════
section "10. CANCEL"
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "\n${BOLD}POST /afmx/cancel/$EXEC_ID (already completed — expected terminal msg)${RESET}"
post "/afmx/cancel/${EXEC_ID}" '{}' | pretty

# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}${GREEN}═══════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  All curl tests complete!${RESET}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════${RESET}\n"
echo "  Run WebSocket streaming test:"
echo "    python3.10 scripts/test_ws.py"
echo ""
echo "  Run full Python test suite:"
echo "    python3.10 scripts/test_realtime.py"
echo ""
echo "  OpenAPI docs:"
echo "    http://localhost:8100/docs"
