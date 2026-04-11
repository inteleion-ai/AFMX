# AFMX Documentation

**Agent Flow Matrix Execution Engine**
Version 1.3.0 · Python 3.10+ · Apache 2.0

---

## What is AFMX?

AFMX is a **production-grade, deterministic execution fabric for autonomous agents**. It is the layer that controls *how* agents act — not what they decide.

Think of it as Kubernetes for agent execution: you declare a DAG of work to be done, AFMX executes it reliably with retry, fallback, circuit breaking, concurrency control, and full observability.

```
Your Agent Logic  (LangChain / LangGraph / CrewAI / OpenAI / custom Python)
        ↓
ExecutionMatrix   (DAG: nodes + edges + mode + abort policy)
        ↓
AFMXEngine
        ↓
Deterministic execution with:
  retry · fallback · circuit breaker · hooks · events · metrics · audit
        ↓
Agentability     (optional — captures decisions, confidence, cost, conflicts)
```

---

## Core Positioning

| What AFMX Is | What AFMX Is Not |
|---|---|
| Execution fabric for agents | Reasoning / planning engine |
| Deterministic DAG runner | LLM orchestrator (that's LangChain) |
| Fault-tolerant node executor | Workflow scheduler (that's Airflow) |
| Framework bridge (LC / LG / CrewAI / OpenAI) | Replacement for those frameworks |
| Observable, auditable runtime | Black box |

**AFMX vs Airflow:** Airflow schedules recurring data pipelines using time-based triggers. AFMX executes agent graphs on API demand. Airflow has no concept of agent outputs flowing between tasks; AFMX passes structured output between every node. See [Architecture](architecture.md) for the full comparison.

---

## Documentation Map

| Document | What it covers |
|---|---|
| **[Architecture](architecture.md)** | System design, layers, internal data flow, comparison with similar tools |
| **[Core Concepts](concepts.md)** | Node, Edge, Matrix, Context, Record — the five primitives |
| **[Quick Start](quickstart.md)** | Install → first execution in 5 minutes |
| **[Writing Handlers](handlers.md)** | How to write, register, and test handler functions |
| **[Matrix Design](matrix_design.md)** | Modes, edges, conditions, abort policies, variable resolver |
| **[API Reference](api_reference.md)** | Every REST endpoint with full request/response schemas |
| **[Adapters](adapters.md)** | LangChain, LangGraph, CrewAI, OpenAI adapter guide |
| **[Hooks](hooks.md)** | PRE/POST matrix and node hooks for cross-cutting behaviour |
| **[Observability](observability.md)** | EventBus, Prometheus metrics, WebSocket streaming, Agentability |
| **[Configuration](configuration.md)** | All `AFMX_` environment variables with defaults and examples |
| **[Testing](testing.md)** | Running the test suite, writing new tests, load testing |
| **[Deployment](deployment.md)** | Docker, Oracle Cloud Linux, Redis backend, production hardening |

---

## Project Layout

```
AFMX/
├── afmx/
│   ├── core/
│   │   ├── engine.py          # AFMXEngine — SEQUENTIAL / PARALLEL / HYBRID
│   │   ├── executor.py        # NodeExecutor + HandlerRegistry
│   │   ├── retry.py           # RetryManager + CircuitBreaker
│   │   ├── router.py          # ToolRouter — deterministic tool routing
│   │   ├── dispatcher.py      # AgentDispatcher — complexity/capability routing
│   │   ├── hooks.py           # HookRegistry — PRE/POST node/matrix hooks
│   │   ├── concurrency.py     # ConcurrencyManager — global semaphore
│   │   └── variable_resolver.py  # {{template}} param resolution
│   ├── models/
│   │   ├── node.py            # Node, NodeResult, RetryPolicy, TimeoutPolicy
│   │   ├── edge.py            # Edge, EdgeCondition (5 condition types)
│   │   ├── matrix.py          # ExecutionMatrix, topological sort, batch grouping
│   │   └── execution.py       # ExecutionContext, ExecutionRecord, ExecutionStatus
│   ├── api/
│   │   ├── routes.py          # Core execution endpoints
│   │   ├── matrix_routes.py   # Named matrix CRUD + execute-by-name
│   │   ├── websocket.py       # Real-time event streaming (WS)
│   │   ├── adapter_routes.py  # Adapter registry inspection
│   │   ├── admin_routes.py    # RBAC key management + admin stats
│   │   ├── audit_routes.py    # Audit log query + export
│   │   └── schemas.py         # Pydantic v2 request/response models
│   ├── adapters/              # LangChain, LangGraph, CrewAI, OpenAI bridges
│   ├── store/
│   │   ├── state_store.py     # ExecutionRecord store (memory + Redis)
│   │   ├── matrix_store.py    # Named matrix store (memory + Redis)
│   │   └── checkpoint.py      # Per-node checkpoint store (memory + Redis)
│   ├── observability/
│   │   ├── events.py          # EventBus + AFMXEvent
│   │   ├── metrics.py         # Prometheus metrics (wired to EventBus)
│   │   └── webhook.py         # Outbound webhook notifier
│   ├── auth/
│   │   ├── rbac.py            # APIKey model, Role enum, 5 roles × 16 permissions
│   │   └── store.py           # APIKey store (memory + Redis)
│   ├── audit/
│   │   ├── model.py           # AuditEvent model, AuditAction enum
│   │   └── store.py           # Audit store (memory + Redis), export (JSON/CSV/NDJSON)
│   ├── middleware/
│   │   ├── rbac.py            # RBAC enforcement middleware
│   │   ├── rate_limit.py      # Token-bucket rate limiter
│   │   └── logging.py         # Structured request/response logging
│   ├── integrations/
│   │   └── agentability_hook.py  # Agentability observability bridge
│   ├── plugins/
│   │   └── registry.py        # PluginRegistry with @registry.tool/agent/function
│   ├── utils/
│   │   ├── exceptions.py      # Full exception hierarchy
│   │   └── helpers.py         # Timer, deep_merge, async_retry, etc.
│   ├── config.py              # AFMXSettings (pydantic-settings, AFMX_ prefix)
│   ├── main.py                # FastAPI app factory + lifespan bootstrap
│   ├── startup_handlers.py    # 15 built-in handlers registered at startup
│   ├── cli.py                 # `afmx` CLI (serve, run, status, validate, ...)
│   └── dashboard/             # React 18 SPA — built via `npm run build`
├── tests/
│   ├── unit/                  # 18 files, 250+ test cases
│   └── integration/           # Engine + API integration (4 files, 40+ cases)
├── examples/                  # 8 runnable Python examples
├── docs/                      # This documentation
├── scripts/                   # Shell + Python dev/test scripts
├── demo_multiagent.py         # 7-scenario live multi-agent demo
├── demo_agentability.py       # AFMX + Agentability integration demo
├── realistic_handlers.py      # Production-grade agent handlers with LLM stubs
├── Dockerfile                 # 2-stage build (builder + runtime)
├── docker-compose.yml         # AFMX + Redis + Prometheus full stack
├── prometheus.yml             # Prometheus scrape config
├── pyproject.toml             # Project metadata + tool config
├── requirements.txt           # Dev install (range versions)
└── requirements-prod.txt      # Production install (exact pins)
```

---

## Quick Start (60 seconds)

```bash
# 1. Install
cd AFMX
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Start server
python3.10 -m afmx serve --reload
# → http://localhost:8100   API
# → http://localhost:8100/docs  Swagger UI
# → http://localhost:8100/afmx/ui  Dashboard (after npm run build)

# 3. Execute a matrix
curl -s -X POST http://localhost:8100/afmx/execute \
  -H "Content-Type: application/json" \
  -d '{
    "matrix": {
      "name": "hello-world",
      "mode": "SEQUENTIAL",
      "nodes": [{"id":"n1","name":"echo","type":"FUNCTION","handler":"echo"}],
      "edges": []
    },
    "input": {"query": "hello AFMX"}
  }' | python3 -m json.tool

# 4. Run the full multi-agent demo
pip install httpx
python demo_multiagent.py --scenario all
```

---

## Agentability Integration

AFMX integrates with [Agentability](../new_project/agentability/Agentability) — an agent intelligence observatory that captures:

- Every node execution → a **Decision** (with confidence, reasoning, cost, constraints)
- Every matrix execution → a **Session** (session_id = execution_id)
- Circuit breaker trips → **Conflicts**
- Retry attempts → LLM call metrics

Enable it in `.env`:
```bash
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db
```

See [Observability](observability.md#agentability-integration) for full setup instructions.

---

## Test Suite

| Test Suite | Count | Command |
|---|---|---|
| Unit tests | 400+ | `pytest tests/unit/ -v` |
| All tests | 400+ | `pytest` |
| Live API suite | 17 sections | `python scripts/test_realtime.py` |
| WebSocket demo | 3 scenarios | `python scripts/test_ws.py` |
| Load test | configurable | `python scripts/test_load.py --concurrency 20 --total 200` |
| Multi-agent demo | 7 scenarios | `python demo_multiagent.py --scenario all` |
