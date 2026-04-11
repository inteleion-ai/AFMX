# AFMX — Product Roadmap
## March 31, 2026 → September 21, 2026

**Status:** Public roadmap. Updated monthly.
**Contact:** hello@agentdyne9.com

---

## Founder Preamble — Honest State of the World

Before writing a roadmap, I need to say what is actually true today.

**What we shipped and it is genuinely good:**
The core engine is production-grade. Deterministic topological execution, per-node retry + circuit breaker + fallback, async semaphore-based concurrency, full audit trail, RBAC, Redis-backed persistence, Agentability integration, and a real SPA dashboard. This is not vaporware. The code does what it says.

**What we claimed and it does not exist yet:**
The website says AFMX is "Built on the Temporal Cognitive Flow Programming (TCFP) model." It is not. TCFP is a separate system. The website says "Execution integrity verification." What we have is an audit trail — accountability, not cryptographic verification. These are not minor copy errors. They are promises to customers that the product cannot currently fulfill.

**What the market is doing right now (March 2026):**
OpenAI launched their Agents SDK in January 2026. It is gaining adoption fast because of the OpenAI brand, not because the execution model is better than ours — it is not. Anthropic's MCP (Model Context Protocol) is now the industry standard for tool connectivity. Every serious agent framework either supports it natively or is building support. LangGraph 1.0 is stable and has strong LangChain ecosystem lock-in. CrewAI is popular with less-technical teams. AutoGen v0.4 from Microsoft is mature. None of them have what we have: deterministic execution ordering, production-grade fault tolerance, or a real audit trail.

**Our sustainable competitive position:**
We win on infrastructure-grade reliability and compliance. Not on feature count, not on framework integrations, not on ease-of-use for demos. Our buyer is the engineering team that has been burned by a LangGraph prototype that worked in staging and failed silently in production. Our buyer is the enterprise that needs to prove to their legal team that every agent decision was logged, ordered, and recoverable. That is our wedge. Everything on this roadmap either deepens that wedge or closes a credibility gap.

**The one thing that would kill us:**
Shipping features the website promises before the core claims are true. If a prospect reads "execution integrity verification" on our website, runs a proof of concept, reads the source code, and finds we have a SQLite audit log with no tamper-evidence — we lose them permanently. Close the credibility gap first. Then grow.

---

## Market Context — March 2026

### What has changed in the last 90 days

**OpenAI Agents SDK (January 2026):** Real competition. Handoffs, tracing, guardrails built in. The DX is excellent. They do not have deterministic ordering, circuit breakers, per-node timeout enforcement, or fallback routing. Their fault tolerance story is "hope the model figures it out." But they have distribution, brand, and a native LLM runtime. We need to treat this seriously.

**MCP is now table stakes:** Anthropic's Model Context Protocol is the de facto standard for connecting agents to tools. Every enterprise evaluating agent infrastructure asks "does it support MCP?" If the answer is no, you are off the shortlist. We do not have a native MCP adapter yet.

**Enterprise procurement reality:** Enterprises evaluating agent infrastructure in Q1 2026 are asking for: multi-tenancy (one deployment, many teams), SOC2 alignment (audit trail, access control, data isolation), cost governance (token spend controls, per-team quotas), and execution replay/resume (incident recovery). We have pieces of all of these. We do not have any of them fully.

**The "agentic" market has split into two layers:**
1. Reasoning/orchestration frameworks — LangGraph, CrewAI, AutoGen, Pydantic AI. These handle LLM calls and agent logic.
2. Execution fabrics — Temporal (general workflows), AFMX (agent-specific). These handle reliability, ordering, and observability.

We are in layer 2 and that is correct. The danger is letting layer 1 players absorb our layer by adding basic retry and logging. We need to make our layer so deep that it is not worth their time to replicate.

### Who is buying agent infrastructure right now

**Profile A — Enterprise AI platform team.** 20–200 engineers. Building internal agent systems for customer service, code review, document processing, financial analysis. They have been burned by LLM unpredictability. They care deeply about auditability, rollback, and multi-team isolation. They will pay for this. Typical contract: $50K–$500K/year. Our product is close but not there on multi-tenancy and SOC2.

**Profile B — AI-native startup engineering team.** 5–30 engineers. Building a product that uses agents as a core feature. They care about DX, TypeScript support, and reliability under scale. They will adopt open-source and pay for cloud/enterprise features later. The TypeScript SDK gap is blocking us here.

**Profile C — Systems integrators.** Building agent infrastructure for their clients. They need adapters for every major framework (OpenAI Agents SDK, LangGraph, MCP), solid documentation, and a license that supports resale. This is a multiplier channel.

