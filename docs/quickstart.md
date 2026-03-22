# Quick Start

Get from zero to a running AFMX server with your first multi-agent execution in under 5 minutes.

---

## Prerequisites

- Python 3.10 or higher
- Oracle Cloud Linux / Ubuntu 22.04 / macOS 13+

```bash
python3.10 --version   # must be 3.10.x or higher
```

---

## Step 1 — Install

```bash
cd AFMX   # project root

# Create virtual environment
python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

---

## Step 2 — Configure

```bash
cp .env.example .env
# Defaults work out of the box for local development.
# Key setting: AFMX_STORE_BACKEND=memory (no Redis needed for dev)
```

---

## Step 3 — Start the Server

```bash
python3.10 -m afmx serve --reload
```

Expected output:
```
INFO  | [AFMX] Store backend: InMemory
INFO  | [AFMX] Startup handlers loaded
INFO  | [AFMX] Realistic agents loaded — rich dashboard data enabled
INFO  | [AFMX] ✅ Engine online — AFMX v1.0.0 | env=development | store=memory
INFO  | uvicorn | Application startup complete.
```

Endpoints:
| URL | What |
|---|---|
| `http://localhost:8100` | Root (service info) |
| `http://localhost:8100/docs` | Swagger UI (interactive) |
| `http://localhost:8100/health` | Health + concurrency stats |
| `http://localhost:8100/afmx/ui` | React dashboard (after `npm run build`) |

---

## Step 4 — Your First Execution

### Option A — curl

```bash
curl -s -X POST http://localhost:8100/afmx/execute \
  -H "Content-Type: application/json" \
  -d '{
    "matrix": {
      "name": "hello-world",
      "mode": "SEQUENTIAL",
      "nodes": [{"id":"n1","name":"echo","type":"FUNCTION","handler":"echo"}],
      "edges": []
    },
    "input": {"query": "hello AFMX"},
    "triggered_by": "quickstart"
  }' | python3 -m json.tool
```

Expected response:
```json
{
  "execution_id": "550e8400-...",
  "matrix_name": "hello-world",
  "status": "COMPLETED",
  "completed_nodes": 1,
  "failed_nodes": 0,
  "duration_ms": 0.8,
  "node_results": {
    "n1": {
      "node_name": "echo",
      "status": "SUCCESS",
      "output": {"echo": {"query": "hello AFMX"}, "node": "echo"},
      "attempt": 1,
      "duration_ms": 0.3,
      "started_at": 1710000000.001,
      "finished_at": 1710000000.002
    }
  }
}
```

### Option B — Python

```python
import httpx, asyncio

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
        r = await client.post("/afmx/execute", json={
            "matrix": {
                "name": "hello-world",
                "mode": "SEQUENTIAL",
                "nodes": [{"id":"n1","name":"echo","type":"FUNCTION","handler":"echo"}],
                "edges": [],
            },
            "input": {"query": "hello AFMX"},
        })
        print(r.json())

asyncio.run(main())
```

---

## Step 5 — Multi-Agent Research Pipeline

Three agents in sequence. Each agent receives the previous agent's output via `node_outputs`.

```bash
curl -s -X POST http://localhost:8100/afmx/execute \
  -H "Content-Type: application/json" \
  -d '{
    "matrix": {
      "name": "research-pipeline",
      "mode": "SEQUENTIAL",
      "nodes": [
        {"id":"analyst",  "name":"analyst",  "type":"AGENT","handler":"analyst_agent"},
        {"id":"writer",   "name":"writer",   "type":"AGENT","handler":"writer_agent"},
        {"id":"reviewer", "name":"reviewer", "type":"AGENT","handler":"reviewer_agent"}
      ],
      "edges": [
        {"from":"analyst","to":"writer"},
        {"from":"writer","to":"reviewer"}
      ]
    },
    "input": {"topic": "Production multi-agent systems in 2026"},
    "triggered_by": "quickstart"
  }' | python3 -m json.tool
```

