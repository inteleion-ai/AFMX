# AFMX — Agent Flow Matrix Execution Engine

> **"LangGraph helps you build demos. AFMX helps you run production AI systems."**

AFMX is the **execution fabric for autonomous agents** — deterministic, fault-tolerant, and built like infrastructure.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-production--stable-brightgreen)]()

---

## What AFMX Is

| Layer | Responsibility |
|---|---|
| `ExecutionMatrix` | DAG of nodes and edges — the execution topology |
| `AFMXEngine` | Orchestrates SEQUENTIAL, PARALLEL, and HYBRID execution |
| `NodeExecutor` | Per-node execution with retry, timeout, circuit breaker, hooks |
| `ToolRouter` | Deterministic, rule-based tool selection |
| `AgentDispatcher` | Routes tasks by complexity, capability, or policy |
| `RetryManager` | Exponential backoff + jitter + per-node circuit breaker |
| `HookRegistry` | PRE/POST node and matrix hooks for cross-cutting behaviour |
| `EventBus` | Every state transition emits an observable event |
| `ConcurrencyManager` | Global semaphore with queue timeout and per-matrix caps |
| `StateStore` | In-memory or Redis-backed execution record persistence |
| `MatrixStore` | Named, versioned matrix definitions |
| `CheckpointStore` | Incremental per-node checkpoints for resumability |
| `AuditStore` | Append-only audit trail (JSON/CSV/NDJSON export) |
| `RBACMiddleware` | 5 roles × 16 permissions API key authentication |
| `PluginRegistry` | Decorator-first handler registration |

## What AFMX Is Not

- Not an LLM reasoning layer — that's LangChain, LangGraph, or your agent framework
- Not a memory system — that's HyperState
- Not a workflow scheduler — that's Airflow (see [Architecture](docs/architecture.md) for the full comparison)
- Not a backend orchestration platform — that's Temporal

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  HTTP / WebSocket API                │
│         FastAPI  ·  REST  ·  WS  ·  Admin            │
├─────────────────────────────────────────────────────┤
│                    AFMXEngine                        │
│   ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│   │ NodeExecutor │  │ToolRouter  │  │  Retry +   │  │
│   │  + Hooks     │  │+Dispatcher │  │   CB       │  │
│   └──────────────┘  └────────────┘  └────────────┘  │
│   ┌─────────────────────────────────────────────┐   │
│   │         SEQUENTIAL | PARALLEL | HYBRID       │   │
│   └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│            HandlerRegistry + Adapters                │
│    LangChain · LangGraph · CrewAI · OpenAI           │
├──────────────────────┬──────────────────────────────┤
│   Stores             │   Observability               │
│   State · Matrix     │   EventBus · Prometheus       │
│   Checkpoint · Audit │   WebSocket · Agentability    │
└──────────────────────┴──────────────────────────────┘
```

---

## Quick Start

### 1. Install

```bash
cd AFMX
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Start server

```bash
python3.10 -m afmx serve --reload
# API:       http://localhost:8100
# Docs:      http://localhost:8100/docs
# Dashboard: http://localhost:8100/afmx/ui  (after npm run build)
```

### 3. Execute a matrix

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
    "input": {"topic": "Production multi-agent systems in 2026"}
  }' | python3 -m json.tool
```

### 4. Run the live multi-agent demo

```bash
pip install httpx
python demo_multiagent.py --scenario all
```

This fires 7 real scenarios against the running server — research chains, parallel fan-out, conditional routing, retry/fallback, document pipelines, swarm review, and a 20-execution burst test. Watch everything appear live in the dashboard.

---

## Core Concepts

### Node

The atomic execution unit. Declares what to run and how to run it safely:

```python
from afmx import Node, NodeType, RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy

node = Node(
    id="search",
    name="web_search",
    type=NodeType.TOOL,
    handler="my_search_handler",

    retry_policy=RetryPolicy(retries=3, backoff_seconds=1.0, backoff_multiplier=2.0),
    timeout_policy=TimeoutPolicy(timeout_seconds=15.0),
    circuit_breaker=CircuitBreakerPolicy(enabled=True, failure_threshold=5),

    fallback_node_id="search-fallback",   # run if primary fails terminally
)
```

### Edge

Directed connection between nodes. Supports five condition types:

```python
from afmx import Edge, EdgeCondition, EdgeConditionType

# Always traverse
Edge(**{"from": "n1", "to": "n2"})