---

## Honest Gap Analysis — Current Codebase vs. Market Needs

| Capability | Current State | Market Need | Priority |
|---|---|---|---|
| Deterministic execution ordering | ✅ Shipped, production quality | Must-have | Maintain |
| Per-node retry + circuit breaker | ✅ Shipped, production quality | Must-have | Maintain |
| Audit trail + RBAC | ✅ Shipped, solid | Must-have for enterprise | Harden |
| Agentability integration | ✅ Shipped, working | Differentiator | Grow |
| **Execution resume from checkpoint** | ⚠️ Checkpoints saved, **no resume API or UI** | Must-have for production | **v1.1** |
| **Streaming node output** | ❌ Nodes return complete JSON only | Developer expectation | **v1.1** |
| **MCP adapter** | ❌ Not built | Table stakes March 2026 | **v1.1** |
| **OpenAI Agents SDK adapter** | ❌ Not built | Fast-growing ecosystem | **v1.2** |
| **TypeScript SDK** | ❌ Not built | Blocking Profile B entirely | **v1.2** |
| **TCFP integration** | ❌ Claimed on website, does not exist | Credibility | **v1.2** |
| **Scheduled execution (cron)** | ❌ Not built | Common enterprise need | **v1.3** |
| **Multi-tenancy data isolation** | ⚠️ RBAC exists, data not isolated per tenant | Enterprise requirement | **v1.3** |
| **Execution replay / dry-run** | ❌ Not built | Debugging, compliance | **v1.3** |
| **Live DAG visualisation** | ❌ Dashboard shows trace, not graph | Developer delight | **v1.4** |
| **Distributed worker pool** | ❌ Single-server only | Scale requirement | **v1.4** |
| **Cost governance** | ❌ No token/cost budget per matrix | Enterprise requirement | **v1.4** |
| **Cryptographic execution integrity** | ❌ Audit trail exists but not tamper-evident | Website claim | **v1.5** |
| **gRPC / streaming transport** | ❌ REST + WebSocket only | Performance at scale | **v2.0** |
| **SaaS cloud offering** | ❌ Self-hosted only | Revenue | **v2.0** |

---

## Six-Month Plan — Release Schedule

```
March 21   →   April 30     v1.1  — Resume + Stream + MCP
May 1      →   May 31       v1.2  — OpenAI SDK + TypeScript alpha + TCFP bridge
June 1     →   June 30      v1.3  — Scheduler + Multi-tenancy + Replay
July 1     →   July 31      v1.4  — Distributed + Live DAG + Cost governance
August 1   →   August 31    v1.5  — Integrity + Enterprise hardening
September 1→   September 21  v2.0  — Platform + Cloud alpha
```

---

## v1.1 — Execution Resume + Streaming + MCP
**Target: April 30, 2026**

### Why this release matters

The checkpoint infrastructure already exists in `afmx/store/checkpoint.py`. `RedisCheckpointStore.update_node_complete()` is called after every successful node. The data is there. What does not exist is a way to use it. If AFMX crashes mid-execution with 15 of 20 nodes complete, all 20 run again on the next attempt. For long-running multi-agent workflows with expensive LLM calls, this is not acceptable. This is the most impactful thing we can ship in the shortest time because 70% of the infrastructure already exists.

MCP is not optional in April 2026. It is the connective tissue of the agent ecosystem. Not having it means losing every evaluation where the customer's tools are MCP servers.

### Features

**1. Execution Resume API**

New endpoint: `POST /afmx/resume/{execution_id}`

When called on a FAILED or TIMEOUT execution:
1. Loads the checkpoint from `CheckpointStore`
2. Rebuilds `ExecutionContext` from checkpoint data (`apply_to_context()`)
3. Reconstructs `node_results` for already-completed nodes
4. Re-runs the matrix starting from the first incomplete node
5. Records a new `ExecutionRecord` linked to the original via `resumed_from` field

The resume is not a retry (which re-runs the whole matrix). It is a continuation from the last successful checkpoint. This distinction matters for billing, debugging, and compliance.

```python
# New field on ExecutionRecord
resumed_from: Optional[str] = None   # execution_id of the original run

# New endpoint
POST /afmx/resume/{execution_id}
→ {"new_execution_id": "...", "resumed_from": "...", "skipped_nodes": ["n1","n2","n3"]}
```

Dashboard change: Executions page shows a "Resume" button on FAILED/TIMEOUT rows alongside the existing "Retry" button. Resumed executions show a chain icon linking back to the original.