---

## Step 6 — Build the React Dashboard

```bash
cd afmx/dashboard
npm install
npm run build       # outputs to afmx/static/ — FastAPI serves it at /afmx/ui

# OR for hot-reload development:
npm run dev         # http://localhost:5173  (proxies API to :8100)
```

---

## Step 7 — Run the Full Live Demo

Fires 7 multi-agent scenarios against the running server:

```bash
pip install httpx   # if not already installed
python demo_multiagent.py --scenario all

# Individual scenarios:
python demo_multiagent.py --scenario research    # 3-agent chain
python demo_multiagent.py --scenario parallel    # fan-out → merge
python demo_multiagent.py --scenario routing     # conditional branching
python demo_multiagent.py --scenario retry       # retry + fallback
python demo_multiagent.py --scenario swarm       # 5-agent parallel review
python demo_multiagent.py --scenario burst       # 20 concurrent executions
```

---

## Step 8 — Run the Test Suite

```bash
pytest                              # 290+ tests
pytest tests/unit/ -v               # unit tests only
pytest tests/integration/ -v        # integration tests (needs server? No — uses TestClient)
pytest --cov=afmx --cov-report=html # coverage report in htmlcov/
python scripts/test_realtime.py     # live API suite against running server
python scripts/test_ws.py           # WebSocket streaming demo
```

---

## Pre-Registered Handlers

These are available in every fresh AFMX server:

### Tools

| Handler | What it does |
|---|---|
| `echo` | Returns input as-is — useful for testing |
| `upper` | Uppercases string input |
| `concat` | Joins all upstream `node_outputs` into one string |
| `multiply` | `input × params.factor` |
| `summarize` | Truncates to 80 chars, 100ms simulated delay |
| `validate` | Checks `params.required_fields` exist in input |
| `enrich` | Adds tenant/source/tags metadata to input |
| `route` | Classifies input → `{category: normal/urgent/error}` |

### Agents (realistic stubs with LLM-shaped output)

| Handler | What it does |
|---|---|
| `analyst_agent` | Analysis with confidence score (0.52–0.97), reasoning chain, token count |
| `writer_agent` | Content generation reading upstream `node_outputs` |
| `reviewer_agent` | Approval/rejection with score, constraint checking |

### Fault-simulation (for testing retry/fallback)

| Handler | What it does |
|---|---|
| `flaky` | Fails on attempts 1 & 2, succeeds on attempt 3 |
| `always_fail` | Always raises — use with `fallback_node_id` |
| `fallback_recovery` | Graceful fallback — used as `fallback_node_id` target |
| `slow` | Sleeps `params.sleep_seconds` — tests timeout enforcement |

---

## CLI Reference

```bash
afmx serve                    # Start server (default :8100)
afmx serve --reload           # Dev mode with auto-reload
afmx serve --port 8200        # Custom port

afmx run matrix.json          # Execute matrix from file
afmx run matrix.json --async  # Fire and forget
afmx run matrix.json --watch  # Stream events in terminal

afmx status <execution_id>    # Poll execution status
afmx result <execution_id>    # Full result with node outputs
afmx list                     # Recent executions
afmx list --status FAILED     # Filter by status

afmx validate matrix.json     # Validate without executing
afmx cancel <execution_id>    # Cancel running execution
afmx plugins                  # List registered handlers
afmx health                   # Server health check
```

---

## Next Steps

- [Core Concepts](concepts.md) — understand Node, Edge, Matrix, Context, Record
- [Matrix Design](matrix_design.md) — advanced patterns (conditional routing, hybrid mode, variable resolver)
- [Writing Handlers](handlers.md) — register your own agent and tool handlers
- [API Reference](api_reference.md) — full REST endpoint documentation
- [Observability](observability.md) — Prometheus, WebSocket, Agentability integration