# Conditional on output value
Edge(**{
    "from": "classifier", "to": "urgent_handler",
    "condition": EdgeCondition(
        type=EdgeConditionType.ON_OUTPUT,
        output_key="category",
        output_value="urgent",
    )
})

# Python expression
Edge(**{
    "from": "scorer", "to": "high_confidence_path",
    "condition": EdgeCondition(
        type=EdgeConditionType.EXPRESSION,
        expression="output['score'] > 0.85",
    )
})
```

### ExecutionMatrix

The complete DAG declaration:

```python
from afmx import ExecutionMatrix, ExecutionMode, AbortPolicy

matrix = ExecutionMatrix(
    name="research-pipeline",
    mode=ExecutionMode.HYBRID,           # SEQUENTIAL | PARALLEL | HYBRID
    nodes=[analyst_node, writer_node, reviewer_node],
    edges=[edge_analyst_writer, edge_writer_reviewer],
    abort_policy=AbortPolicy.FAIL_FAST,  # FAIL_FAST | CONTINUE | CRITICAL_ONLY
    max_parallelism=10,
    global_timeout_seconds=300.0,
)
```

### Execution Modes

| Mode | Behaviour |
|---|---|
| `SEQUENTIAL` | Topological order, one node at a time, conditional edge evaluation |
| `PARALLEL` | All nodes fire concurrently under semaphore cap |
| `HYBRID` | DAG level-sets — nodes in same level run in parallel, levels are sequential |

### Registering Handlers

```python
from afmx.plugins import default_registry

@default_registry.agent("my_analyst")
async def analyst(node_input: dict, context, node) -> dict:
    topic = node_input["input"].get("topic", "")
    return {
        "analysis": f"Deep analysis of: {topic}",
        "confidence": 0.87,
        "agent": "analyst",
    }

@default_registry.tool("web_search")
async def search(node_input: dict, context, node) -> dict:
    query = node_input["params"].get("query") or node_input["input"]
    results = await run_search(query)
    return {"results": results}
```

### Handler Signature

Every handler receives this exact signature:

```python
async def my_handler(node_input: dict, context: ExecutionContext, node: Node) -> Any:
    node_input["input"]        # Matrix-level input payload
    node_input["params"]       # Resolved node config ({{templates}} expanded)
    node_input["variables"]    # Runtime variables
    node_input["node_outputs"] # All upstream node outputs keyed by node_id
    node_input["memory"]       # Shared execution memory
    node_input["metadata"]     # Merged execution + node metadata
    return {"result": "..."}   # Any JSON-serializable value
```

---

## Retry + Circuit Breaker

Per-node. Configured in the matrix definition:

```python
Node(
    name="external_api",
    type=NodeType.TOOL,
    handler="api_call",
    retry_policy=RetryPolicy(
        retries=5,
        backoff_seconds=1.0,
        backoff_multiplier=2.0,
        max_backoff_seconds=30.0,
        jitter=True,                   # 1s → 2s → 4s → 8s → 16s (±jitter)
    ),
    circuit_breaker=CircuitBreakerPolicy(
        enabled=True,
        failure_threshold=5,           # trips after 5 failures
        recovery_timeout_seconds=60.0, # auto-recovers after 60s
    ),
    fallback_node_id="api_fallback",   # activates if primary fails terminally
)
```

---

## Observability

### Event Bus

```python
@bus.subscribe(EventType.NODE_FAILED)
async def on_fail(event):
    await alert_team(event.execution_id, event.data["error"])
```

### Prometheus Metrics

```
afmx_executions_total{matrix_name, status}
afmx_execution_duration_seconds{matrix_name, status}
afmx_nodes_total{node_type, status}
afmx_node_duration_seconds{node_type, status}
afmx_node_retries_total{node_id}
afmx_circuit_breaker_trips_total{node_id}
afmx_active_executions
```

Scrape at `GET /metrics` when `AFMX_PROMETHEUS_ENABLED=true`.

### WebSocket Streaming

```python
import websockets, json

async with websockets.connect(f"ws://localhost:8100/afmx/ws/stream/{exec_id}") as ws:
    async for msg in ws:
        event = json.loads(msg)
        if event["type"] == "eof": break
        print(event["type"], event.get("data", {}))
```

### Agentability Integration

AFMX integrates with [Agentability](../new_project/agentability/Agentability) to capture agent intelligence data — confidence scores, reasoning chains, token costs, and conflict detection.

```bash
# Enable in .env
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db