**2. Node-Level Streaming Output**

Currently nodes return a complete JSON dict. For long-running LLM calls, the user sees nothing for 30 seconds then gets the full response. This is bad DX.

New mechanism: handlers can yield partial results via an async generator protocol.

```python
# Streaming handler — yields partial results
async def streaming_analyst(node_input, context, node):
    async for chunk in llm_stream(node_input["input"]):
        yield {"partial": chunk}    # streamed to WebSocket clients
    yield {"final": "complete result", "confidence": 0.87}  # stored in NodeResult.output
```

`NodeExecutor` detects `async_generator` and:
- Streams each `yield` to the execution's WebSocket queue as `{"type": "node.stream", "node_id": "...", "chunk": {...}}`
- Stores only the final `yield` value in `NodeResult.output`
- Falls back to existing behaviour if the handler is a regular coroutine

Dashboard: Live Stream page shows streaming chunks in real-time with a scrolling chunk display per node.

**3. MCP (Model Context Protocol) Adapter**

`afmx/adapters/mcp.py` — wraps any MCP server as an AFMX TOOL node.

```python
from afmx.adapters.mcp import MCPAdapter

adapter = MCPAdapter()

# From an MCP server URL
node = adapter.from_server(
    server_url="http://localhost:3000",
    tool_name="search",
    node_id="mcp-search",
    retry_policy=RetryPolicy(retries=3),
)

# From an MCP server config dict (Claude Desktop / Cursor format)
node = adapter.from_config({
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-filesystem"],
})
```

The MCP adapter:
- Speaks the MCP JSON-RPC protocol (tools/call, tools/list)
- Auto-discovers available tools from a server via `tools/list`
- Maps each MCP tool to an AFMX TOOL node with schema validation
- Handles SSE and HTTP transports
- Supports the Claude Desktop `mcpServers` config format directly

This gives AFMX instant access to every MCP server in the ecosystem — filesystem, web search, GitHub, Slack, Notion, Linear, databases — without writing a single adapter per tool.

**4. Dashboard: Execution Resume + Stream UI**

- Resume button on FAILED/TIMEOUT executions in the list and detail modal
- Chain indicator showing `resumed_from` relationship
- Live Stream page: per-node streaming chunk display with auto-scroll
- Stream type filter: `node.stream` events distinguished from lifecycle events

### Quality bar for v1.1 release

- Resume: integration test covering crash-mid-execution + resume from checkpoint
- MCP: integration test against a real MCP server (filesystem server from Anthropic)
- Streaming: unit test for generator detection, integration test for WS delivery
- All existing 290+ tests still pass

---

## v1.2 — OpenAI Agents SDK + TypeScript SDK Alpha + TCFP Bridge
**Target: May 31, 2026**

### Why this release matters

OpenAI's Agents SDK is the fastest-growing agent framework right now. Not having an adapter is a sales blocker for every customer who is already using it. This is a market capture move.

The TypeScript SDK is a developer acquisition move. Right now AFMX is Python-only. The majority of web-native AI applications are TypeScript. Every Profile B company (AI-native startups) is using TypeScript. Without it, we are invisible to half the market.

TCFP closes the credibility gap. The website makes this claim. We need to make it true or change the website. Making it true is better.

### Features

**1. OpenAI Agents SDK Adapter**

`afmx/adapters/openai_agents.py` — wraps OpenAI's Agent, Tool, and Handoff objects.

```python
from afmx.adapters.openai_agents import OpenAIAgentsAdapter
from openai import OpenAI
from agents import Agent, Tool

client = OpenAI()
adapter = OpenAIAgentsAdapter(client=client)

# Wrap an OpenAI Agent as an AFMX AGENT node
agent = Agent(
    name="Research Assistant",
    instructions="You are a research assistant...",
    tools=[search_tool, summarize_tool],
)
node = adapter.agent_node(agent, node_id="research", timeout_policy=TimeoutPolicy(120.0))

# Wrap an OpenAI Handoff as a conditional AFMX edge
# Handoff routing logic → AFMX EXPRESSION edge condition
```

The adapter handles:
- Agent run lifecycle (create thread, add message, poll run, extract response)
- Tool call execution within the OpenAI runtime (tools still call back to AFMX handlers)
- Handoff translation to AFMX conditional edges with `ON_OUTPUT` conditions
- Streaming run output via the streaming node protocol from v1.1

This means a customer can take an existing OpenAI Agents application and wrap it in AFMX for fault tolerance, audit trail, and observability — without rewriting any agent logic.

**2. TypeScript SDK (Alpha)**

