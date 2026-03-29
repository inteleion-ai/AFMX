# AFMX — Agent Flow Matrix Execution Engine

> **"Tag your agent's cognitive intent once. Get 60–90% cheaper LLM costs automatically, with a full audit trail. No rewrites. Works with LangGraph, CrewAI, OpenAI, MCP, and anything else you're already running."**

[![CI](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml/badge.svg)](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-afmx%201.2.1-blue)](https://pypi.org/project/afmx/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

## The one-line pitch

```python
from afmx import Node, CognitiveLayer

# Add ONE field to your existing node.
# AFMX auto-routes: cheap model for retrieval/action, premium for reasoning/planning.
node = Node(name="analyse", handler="my_agent", cognitive_layer=CognitiveLayer.REASON)
# → Claude Opus / GPT-4o selected automatically
# → cheaper layers get Haiku / gpt-4o-mini automatically
# → every node result logged to tamper-evident audit trail
# → visual heatmap shows cost + model per cell
```

AFMX is the **production execution fabric for autonomous agents**. Deterministic, fault-tolerant, built like infrastructure.

[![Docs](https://img.shields.io/badge/docs-afmx.inteleion.com-blue)](https://afmx.inteleion.com/docs)

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

With extras:
```bash
pip install "afmx[redis,metrics]"    # Redis store + Prometheus
pip install "afmx[full]"             # everything except framework adapters
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

### Live demo — 7 multi-agent scenarios
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
```python
from afmx.adapters.langchain import LangChainAdapter
from langchain.tools import DuckDuckGoSearchRun

adapter = LangChainAdapter()
node = adapter.to_afmx_node(DuckDuckGoSearchRun(), node_id="search")
```

Built-in adapters: LangChain · LangGraph · CrewAI · OpenAI — all lazy-loaded.

---

## Registering Handlers
```python
from afmx.plugins import default_registry

@default_registry.agent("my_analyst")
async def analyst(node_input: dict, context, node) -> dict:
    return {"analysis": "...", "confidence": 0.87}

@default_registry.tool("web_search")
async def search(node_input: dict, context, node) -> dict:
    return {"results": await run_search(node_input["input"])}
```

---

## Cognitive Execution Matrix

AFMX v1.2 introduces the **Cognitive Execution Matrix** — a 2D coordinate system that
maps every node to a cognitive layer (what type of thinking) and an agent role (which
domain role performs it).

```
                  ROLES (open, domain-specific)
                  OPS   ANALYST  QUANT  CLINICIAN  PARALEGAL
LAYERS  PERCEIVE   ■      □       □       □          □
(fixed) RETRIEVE   ■      □       ■       □          □
        REASON     □      ■       ■       ■          □
        PLAN       ■      □       □       ■          ■
        ACT        ■      □       ■       □          □
        EVALUATE   □      ■       □       ■          □
        REPORT     ■      □       □       □          □
```

Row axis = **CognitiveLayer** (fixed, universal, drives automatic LLM cost routing).
Column axis = **AgentRole** (open string — any industry vocabulary).

```python
from afmx import Node, NodeType, CognitiveLayer
from afmx.domains.finance import FinanceRole

# Finance domain node
node = Node(
    name            = "risk-scorer",
    type            = NodeType.AGENT,
    handler         = "risk_model",
    cognitive_layer = CognitiveLayer.REASON,    # → premium LLM auto-selected
    agent_role      = FinanceRole.RISK_MANAGER, # == "RISK_MANAGER"
)

# Healthcare domain node
from afmx.domains.healthcare import HealthcareRole
node = Node(
    name            = "diagnosis",
    type            = NodeType.AGENT,
    handler         = "diagnostic_model",
    cognitive_layer = "REASON",
    agent_role      = HealthcareRole.CLINICIAN,
)

# Custom domain — any UPPER_SNAKE_CASE string is valid
node = Node(
    cognitive_layer = "PLAN",
    agent_role      = "DISPATCHER",   # logistics domain
    ...
)
```

**Built-in domain packs:** tech · finance · healthcare · legal · manufacturing.
**Custom domains:** register in 8 lines with `DomainPack` + `domain_registry`.

### LLM cost routing (automatic)

The `CognitiveModelRouter` auto-selects models by cognitive layer:
```
PERCEIVE / RETRIEVE / ACT / REPORT  →  cheap model  (Haiku, gpt-4o-mini)
REASON   / PLAN     / EVALUATE      →  premium model (Opus, o3, gpt-4o)
```
Typical result: 60–90% LLM cost reduction on multi-agent workflows.

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/afmx/execute` | Execute matrix synchronously |
| `POST` | `/afmx/execute/async` | Execute and return immediately |
| `GET` | `/afmx/result/{id}` | Full result with node outputs |
| `POST` | `/afmx/validate` | Validate matrix without executing |
| `POST` | `/afmx/retry/{id}` | Retry failed execution |
| `POST` | `/afmx/resume/{id}` | Resume from checkpoint |
| `POST` | `/afmx/matrices` | Save named matrix |
| `GET` | `/afmx/executions` | List recent executions |
| `GET` | `/afmx/matrix-view/{id}` | Cognitive Matrix view for an execution |
| `GET` | `/afmx/domains` | List all domain packs |
| `GET` | `/afmx/domains/{name}` | Get a domain pack by name |
| `GET` | `/afmx/audit` | Query audit log |
| `WS` | `/afmx/ws/stream/{id}` | Real-time event streaming |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |

---

## Dashboard
```bash
cd afmx/dashboard
npm install && npm run build   # served at /afmx/ui
npm run dev                    # hot-reload at localhost:5173
```

Pages: Overview · Executions · Live Stream · Run Matrix · Saved Matrices · Plugins · **Cognitive Matrix** · **Domain Packs** · Audit Log · API Keys

Run Matrix includes cross-domain templates: `cognitive` (SRE) · `finance` · `healthcare` · `legal`.

---

## Observability
```python
@bus.subscribe(EventType.NODE_FAILED)
async def on_fail(event):
    await alert_team(event.execution_id, event.data["error"])
```

Prometheus metrics at `GET /metrics`. WebSocket streaming at `WS /afmx/ws/stream/{id}`.

---

## Agentability Integration

AFMX integrates with [Agentability](https://github.com/inteleion-ai/Agentability) — captures confidence scores, reasoning chains, token costs, and conflict detection per node execution.
```bash
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db
python demo_agentability.py
```

---

## Docker
```bash
docker build -t afmx:latest .
docker run -p 8100:8100 --env-file .env afmx:latest

# Full stack: AFMX + Redis + Prometheus
docker-compose up -d
```

---

## Testing
```bash
pytest                              # 290+ tests
pytest tests/unit/ -v               # unit only
pytest tests/integration/ -v        # integration only
pytest --cov=afmx --cov-report=html # coverage report
```

---

## Documentation

| Doc | Description |
|---|---|
| [Architecture](docs/architecture.md) | Layers, data flow, AFMX vs Airflow/Temporal/LangGraph |
| [Core Concepts](docs/concepts.md) | Node, Edge, Matrix, Context, Record |
| [Quick Start](docs/quickstart.md) | 5-minute setup guide |
| [Handlers](docs/handlers.md) | Writing and registering handlers |
| [Matrix Design](docs/matrix_design.md) | Modes, edge conditions, variable resolver |
| [API Reference](docs/api_reference.md) | All REST endpoints |
| [Adapters](docs/adapters.md) | LangChain, LangGraph, CrewAI, OpenAI |
| [Hooks](docs/hooks.md) | PRE/POST hooks |
| [Observability](docs/observability.md) | EventBus, Prometheus, WebSocket, Agentability |
| [Configuration](docs/configuration.md) | All `AFMX_` environment variables |
| [Testing](docs/testing.md) | Running the test suite |
| [Deployment](docs/deployment.md) | Docker, Oracle Cloud, production hardening |

---

## AFMX vs alternatives (March 2026)

| | AFMX 1.2 | LangGraph 1.0 | OpenAI Agents SDK | CrewAI |
|---|---|---|---|---|
| Deterministic ordering | ✅ | ❌ LLM-dependent | ❌ | ❌ |
| Per-node fault tolerance | ✅ Retry + CB + fallback | ❌ Manual | ⚠️ Basic | ❌ |
| Full audit trail | ✅ Append-only, exportable | ❌ | ⚠️ | ❌ |
| Cognitive cost routing | ✅ 60-90% LLM cost reduction | ❌ | ❌ | ❌ |
| Cross-industry domains | ✅ 5 built-in + custom | ❌ | ❌ | ❌ |
| Execution resume | ✅ Checkpoint-based | ❌ | ❌ | ❌ |
| RBAC + multi-tenancy | ✅ | ❌ | ❌ | ❌ |
| Cognitive Matrix UI | ✅ | ❌ | ❌ | ❌ |

**Mental model:** AFMX = how agents **act**. LangGraph = how agents **think**.
They are complementary — AFMX can execute LangGraph graphs as nodes.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Enterprise features (multi-tenancy, SSO/OIDC, cryptographic execution integrity, distributed workers, cost governance, AFMX Cloud) available under a separate commercial license.
See [ENTERPRISE.md](ENTERPRISE.md) or contact **support@inteleion.com**.
