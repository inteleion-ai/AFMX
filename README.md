# AFMX — Agent Flow Matrix Execution Engine

> **60–90% cheaper LLM costs. Automatic. Tag one field.**

[![CI](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml/badge.svg)](https://github.com/inteleion-ai/AFMX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/afmx?color=blue&label=PyPI)](https://pypi.org/project/afmx/)
[![npm](https://img.shields.io/npm/v/@agentdyne9/afmx?color=blue&label=npm)](https://www.npmjs.com/package/@agentdyne9/afmx)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-60%25%2B-brightgreen)](https://github.com/inteleion-ai/AFMX/actions)

---

## The 30-second pitch

```python
from afmx import Node, CognitiveLayer

# Add ONE field to any existing node.
node = Node(
    name="analyse",
    handler="my_agent",
    cognitive_layer=CognitiveLayer.REASON,  # ← this is all you change
)
# → Claude Opus / GPT-4o selected automatically for REASON nodes
# → PERCEIVE / RETRIEVE / ACT nodes get Haiku / gpt-4o-mini
# → every execution logged to tamper-evident audit trail
# → visual heatmap shows cost + model tier per cell
```

AFMX is the **production execution fabric for autonomous agents** — the layer that controls *how* agents act reliably, cheaply, and auditably. Not an agent framework. Not a reasoning engine. The infrastructure underneath them.

---

## Install

```bash
# Core
pip install afmx

# With optional extras
pip install "afmx[mcp]"               # MCP server adapter
pip install "afmx[semantic-kernel]"   # Microsoft Semantic Kernel
pip install "afmx[google-adk]"        # Google ADK
pip install "afmx[bedrock]"           # Amazon Bedrock
pip install "afmx[redis,metrics]"     # Redis store + Prometheus
pip install "afmx[adapters]"          # All framework adapters
pip install "afmx[full]"              # Everything except framework adapters
```

```bash
# TypeScript / JavaScript
npm install @agentdyne9/afmx
```

---

## Quick Start

```bash
python -m afmx serve --reload
# API:       http://localhost:8100
# Swagger:   http://localhost:8100/docs
# Dashboard: http://localhost:8100/afmx/ui
```

```bash
curl -s -X POST http://localhost:8100/afmx/execute \
  -H "Content-Type: application/json" \
  -d '{
    "matrix": {
      "name": "research-pipeline",
      "mode": "DIAGONAL",
      "nodes": [
        {"id":"p1","name":"ingest","type":"AGENT","handler":"perceive","cognitive_layer":"PERCEIVE","agent_role":"OPS"},
        {"id":"r1","name":"analyse","type":"AGENT","handler":"reason","cognitive_layer":"REASON","agent_role":"ANALYST"},
        {"id":"a1","name":"report","type":"AGENT","handler":"report","cognitive_layer":"REPORT","agent_role":"OPS"}
      ],
      "edges": [{"from":"p1","to":"r1"},{"from":"r1","to":"a1"}]
    },
    "input": {"topic": "Multi-agent systems in 2026"}
  }' | python3 -m json.tool
```

---

## Why AFMX

### The problem

Every multi-agent system eventually answers the same question: *did we really need GPT-4o for that `read_file` call?*

Routing all nodes through the same frontier model is the path of least resistance. It is also expensive and wasteful — most of what agents do is retrieval, formatting, and simple actions. Complex reasoning is a small fraction of total calls, but it consumes most of the bill.

### The fix

AFMX's `CognitiveModelRouter` routes model selection automatically based on what a node *does*, not which node it is:

```
PERCEIVE / RETRIEVE / ACT / REPORT  →  cheap model  (Haiku, gpt-4o-mini)
REASON   / PLAN     / EVALUATE      →  premium model (Opus, gpt-4o, o3)
```

Tag the node once. Pay 60–90% less. Get a full audit trail showing which model ran in which cell, at what cost, with whose authority.

---

## Cognitive Execution Matrix

The matrix is the core abstraction — a 2D coordinate system mapping every node to:
- **ROW** → `CognitiveLayer` (fixed, universal — drives model routing)
- **COLUMN** → `AgentRole` (open string — any domain vocabulary)

```
                  ROLES → domain-specific, open string
                  OPS      ANALYST   QUANT   CLINICIAN  PARALEGAL
LAYERS  PERCEIVE   ■         □         □         □          □
(fixed) RETRIEVE   ■         □         ■         □          □
        REASON     □         ■         ■         ■          □
        PLAN       ■         □         □         ■          ■
        ACT        ■         □         ■         □          □
        EVALUATE   □         ■         □         ■          □
        REPORT     ■         □         □         □          □
```

Five built-in domain packs: **tech** · **finance** · **healthcare** · **legal** · **manufacturing**. Custom domains in 8 lines.

```python
from afmx import Node, CognitiveLayer, NodeType
from afmx.domains.finance import FinanceRole

# Finance: automatic premium routing for REASON, cheap for RETRIEVE
risk_node = Node(
    name="risk-scorer",
    type=NodeType.AGENT,
    handler="risk_model",
    cognitive_layer=CognitiveLayer.REASON,    # → Opus / GPT-4o
    agent_role=FinanceRole.RISK_MANAGER,
)

# Cross-domain — any UPPER_SNAKE_CASE string
logistics_node = Node(
    cognitive_layer="PLAN",
    agent_role="DISPATCHER",
    handler="route_planner",
)
```

### DIAGONAL execution mode

Groups nodes by cognitive layer, runs each layer's nodes in parallel, layers execute in canonical order:

```
PERCEIVE → RETRIEVE → REASON → PLAN → ACT → EVALUATE → REPORT
```

Perfect for complex pipelines where ingestion, analysis, and action must be sequential *at the layer level* but parallel *within each layer*.

---

## Framework Adapters

AFMX wraps anything. All adapters are lazy-loaded — the framework only needs to be installed if you use it.

### MCP (Model Context Protocol)

```python
from afmx.adapters.mcp import MCPAdapter

adapter = MCPAdapter()

# SSE transport — remote server
nodes = await adapter.from_server("http://localhost:3000")

# stdio transport — local process (Claude Desktop format)
nodes = await adapter.from_config({
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-filesystem", "/"],
})

# Load all servers from Claude Desktop config at once
nodes = await adapter.from_desktop_config({
    "mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@anthropic/mcp-server-filesystem", "/"]},
        "github":     {"command": "npx", "args": ["-y", "@anthropic/mcp-server-github"]},
    }
})
# CognitiveLayer auto-inferred: read_file→RETRIEVE, write_file→ACT, check_health→EVALUATE
```

### LangChain / LangGraph / CrewAI / OpenAI

```python
from afmx.adapters.langchain import LangChainAdapter
from langchain.tools import DuckDuckGoSearchRun

adapter = LangChainAdapter()
node = adapter.to_afmx_node(DuckDuckGoSearchRun(), node_id="search")
```

### Microsoft Semantic Kernel

```python
from afmx.adapters.semantic_kernel import SemanticKernelAdapter

adapter = SemanticKernelAdapter(kernel=my_kernel)
node = adapter.function_node(fn, node_name="summarise", cognitive_layer="REASON")
nodes = adapter.plugin_nodes("WebSearch", agent_role="OPS")
```

### Google ADK

```python
from afmx.adapters.google_adk import GoogleADKAdapter

adapter = GoogleADKAdapter()
search_node = adapter.tool_node(google_search)          # → RETRIEVE
agent_node  = adapter.agent_node(researcher_agent)      # → REASON
plan_node   = adapter.agent_node(SequentialAgent(...))  # → PLAN (auto)
```

### Amazon Bedrock

```python
from afmx.adapters.bedrock import BedrockAdapter

adapter = BedrockAdapter(region_name="us-east-1")

# Direct model invocation (all providers: Claude, Llama, Titan, Mistral, Cohere)
haiku_node  = adapter.model_node("anthropic.claude-3-haiku-20240307-v1:0")   # → RETRIEVE
sonnet_node = adapter.model_node("anthropic.claude-3-5-sonnet-20241022-v2:0") # → REASON

# Bedrock Agent
agent_node = adapter.agent_node("AGENT_ID_HERE", "TSTALIASID")
```

---

## Platform Integrations

### HyperState — Cognitive Memory

```python
from afmx.integrations.hyperstate import attach_hyperstate

attach_hyperstate(
    api_url="http://localhost:8000",
    api_key="hs_...",
    hook_registry=afmx_app.hook_registry,
    inject_into_memory=True,    # PRE_NODE: inject memories into RETRIEVE nodes
    persist_agent_outputs=True, # POST_NODE: store REASON/PLAN outputs back
)
# RETRIEVE nodes now query HyperState automatically.
# handler="hyperstate:retrieve" and handler="hyperstate:store" always available.
```

### MAP — Verified Context

```python
from map.service import MAPService
from afmx.integrations.map_plugin import attach_map

map_svc = await MAPService.create()
await attach_map(
    service=map_svc,
    hook_registry=afmx_app.hook_registry,
    inject_into_memory=True,  # SHA-256 verified ContextUnit[] before RETRIEVE nodes
)
# handler="map:retrieve" and handler="map:verify" always available.
```

### RHFL — Human Governance Gate

```python
from afmx.integrations.rhfl import attach_rhfl

attach_rhfl(
    api_url="http://rhfl.internal:4000/api/v1",
    token=os.getenv("RHFL_TOKEN"),
    hook_registry=afmx_app.hook_registry,
    gate_act_nodes=True,  # ALL ACT-layer nodes require human approval
    max_wait=300.0,       # 5 min to approve or reject
)
# AUTO → proceed · REVIEW → poll · BLOCK → RHFLBlockedError · ESCALATE → escalate
```

### Agentability — Observability

```python
from afmx.integrations.agentability_hook import attach_to_afmx

attach_to_afmx(
    afmx_app.hook_registry,
    afmx_app.event_bus,
    db_path="agentability.db",
)
# Every node execution → Agentability Decision with confidence, cost, reasoning chain
```

---

## TypeScript SDK

```typescript
import { AFMXClient, ExecutionMode, CognitiveLayer, buildNode, buildEdge } from "@agentdyne9/afmx";

const client = new AFMXClient({ baseUrl: "http://localhost:8100" });

const result = await client.execute({
  matrix: {
    name: "risk-analysis",
    mode: ExecutionMode.DIAGONAL,
    nodes: [
      buildNode({ id: "retrieve", name: "fetch-data",    handler: "data_retriever",  layer: CognitiveLayer.RETRIEVE, role: "QUANT" }),
      buildNode({ id: "analyse",  name: "analyse-risk",  handler: "risk_analyser",   layer: CognitiveLayer.REASON,   role: "RISK_MANAGER" }),
      buildNode({ id: "report",   name: "generate-report", handler: "reporter",      layer: CognitiveLayer.REPORT,   role: "ANALYST" }),
    ],
    edges: [buildEdge("retrieve", "analyse"), buildEdge("analyse", "report")],
  },
  input: { ticker: "AAPL", lookback_days: 30 },
});

console.log(result.status, result.duration_ms + "ms");

// Async + poll
const { execution_id } = await client.executeAsync({ matrix, input });
const final = await client.pollUntilDone(execution_id, { intervalMs: 500 });

// Cognitive Matrix heatmap
const view = await client.matrixView(execution_id);
// view.cells["REASON:RISK_MANAGER"] → { status, model_tier, duration_ms }
```

---

## Core Engine

```python
from afmx import Node, RetryPolicy, CircuitBreakerPolicy, TimeoutPolicy

Node(
    name="external_api",
    handler="api_call",
    retry_policy=RetryPolicy(
        retries=5,
        backoff_seconds=1.0,
        backoff_multiplier=2.0,  # 1s → 2s → 4s → 8s → 16s
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

| Component | What it does |
|---|---|
| `AFMXEngine` | SEQUENTIAL · PARALLEL · HYBRID · DIAGONAL orchestration |
| `CognitiveModelRouter` | Auto model-tier routing by cognitive layer |
| `NodeExecutor` | Per-node retry + timeout + circuit breaker |
| `HandlerRegistry` | Key → callable registry, dotted-path resolution |
| `HookRegistry` | PRE/POST matrix and node hooks |
| `EventBus` | Typed async events — every state transition |
| `ConcurrencyManager` | Global semaphore + queue timeout |
| `StateStore` | In-memory or Redis execution persistence |
| `CheckpointStore` | Per-node checkpoints for resumability |
| `AuditStore` | Append-only audit trail, JSON/CSV/NDJSON export |
| `RBACMiddleware` | 5 roles × 16 permissions, API key auth |

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/afmx/execute` | Execute synchronously |
| `POST` | `/afmx/execute/async` | Fire-and-forget, returns `execution_id` |
| `GET` | `/afmx/result/{id}` | Full result with node outputs |
| `GET` | `/afmx/status/{id}` | Status-only poll |
| `POST` | `/afmx/validate` | Validate matrix without executing |
| `POST` | `/afmx/retry/{id}` | Retry failed execution |
| `POST` | `/afmx/resume/{id}` | Resume from last checkpoint |
| `POST` | `/afmx/cancel/{id}` | Cancel running execution |
| `GET` | `/afmx/matrix-view/{id}` | 2D heatmap: layer × role × status × model tier |
| `GET` | `/afmx/domains` | List all domain packs |
| `GET` | `/afmx/domains/{name}` | Get a domain pack by name |
| `GET` | `/afmx/audit` | Query audit log |
| `WS` | `/afmx/ws/stream/{id}` | Real-time event streaming |
| `GET` | `/health` | Health + concurrency stats |
| `GET` | `/metrics` | Prometheus metrics |

---

## Dashboard

```bash
cd afmx/dashboard
npm install && npm run build   # → served at /afmx/ui
npm run dev                    # hot-reload at localhost:5173
```

Pages: **Overview** · **Executions** · **Live Stream** · **Run Matrix** · **Cognitive Matrix** · **Domain Packs** · **Saved Matrices** · **Plugins** · **Audit Log** · **API Keys**

---

## vs Alternatives (March 2026)

| | **AFMX 1.3** | LangGraph 1.0 | OpenAI Agents SDK | CrewAI |
|---|---|---|---|---|
| Deterministic execution | ✅ | ❌ LLM-dependent | ❌ | ❌ |
| Per-node fault tolerance | ✅ Retry + CB + fallback | ❌ Manual | ⚠️ Basic | ❌ |
| Full audit trail | ✅ Append-only, exportable | ❌ | ⚠️ | ❌ |
| **Cognitive cost routing** | ✅ **60–90% cost reduction** | ❌ | ❌ | ❌ |
| Cross-industry domains | ✅ 5 built-in + custom | ❌ | ❌ | ❌ |
| MCP native | ✅ SSE + stdio | ❌ | ⚠️ | ❌ |
| Bedrock / SK / ADK | ✅ All three | ❌ | ❌ | ❌ |
| Execution resume | ✅ Checkpoint-based | ❌ | ❌ | ❌ |
| RBAC + multi-tenancy | ✅ | ❌ | ❌ | ❌ |
| TypeScript SDK | ✅ | ⚠️ | ⚠️ | ❌ |
| Human governance gate | ✅ RHFL integration | ❌ | ❌ | ❌ |

AFMX is the execution layer *underneath* your existing agents. LangGraph graphs, CrewAI crews, and OpenAI Assistants all run as AFMX nodes.

---

## Documentation

| Doc | Description |
|---|---|
| [Architecture](docs/architecture.md) | Layer diagram, request lifecycle, design decisions |
| [Core Concepts](docs/concepts.md) | Node, Edge, Matrix, Context, Record |
| [Quick Start](docs/quickstart.md) | 5-minute setup + 7 live demo scenarios |
| [Handlers](docs/handlers.md) | Writing and registering agent + tool handlers |
| [Adapters](docs/adapters.md) | MCP, LangChain, LangGraph, CrewAI, OpenAI, SK, ADK, Bedrock |
| [Integrations](docs/integrations.md) | HyperState, MAP, RHFL, Agentability |
| [Matrix Design](docs/matrix_design.md) | Execution modes, edge conditions, variable resolver |
| [Domains](docs/domains.md) | Domain packs, custom roles, cross-industry patterns |
| [API Reference](docs/api_reference.md) | All REST endpoints + schemas |
| [Hooks](docs/hooks.md) | PRE/POST hook patterns |
| [Observability](docs/observability.md) | EventBus, Prometheus, WebSocket, Agentability |
| [Configuration](docs/configuration.md) | All `AFMX_` environment variables |
| [Testing](docs/testing.md) | Running the test suite |
| [Deployment](docs/deployment.md) | Docker, Oracle Cloud, production hardening |
| [TypeScript SDK](sdk/typescript/README.md) | `@agentdyne9/afmx` npm package |

---

## Testing

```bash
pytest                                       # 400+ tests
pytest tests/unit/ -v                        # unit only (no server)
pytest --cov=afmx --cov-report=html          # coverage report
python demo_multiagent.py --scenario all     # 7 live scenarios
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome.

All new `.py` files must include the Apache 2.0 header (see CONTRIBUTING.md for the exact block). Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Enterprise features (multi-tenancy, SSO/OIDC, cryptographic execution integrity, distributed workers, cost governance, AFMX Cloud) available under a separate commercial license. See [ENTERPRISE.md](ENTERPRISE.md) or contact **hello@agentdyne9.com**.