`sdk/typescript/` — parallel to Agentability's planned TypeScript SDK.

The TypeScript SDK is a **client SDK only** — it does not re-implement the engine in TypeScript. The engine stays Python. The TS SDK talks to the AFMX REST API.

```typescript
import { AFMXClient, ExecutionMatrix, ExecutionMode } from '@agentdyne9/afmx'

const client = new AFMXClient({
  baseUrl: 'http://localhost:8100',
  apiKey: 'afmx_key_...',
})

// Execute a matrix
const result = await client.execute({
  matrix: {
    name: 'research-pipeline',
    mode: ExecutionMode.Sequential,
    nodes: [
      { id: 'analyst', name: 'analyst', type: 'AGENT', handler: 'analyst_agent' },
      { id: 'writer',  name: 'writer',  type: 'AGENT', handler: 'writer_agent'  },
    ],
    edges: [{ from: 'analyst', to: 'writer' }],
  },
  input: { topic: 'AI infrastructure in 2026' },
})

// Stream events
const stream = client.stream(result.execution_id)
for await (const event of stream) {
  if (event.type === 'node.completed') console.log(event.data)
}
```

Full TypeScript types generated from the OpenAPI spec. The SDK is published to npm as `@agentdyne9/afmx`.

Alpha scope: execute, execute_async, status, result, stream (WebSocket). Full API parity in v1.3.

**3. TCFP Bridge**

This closes the most important credibility gap. TCFP (Temporal Cognitive Flow Programming) is a separate Agentdyne9 system that defines reasoning modes and cognitive flow strategies. AFMX needs to be able to receive execution plans from TCFP and execute them deterministically.

`afmx/integrations/tcfp.py` — the bridge.

The bridge defines a protocol:

```python
from afmx.integrations.tcfp import TCFPBridge, TCFPPlan

bridge = TCFPBridge(afmx_engine=engine)

# TCFP produces a plan (a structured reasoning trace with execution steps)
# The bridge translates it to an AFMX ExecutionMatrix and executes it
result = await bridge.execute_plan(
    plan=TCFPPlan(
        flow_id="tcfp_plan_abc123",
        cognitive_mode="analytical",
        steps=[...],        # TCFP step definitions
        variables={...},
    ),
    input={"query": "..."},
)
```

The `TCFPPlan` → `ExecutionMatrix` translation:
- Each TCFP step → AFMX Node
- TCFP step dependencies → AFMX Edges
- TCFP cognitive_mode → AFMX ExecutionMode (analytical → SEQUENTIAL, parallel_synthesis → HYBRID)
- TCFP flow_id → stored in ExecutionRecord.metadata for lineage tracking

This makes the website claim true: AFMX is the execution layer for TCFP plans. TCFP decides what to do. AFMX executes it deterministically and records it.

New endpoint: `POST /afmx/tcfp/execute` accepts a raw TCFP plan and returns an execution result.

Health endpoint now shows `tcfp_bridge: {enabled: true/false}`.

**4. Python SDK packaging**

Currently AFMX is installed as `pip install -e .` from source. We need a proper PyPI-published package.

- `pip install afmx` installs the server + SDK
- `pip install afmx-sdk` installs only the SDK (no server, no FastAPI, minimal deps) — for embedding AFMX engine in existing apps
- Versioned releases with GitHub Actions publishing on tag

---

## v1.3 — Scheduler + Multi-Tenancy + Execution Replay
**Target: June 30, 2026**

### Why this release matters

Scheduled execution is the most requested feature from enterprise prospects. "Can we run this matrix every hour?" and "Can we trigger this when a file arrives?" are questions we get asked in every sales call. Right now the answer is "use a cron job to call our API." That is not acceptable for a production infrastructure product.

Multi-tenancy is what separates a tool from a platform. Right now all executions, matrices, audit logs, and API keys live in one flat namespace. A company with 10 teams cannot safely use AFMX without one team's data bleeding into another's. This blocks every enterprise deal where multiple teams share one deployment.

### Features

**1. Execution Scheduler**

`afmx/scheduler/` — a lightweight scheduler baked into AFMX. Not Airflow. Not Celery. A scheduler that understands AFMX matrices natively.

```python
# Register a scheduled matrix via API
POST /afmx/schedules
{
  "name": "nightly-research",
  "matrix_name": "research-pipeline",    // saved matrix
  "schedule": "0 2 * * *",              // cron expression
  "timezone": "Asia/Kolkata",
  "input": {"topic": "daily AI digest"},
  "enabled": true,
  "tags": ["scheduled", "nightly"]
}

# Or trigger-based — runs when a webhook arrives
POST /afmx/schedules
{
  "name": "on-document-upload",
  "matrix_name": "document-pipeline",
  "trigger": "webhook",                 // inbound webhook trigger
  "trigger_secret": "hmac-secret-here"
}
```