# Run the integration demo
python demo_agentability.py
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/afmx/execute` | Execute matrix synchronously |
| `POST` | `/afmx/execute/async` | Execute and return immediately |
| `GET` | `/afmx/status/{id}` | Poll execution status |
| `GET` | `/afmx/result/{id}` | Full result with node outputs |
| `GET` | `/afmx/executions` | List recent executions |
| `POST` | `/afmx/validate` | Validate matrix without executing |
| `POST` | `/afmx/cancel/{id}` | Cancel running execution |
| `POST` | `/afmx/retry/{id}` | Retry failed execution |
| `POST` | `/afmx/matrices` | Save named matrix |
| `GET` | `/afmx/matrices` | List saved matrices |
| `POST` | `/afmx/matrices/{name}/execute` | Execute saved matrix by name |
| `GET` | `/afmx/plugins` | List registered handlers |
| `GET` | `/afmx/adapters` | List framework adapters |
| `GET` | `/afmx/concurrency` | Live concurrency stats |
| `GET` | `/afmx/audit` | Query audit log |
| `GET` | `/afmx/audit/export/{format}` | Export audit (json/csv/ndjson) |
| `GET` | `/afmx/admin/keys` | List API keys (RBAC) |
| `POST` | `/afmx/admin/keys` | Create API key |
| `WS` | `/afmx/ws/stream/{id}` | Real-time event streaming |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |

---

## Dashboard

A production React 18 SPA is included:

```bash
cd afmx/dashboard
npm install
npm run build       # builds to afmx/static/ — served at /afmx/ui
npm run dev         # hot-reload dev at http://localhost:5173
```

Pages: Overview · Executions (trace/waterfall/output) · Live Stream · Run Matrix · Saved Matrices · Plugins · Audit Log · API Keys

---

## Docker

```bash
# Single container
docker build -t afmx:latest .
docker run -p 8100:8100 --env-file .env afmx:latest

# Full stack (AFMX + Redis + Prometheus)
docker-compose up -d
```

---

## Testing

```bash
pytest                              # 290+ tests
pytest tests/unit/ -v               # unit only
pytest tests/integration/ -v        # integration only
pytest --cov=afmx --cov-report=html # HTML coverage report

python scripts/test_realtime.py     # 50+ live API assertions
python scripts/test_ws.py           # WebSocket stream demo
python scripts/test_load.py --concurrency 20 --total 200
```

---

## AFMX vs LangGraph

| | AFMX | LangGraph |
|---|---|---|
| Core focus | Execution & orchestration | LLM reasoning flow |
| Determinism | ✅ Strong — same input = same path | ❌ LLM-dependent |
| Parallel execution | ✅ Native (PARALLEL + HYBRID) | ⚠️ Limited |
| Tool routing | ✅ Rule-based, explicit | ⚠️ Prompt-driven |
| Fault handling | ✅ Retry + fallback + circuit breaker | ❌ Manual |
| Multi-agent scale | ✅ 100+ concurrent agents | ⚠️ Not proven at scale |
| Production grade | ✅ RBAC, audit, checkpoints, Redis | ⚠️ App-layer only |

**Mental model:** AFMX = how agents **act**. LangGraph = how agents **think**. They are not competitors — AFMX can execute LangGraph graphs as nodes.

---

## Documentation

Full documentation in [`docs/`](docs/):

- [Architecture](docs/architecture.md) — layers, data flow, AFMX vs Airflow/Temporal/LangGraph
- [Core Concepts](docs/concepts.md) — Node, Edge, Matrix, Context, Record
- [Quick Start](docs/quickstart.md) — 5-minute setup guide
- [Handlers](docs/handlers.md) — writing and registering handlers
- [Matrix Design](docs/matrix_design.md) — modes, conditions, variable resolver
- [API Reference](docs/api_reference.md) — all endpoints
- [Adapters](docs/adapters.md) — LangChain, LangGraph, CrewAI, OpenAI
- [Hooks](docs/hooks.md) — PRE/POST hooks
- [Observability](docs/observability.md) — EventBus, Prometheus, WebSocket, Agentability
- [Configuration](docs/configuration.md) — all `AFMX_` variables
- [Testing](docs/testing.md) — running the test suite
- [Deployment](docs/deployment.md) — Docker, Oracle Cloud, production hardening

---

## Founder Note

AFMX must be:
- **Deterministic** — same input always produces the same execution path
- **Fast** — zero AI in the core execution loop
- **Composable** — plug in any router, dispatcher, store, or adapter
- **Observable** — every state transition is a measurable, streamable event
- **Fault-tolerant** — retry, fallback, circuit breaker at every node

> Do NOT make the engine intelligent. It is the execution layer — not the brain.
