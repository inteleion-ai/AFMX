# AFMX — Agent Flow Matrix Execution Engine

> **"LangGraph helps you build demos. AFMX helps you run production AI systems."**

AFMX is the **execution fabric for autonomous agents** — deterministic, fault-tolerant, and built like infrastructure.

[![CI](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml/badge.svg)](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/afmx.svg)](https://pypi.org/project/afmx/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-production--stable-brightgreen)]()

---

## What is AFMX?

AFMX is a **production-grade, deterministic execution fabric for autonomous agents**.
It is not an agent reasoning framework — it is the layer that controls *how* agents act reliably in production.

```
Your Agent Logic  (LangChain / LangGraph / CrewAI / OpenAI / custom Python)
        ↓
ExecutionMatrix   (DAG: nodes + edges + mode + abort policy)
        ↓
AFMXEngine
        ↓
Deterministic execution:
  retry · fallback · circuit breaker · hooks · events · audit · RBAC
```

---

## Install

```bash
pip install afmx
```

Or install with extras:

```bash
pip install "afmx[redis,metrics]"    # Redis store + Prometheus
pip install "afmx[full]"             # everything except adapter frameworks
pip install "afmx[dev]"              # development + testing toolchain
```

---

## Quick Start

```bash
python3.10 -m afmx serve --reload
# API:       http://localhost:8100
# Docs:      http://localhost:8100/docs
# Dashboard: http://localhost:8100/afmx/ui
```

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

### Run the live demo (7 multi-agent scenarios)

```bash
pip install httpx
python demo_multiagent.py --scenario all
```

---

## Core Features

| Layer | Responsibility |
|---|---|
| `ExecutionMatrix` | DAG of nodes and edges — the execution topology |
| `AFMXEngine` | SEQUENTIAL, PARALLEL, HYBRID orchestration |
| `NodeExecutor` | Per-node execution with retry, timeout, circuit breaker |
| `RetryManager` | Exponential backoff + jitter + per-node circuit breaker |
| `ToolRouter` | Deterministic rule-based tool selection |
| `AgentDispatcher` | Routes agents by complexity, capability, or policy |
| `HookRegistry` | PRE/POST node and matrix hooks |
| `EventBus` | Every state transition emits an observable event |
| `ConcurrencyManager` | Global semaphore with queue timeout |
| `StateStore` | In-memory or Redis-backed execution persistence |
| `MatrixStore` | Named, versioned matrix definitions |
| `CheckpointStore` | Per-node incremental checkpoints for resumability |
| `AuditStore` | Append-only audit trail (JSON/CSV/NDJSON export) |
| `RBACMiddleware` | 5 roles × 16 permissions API key authentication |
| `PluginRegistry` | Decorator-first handler registration |

---

## Execution Modes

| Mode | Behaviour |
|---|---|
| `SEQUENTIAL` | Topological order, one node at a time, conditional edge evaluation |
| `PARALLEL` | All nodes fire concurrently under semaphore cap |
| `HYBRID` | DAG level-sets — same-level nodes run in parallel, levels are sequential |

---

## Fault Tolerance

```python
from afmx import Node, RetryPolicy, CircuitBreakerPolicy, TimeoutPolicy

Node(
    name="external_api",
    handler="api_call",
    retry_policy=RetryPolicy(
        retries=5,
        backoff_seconds=1.0,
        backoff_multiplier=2.0,   # 1s → 2s → 4s → 8s → 16s
        jitter=True,
    ),
    circuit_breaker=CircuitBreakerPolicy(
        enabled=True,
        failure_threshold=5,
        recovery_timeout_seconds=60.0,
    ),
    fallback_node_id="api_fallback",
)
```

---

## Framework Adapters

Built-in adapters for LangChain, LangGraph, CrewAI, and OpenAI — all lazy-loaded.

```python
from afmx.adapters.langchain import LangChainAdapter
from langchain.tools import DuckDuckGoSearchRun

adapter = LangChainAdapter()
node = adapter.to_afmx_node(DuckDuckGoSearchRun(), node_id="search")
```

---

## Registering Handlers

```python
from afmx.plugins import default_registry

@default_registry.agent("my_analyst")
async def analyst(node_input: dict, context, node) -> dict:
    topic = node_input["input"].get("topic", "")
    return {"analysis": f"Analysis of: {topic}", "confidence": 0.87}

@default_registry.tool("web_search")
async def search(node_input: dict, context, node) -> dict:
    query = node_input["params"].get("query") or node_input["input"]
    return {"results": await run_search(query)}
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/afmx/execute` | Execute matrix synchronously |
| `POST` | `/afmx/execute/async` | Execute and return immediately |
| `GET` | `/afmx/result/{id}` | Full result with node outputs |
| `POST` | `/afmx/validate` | Validate matrix without executing |
| `POST` | `/afmx/retry/{id}` | Retry failed execution |
| `POST` | `/afmx/matrices` | Save named matrix |
| `GET` | `/afmx/executions` | List recent executions |
| `GET` | `/afmx/audit` | Query audit log |
| `WS` | `/afmx/ws/stream/{id}` | Real-time event streaming |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |

---

## Dashboard

React 18 SPA included:

```bash
cd afmx/dashboard
npm install && npm run build   # served at /afmx/ui
npm run dev                    # hot-reload at localhost:5173
```

Pages: Overview · Executions (trace/waterfall/output) · Live Stream · Run Matrix · Saved Matrices · Plugins · Audit Log · API Keys

---

## Observability

```python
# Subscribe to any execution event
@bus.subscribe(EventType.NODE_FAILED)
async def on_fail(event):
    await alert_team(event.execution_id, event.data["error"])
```

Prometheus metrics scraped at `GET /metrics`. WebSocket streaming at `WS /afmx/ws/stream/{id}`.

---

## Docker

```bash
docker build -t afmx:latest .
docker run -p 8100:8100 --env-file .env afmx:latest

# Full stack: AFMX + Redis + Prometheus
docker-compose up -d
```

---

## Documentation

Full documentation in [`docs/`](docs/):

| Doc | Description |
|---|---|
| [Architecture](docs/architecture.md) | System layers, data flow, AFMX vs Airflow / Temporal / LangGraph |
| [Core Concepts](docs/concepts.md) | Node, Edge, Matrix, Context, Record |
| [Quick Start](docs/quickstart.md) | 5-minute setup guide |
| [Handlers](docs/handlers.md) | Writing and registering handlers |
| [Matrix Design](docs/matrix_design.md) | Modes, conditions, variable resolver |
| [API Reference](docs/api_reference.md) | All REST endpoints |
| [Adapters](docs/adapters.md) | LangChain, LangGraph, CrewAI, OpenAI |
| [Hooks](docs/hooks.md) | PRE/POST hooks |
| [Observability](docs/observability.md) | EventBus, Prometheus, WebSocket, Agentability |
| [Configuration](docs/configuration.md) | All `AFMX_` environment variables |
| [Testing](docs/testing.md) | Running the test suite |
| [Deployment](docs/deployment.md) | Docker, production hardening |

---

## Testing

```bash
pytest                              # 290+ tests
pytest tests/unit/ -v               # unit tests only
pytest tests/integration/ -v        # integration tests only
pytest --cov=afmx --cov-report=html # HTML coverage report
```

---

## AFMX vs LangGraph

| | AFMX | LangGraph |
|---|---|---|
| Determinism | ✅ Same input = same path | ❌ LLM-dependent |
| Fault tolerance | ✅ Retry + fallback + circuit breaker | ❌ Manual |
| Parallel execution | ✅ Native PARALLEL + HYBRID | ⚠️ Limited |
| Production grade | ✅ RBAC, audit, checkpoints, Redis | ⚠️ App-layer |

**Mental model:** AFMX = how agents **act**. LangGraph = how agents **think**. They are complementary — AFMX can execute LangGraph graphs as nodes.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Enterprise features (multi-tenancy, SSO/OIDC, cryptographic execution integrity, distributed workers, cost governance, AFMX Cloud) are available under a separate commercial license.
See [ENTERPRISE.md](ENTERPRISE.md) or contact **enterprise@agentdyne9.com**.