`GET /afmx/schedules` — list all schedules with last-run status
`GET /afmx/schedules/{name}/history` — execution history for a schedule
`POST /afmx/schedules/{name}/run-now` — trigger immediately outside schedule

The scheduler is backed by the existing MatrixStore and StateStore. No new database. The scheduler runs as an `asyncio` background task inside the existing FastAPI process. For multi-worker deployments, leader election uses a Redis lock to ensure only one worker runs the scheduler at a time.

Schedule types:
- **Cron** — standard 5-field cron expression with timezone support
- **Interval** — "every 30 minutes"
- **One-shot** — run once at a specific datetime
- **Webhook trigger** — run when `POST /afmx/webhooks/{name}` receives a signed request
- **EventBus trigger** — run when a specific `EventType` fires (e.g. run cleanup matrix after every EXECUTION_FAILED)

Dashboard: new Schedules page showing all schedules, next-run time, last-run status, and a Run Now button.

**2. Multi-Tenancy Data Isolation**

Currently `tenant_id` can be passed in `metadata` but all data lives in the same store. Tenant A can call `GET /afmx/executions` and see Tenant B's executions.

Implementation: every store operation gets a `tenant_id` prefix filter.

```python
# In AFMXSettings:
AFMX_MULTI_TENANCY_ENABLED=false   # default off
AFMX_TENANT_ISOLATION=strict       # strict | soft

# API key → tenant_id binding (already in APIKey model)
# All store queries now include tenant_id filter when enabled
```

When `AFMX_MULTI_TENANCY_ENABLED=true`:
- Every API request extracts `tenant_id` from the API key
- All `StateStore`, `MatrixStore`, `AuditStore` queries are prefixed with `tenant_id`
- `GET /afmx/executions` returns only executions for the caller's tenant
- ADMIN role can query cross-tenant with `?tenant_id=` query param
- Redis key prefix becomes `afmx:exec:{tenant_id}:` instead of `afmx:exec:`

This is the correct implementation for enterprise where Ops wants one deployment but Engineering, Finance, and Customer Success each have their own agent workflows and cannot see each other's data.

**3. Execution Replay / Dry-Run**

Two related capabilities:

**Dry-run mode:** Execute a matrix but do not call any handlers. Return the execution plan — which nodes would run in what order, with what inputs (template variables resolved). Used for debugging complex variable resolution and conditional routing without side effects.

```bash
POST /afmx/execute
{
  "matrix": {...},
  "input": {...},
  "dry_run": true      # new field
}
→ {
  "execution_plan": [
    {"node_id": "n1", "would_run": true,  "resolved_params": {...}},
    {"node_id": "n2", "would_run": true,  "resolved_params": {...}},
    {"node_id": "n3", "would_run": false, "skip_reason": "edge condition not met"}
  ]
}
```

**Execution replay:** Take a completed execution and replay it with modified input. Uses the original matrix definition (from MatrixStore) and runs against new input. Produces a new execution record linked to the original via `replayed_from`.

```bash
POST /afmx/replay/{execution_id}
{
  "input": {"topic": "modified input for replay"},
  "variables": {"depth": "shallow"}
}
```

Used for: incident investigation ("what would have happened if the input was different?"), regression testing ("does this matrix still produce the same result?"), customer demos.

**4. TypeScript SDK — Full API parity**

Complete the TypeScript SDK from alpha to full feature parity with the Python SDK:
- All execution endpoints
- Matrix CRUD
- Schedule management
- Streaming (full WebSocket protocol)
- RBAC key management
- Type-safe matrix builder with validation

---

## v1.4 — Distributed Workers + Live DAG + Cost Governance
**Target: July 31, 2026**

### Why this release matters

Single-server AFMX is limited by the asyncio event loop of one Python process. For heavy multi-agent workloads (hundreds of concurrent executions, nodes that take minutes), we need horizontal scaling at the node execution level — not just at the API level.

The live DAG visualisation is the demo feature that closes sales. When you can show a prospect their 15-agent workflow executing in real-time with nodes lighting up as they complete, that is more convincing than any benchmark.

Cost governance is the CFO feature. Every enterprise AI deployment now has a "who approved this $40,000 GPT-4o bill" conversation. AFMX is positioned to answer that question because we sit between the agents and the handlers.

### Features

**1. Distributed Worker Pool**

`afmx/workers/` — a worker process architecture for distributing node execution across machines.

Architecture:
```
API Server (FastAPI)
    │ publishes NodeExecution tasks
    ▼
Redis Task Queue (LPUSH/BRPOP)
    │
    ├── Worker 1 (Python process)
    ├── Worker 2 (Python process)
    └── Worker N (Python process, different machine OK)
```

The API server orchestrates (graph logic, skip/retry decisions, result aggregation) and workers execute (call the handler function). This separation means:
- Handlers can be CPU-intensive — workers run in separate processes, no GIL contention
- Workers can run on different machines — horizontal scale
- Worker crashes do not kill the API server
- The engine's topological logic stays in the API server — only leaf execution is distributed

Worker process: `afmx worker --concurrency 20 --queues default,high-priority`

API changes: `GET /afmx/workers` — list connected workers and their load.

Backwards compatible: when no workers are connected, AFMX falls back to in-process execution (current behaviour). Zero configuration change for existing deployments.

**2. Live DAG Visualisation**

The dashboard's most impactful feature. A real-time D3-based execution graph that shows the matrix topology and animates node state transitions.

```
  [analyst] ──────► [writer] ──────► [reviewer]
    RUNNING           QUEUED            QUEUED

  ↓ 500ms later

  [analyst] ──────► [writer] ──────► [reviewer]
  COMPLETED          RUNNING           QUEUED
```

Implementation:
- D3.js force-directed graph (dagre-d3 for DAG layout)
- Nodes colour-coded by status (green=SUCCESS, red=FAILED, amber=RUNNING, grey=QUEUED/SKIPPED)
- Edge animations showing data flow
- Click any node to see real-time output streaming (from v1.1 streaming protocol)
- WebSocket-driven — reuses the existing stream endpoint

New page in dashboard: **Execution Graph** — accessible from the Executions detail modal (4th tab alongside Trace/Waterfall/Output).

For saved matrices: the Matrix Design view shows the static DAG before execution, then switches to live view when an execution starts.

**3. Cost Governance**

AFMX sits between agents and handlers. It can intercept LLM calls and enforce budgets.

```python
# Matrix-level cost budget
matrix = ExecutionMatrix(
    name="research-pipeline",
    cost_policy=CostPolicy(
        max_cost_usd=5.00,             # abort if execution would exceed $5
        max_tokens=100_000,            # abort if total tokens exceed limit
        per_node_max_cost_usd=1.00,    # per-node budget
        action_on_breach="ABORT",      # ABORT | WARN | LOG
        notify_webhook=True,           # POST to AFMX_WEBHOOK_URL
    ),
)
```

How it works:
- Handlers that return `_llm_meta` (our `realistic_handlers.py` pattern) report cost
- The POST_NODE hook accumulates cost on `ExecutionContext.metadata["__cost_tracker__"]`
- When cumulative cost exceeds the budget, the engine calls `record.mark_aborted("Cost budget exceeded")`
- `GET /afmx/executions` response includes `total_cost_usd` and `total_tokens` fields
- Dashboard Overview page shows cost trend chart

Admin cost dashboard: `GET /afmx/admin/cost-report?from=...&to=...&group_by=matrix_name|tenant_id|tag`

This answers the CFO's question. It also makes AFMX sticky — once cost governance is wired into a budget approval workflow, it is very hard to rip out.

---

## v1.5 — Execution Integrity + Enterprise Hardening
**Target: August 31, 2026**

### Why this release matters

This is the release that closes the credibility gap on the biggest website claim. "Execution integrity verification" needs to mean something real. In August 2026, with enterprise deals on the line, we need to be able to tell a customer's legal team that the execution records are tamper-evident.

This is also the hardening release. Everything from v1.1 to v1.4 gets battle-tested, edge cases closed, performance profiled, and the overall system stress-tested under production load.

### Features

**1. Cryptographic Execution Integrity**

Each `ExecutionRecord` gets a cryptographic hash chain:

```python
# On ExecutionRecord completion:
record.integrity_hash = sha256(
    record.execution_id +
    record.matrix_id +
    record.status +
    json.dumps(record.node_results, sort_keys=True) +
    str(record.started_at) +
    str(record.finished_at) +
    previous_record_hash    # chain to previous execution
)
record.integrity_version = "1"
```

`GET /afmx/result/{id}` includes `integrity_hash` and `integrity_version`.

`POST /afmx/verify/{execution_id}` — verifies the hash against current record content. Returns `{"valid": true}` or `{"valid": false, "tampered_fields": [...]}`.

The audit log gets HMAC-signed entries: each `AuditEvent` includes an HMAC-SHA256 signature using a server-side signing key (`AFMX_AUDIT_SIGNING_KEY`). The signing key is never stored in the database. Verification requires the key — meaning you cannot silently modify audit records without breaking the chain.

This makes "Execution integrity verification" an accurate claim. It is now cryptographically verifiable, not just observable.

**2. SOC2-Aligned Audit Hardening**

Additions to bring the audit trail into SOC2 alignment:
- `AuditEvent.actor_ip` — IP address of every operation
- `AuditEvent.user_agent` — client identifier
- `AuditEvent.request_id` — correlation ID from `X-Request-ID` header
- Non-destructive API keys — revoked keys are marked not deleted (audit history preserved)
- `GET /afmx/audit/export/soc2` — pre-formatted SOC2 audit report for a time range
- Configurable audit retention (default: 1 year) with automatic archival to S3/GCS

**3. OpenTelemetry (OTEL) Export**

`afmx/observability/otel.py` — OTEL trace exporter.

Every execution becomes an OTEL trace. Every node becomes a span. Retry attempts, circuit breaker events, hook execution — all become OTEL span events.

```bash
AFMX_OTEL_ENABLED=true
AFMX_OTEL_ENDPOINT=http://otel-collector:4317
AFMX_OTEL_SERVICE_NAME=afmx-production
```

This means AFMX plugs natively into Datadog, Honeycomb, Grafana Tempo, AWS X-Ray, Jaeger — whatever the customer already has. We stop being a silo.

**4. Performance Hardening**

Real-world production load testing and optimisation:

- `GET /afmx/executions` with 100K records: add pagination cursor (current uses offset, bad at scale)
- WebSocket connection leak prevention: idle connection cleanup, max-connections-per-execution cap
- Redis pipeline batching for bulk node result writes
- `HandlerRegistry.resolve()` LRU cache for dotted module path resolution (currently re-imports on every cold-start)
- Async context manager pool for the `CheckpointStore` to avoid lock contention under high parallelism

Target: 500 concurrent executions, each with 20 nodes, on a 4-core/16GB server with Redis backend, sustaining < 5ms overhead per node lifecycle event.

---

## v2.0 — Platform + Cloud Alpha
**Target: September 21, 2026**

### Why this release matters

v2.0 is the business model pivot from open-source tool to platform. Open-source stays open. The cloud offering is the revenue engine.

### Features

**1. AFMX Cloud (Alpha)**

Managed AFMX as a service. No infrastructure to run.

```
https://api.afmx.io/execute
X-AFMX-API-Key: afmx_cloud_key_...
```

The cloud offering:
- Multi-region (US-West, EU-West, AP-South) — first three regions
- Automatic scaling — no concurrency cap to configure
- Built-in Redis (no self-hosted Redis needed)
- Managed Agentability observability — free tier included
- Web-based dashboard at `app.afmx.io`
- Usage-based pricing: $0.001 per node execution + $10/seat/month for dashboard access

Free tier: 10,000 node executions/month, 1 team, no SLA. Converts to paid at scale.

**2. Execution Marketplace**

`afmx.io/matrices` — a public registry of reusable matrix templates.

Teams can publish their matrices (if they choose) and others can import them:

```bash
afmx pull research-pipeline@community/agentdyne9
afmx push my-pipeline --public
```

This is the ecosystem play. Every published matrix is an advertisement for AFMX. Every popular template creates adoption.

**3. Python SDK v2 — Type-Safe Matrix Builder**

```python
from afmx.builder import MatrixBuilder

matrix = (
    MatrixBuilder("research-pipeline")
    .mode("HYBRID")
    .abort("CONTINUE")
    .node("analyst",  type="AGENT", handler="analyst_agent", timeout=60)
    .node("writer",   type="AGENT", handler="writer_agent",  timeout=60)
    .node("reviewer", type="AGENT", handler="reviewer_agent",timeout=30)
    .edge("analyst", "writer")
    .edge("writer",  "reviewer")
    .on_failure("analyst", fallback="backup_analyst")
    .cost_policy(max_usd=5.00)
    .build()
)
```

Fluent builder API with full type safety and validation. Replaces raw dict construction for users who prefer Python over JSON.

---

## What We Are NOT Building in the Next 6 Months

Being explicit about this is as important as the roadmap itself.

**Not building a reasoning engine.** AFMX does not plan, does not call LLMs in the core loop, does not decide what the next node should be based on agent output. That is TCFP's job. We execute TCFP plans. We do not replicate TCFP.

**Not building a memory system.** `ExecutionContext.memory` is a runtime scratchpad, not a long-term memory system. Long-term memory is HyperState. We integrate with it; we do not build it.

**Not building a new LLM abstraction layer.** We adapt to existing frameworks (LangChain, CrewAI, OpenAI Agents SDK, MCP) via adapters. We do not build a new way to call LLMs.

**Not building a no-code / low-code interface.** The matrix JSON format and Python SDK are the interfaces. A drag-and-drop graph builder would be useful but it is not the product for the next 6 months. The live DAG visualisation (v1.4) is a viewing tool, not an editing tool.

**Not pivoting to a general workflow engine.** Temporal handles general durable workflows. We are agent-specific. The moment we start supporting database migrations, email sending, and file processing as first-class primitives, we lose our identity.

---

## Success Metrics — 6 Months

| Metric | Today (March 21, 2026) | Target (Sept 21, 2026) |
|---|---|---|
| Website claims that are true | 2/4 | 4/4 |
| GitHub stars | baseline | 500+ |
| PyPI monthly downloads | baseline | 10,000+ |
| npm monthly downloads (`@agentdyne9/afmx`) | 0 (not published) | 2,000+ |
| Enterprise prospects in pipeline | — | 10+ |
| Paid enterprise contracts | 0 | 2+ |
| Cloud alpha users | 0 | 50+ |
| Test coverage | 70% (enforced floor) | 85% |
| Documented MCP integrations | 0 | 10+ |
| Documented OpenAI Agents SDK integrations | 0 | 5+ |
| `POST /afmx/verify/{id}` returns `valid: true` | N/A (not built) | Working |
| p99 latency per node lifecycle event (500 concurrent) | Unknown | < 5ms |

---

## Resourcing Reality

This roadmap assumes a small, focused team. The six releases in six months are achievable with 2–3 backend engineers, 1 frontend engineer, and 1 person managing docs, comms, and customer conversations.

The highest-risk items are:

**Distributed workers (v1.4):** This is architecturally the largest change. The risk is introducing distributed state bugs that break the core determinism guarantee — which is our entire value proposition. It must be built behind a feature flag and disabled by default until it has been load-tested to destruction.

**AFMX Cloud (v2.0):** Cloud infrastructure, billing, multi-tenancy, and SLA are each month-long projects on their own. The alpha target is an internal hosted version that 50 friendly users can poke at. It is not a GA launch.

**TypeScript SDK (v1.2 alpha → v1.3 full):** TypeScript SDK development is parallel work that cannot be done by the same engineer as the Python backend. It needs dedicated ownership.

---

## Immediate Actions — Next 30 Days

These need to start today:

1. **Fix the website copy.** Change "Built on the TCFP model" to "Designed to execute TCFP plans" until v1.2 ships the bridge. Change "Execution integrity verification" to "Full execution audit trail" until v1.5 ships cryptographic hashing. Every day the false claims are live, they are a liability.

2. **Publish to PyPI.** Run `python -m build && twine upload dist/*`. Version 1.0.1 needs to be installable with `pip install afmx`. Every doc currently says `pip install -e .` which only works from source. This is the single biggest barrier to adoption.

3. **Open the GitHub repository.** The code is good. It should be public. Stars, forks, issues, and PRs are free marketing and user research. Keep the cloud offering closed-source when it arrives.

4. **Start the MCP adapter.** This is the fastest path to "yes" in an evaluation. Read the MCP spec (it is clean), build the adapter, write a blog post: "Connecting any MCP tool to AFMX in 5 minutes." Publish by April 15.

5. **Wire the resume endpoint to the existing checkpoint infrastructure.** The data is already being written. The resume logic is 150 lines of Python. This should ship in two weeks.

6. **Set up the GitHub Actions publishing pipeline.** Tag → build → publish to PyPI and npm. This takes one day to set up and unblocks everything else.

---

## Closing Note

The core engine we have built is genuinely differentiated. Deterministic execution, per-node fault tolerance at the infrastructure level, full audit trail — nobody else has all three in a clean, hackable Python package. The risk is not that someone builds something better. The risk is that we let the credibility gap grow wider, that we stay invisible on PyPI and npm, and that a well-funded competitor catches up while we are still running from source.

The next six months are about closing the gap between what the engine can do and what the world knows it can do. Ship v1.1 fast. Get on PyPI. Open the repo. Build the MCP adapter. Then execute the rest of the roadmap with discipline.

The engine is ready. The question is whether we are.
