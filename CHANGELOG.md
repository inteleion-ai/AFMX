# AFMX Changelog

All notable changes are documented here.

---

## [1.3.0] — 2026-03-31 — Enterprise Adapters + Platform Integrations

### Summary

Major expansion of the adapter ecosystem and first-party platform integrations.
No breaking changes. Full backward compatibility with v1.2.x.

### New — Adapters

- **`afmx/adapters/semantic_kernel.py`** — Microsoft Semantic Kernel adapter.
  Wraps `KernelFunction` objects (prompt functions, native functions) as AFMX
  nodes. `function_node()` wraps a single function; `plugin_nodes()` wraps all
  functions in an SK plugin. CognitiveLayer inferred from function name.
  Install: `pip install afmx[semantic-kernel]`

- **`afmx/adapters/google_adk.py`** — Google ADK adapter (launched March 2026).
  Wraps `BaseTool`, `LlmAgent`, `SequentialAgent`, `ParallelAgent` as AFMX
  nodes. Full ADK `Runner` session execution. `SequentialAgent`/`ParallelAgent`
  auto-map to `PLAN` layer. Install: `pip install afmx[google-adk]`

- **`afmx/adapters/bedrock.py`** — Amazon Bedrock adapter.
  `agent_node()` invokes Bedrock Agents via `bedrock-agent-runtime`.
  `model_node()` invokes any model via `invoke_model` with provider-specific
  request/response handling (Claude/Llama/Titan/Mistral/Cohere).
  Haiku/Lite models auto-mapped to RETRIEVE; Opus/Sonnet to REASON.
  Install: `pip install afmx[bedrock]`

### New — Platform Integrations

- **`afmx/integrations/hyperstate.py`** — HyperState cognitive memory.
  3 modes: handler registration (`hyperstate:retrieve`, `hyperstate:store`),
  PRE_NODE memory injection for RETRIEVE layers, POST_NODE output persistence
  for REASON/PLAN/EVALUATE layers.
  Install: `pip install afmx[hyperstate]`

- **`afmx/integrations/map_plugin.py`** — MAP (Memory Augmentation Platform).
  `map:retrieve` handler returns SHA-256 verified, provenanced `ContextUnit[]`.
  `map:verify` checks integrity of a specific context unit.
  PRE_NODE hook injects deterministic context into RETRIEVE nodes.
  Install: `pip install afmx[map]`

- **`afmx/integrations/rhfl.py`** — RHFL governance gate.
  Intercepts all ACT-layer nodes via PRE_NODE hook. Submits to RHFL REST API.
  AUTO → proceed; REVIEW → poll for approval; BLOCK → `RHFLBlockedError`;
  ESCALATE → wait with escalation context. `RHFLTimeoutError` on max_wait exceeded.
  No additional install needed (httpx is already a core dep).

### New — TypeScript SDK

- **`sdk/typescript/src/index.ts`** — `@agentdyne9/afmx` npm package.
  Type-safe client: `execute`, `executeAsync`, `pollUntilDone`, `matrixView`,
  `listDomains`, `cancel`, `retry`, `resume`. `buildNode()` and `buildEdge()`
  helpers. Full enum exports: `CognitiveLayer`, `ExecutionMode`, `NodeType`.
  Zero dependencies beyond `fetch` (native in Node 18+).

### Changed

- `afmx/adapters/__init__.py` — exports `SemanticKernelAdapter`, `GoogleADKAdapter`,
  `BedrockAdapter`. Docstring updated with enterprise adapter quick-start.
- `afmx/adapters/registry.py` — `_BUILTIN_SPECS` extended with 3 new adapters.
  Added `_requires_init_args()` guard to skip auto-instantiation of adapters
  that require constructor arguments (SK, Bedrock, ADK).
- `afmx/integrations/__init__.py` — updated docstring listing all 4 integrations.
- `afmx/__init__.py` — exports `SemanticKernelAdapter`, `GoogleADKAdapter`,
  `BedrockAdapter`. Version: `1.3.0`.
- `pyproject.toml` — version `1.3.0`; new optional deps: `semantic-kernel`,
  `google-adk`, `bedrock`, `hyperstate`, `map`, `rhfl`.
- `README.md` — cost routing story moved to top. Badge updated to 1.3.0.

### Tests

- `tests/unit/test_v130_adapters_integrations.py` — 60+ tests:
  SemanticKernelAdapter (function/plugin node, layer inference, missing SDK).
  GoogleADKAdapter (tool/agent node, SequentialAgent → PLAN, to_afmx_node routing).
  BedrockAdapter (model/agent node, provider bodies, response extraction).
  HyperState integration (handler registration, empty query).
  MAP integration (handler registration, missing SDK).
  RHFL integration (BLOCK/AUTO/TIMEOUT scenarios, token guard).
  AdapterRegistry (`_requires_init_args`, register/deregister/decorator).

### Examples

- `examples/11_hyperstate_map.py` — HyperState RETRIEVE → REASON flow + MAP verified context.
- `examples/12_rhfl_gate.py`     — AUTO and BLOCK governance scenarios.
- `examples/13_enterprise_adapters.py` — SK, Google ADK, Bedrock with mock objects.

---

## [1.2.1] — 2026-03-22 — MCP Adapter + Ad-hoc Resume + Layer Events

### Summary

Three targeted fixes and one major new adapter shipped together. No breaking
changes. All v1.2.0 code is fully backward-compatible.

### New — `afmx/adapters/mcp.py` — Model Context Protocol Adapter

First-class MCP support. Every MCP server tool becomes an AFMX `NodeType.MCP`
node — with automatic `CognitiveLayer` inference, retry, circuit breaker, and
full audit trail — with zero per-tool boilerplate.

**Public API:**

```python
from afmx.adapters.mcp import MCPAdapter, MCPServerConfig, infer_cognitive_layer

adapter = MCPAdapter()

# SSE transport (remote HTTP server)
nodes = await adapter.from_server("http://localhost:3000")

# stdio transport (local subprocess)
nodes = await adapter.from_config({
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-filesystem", "/"],
})

# Claude Desktop / Cursor config format
nodes = await adapter.from_desktop_config({
    "mcpServers": {
        "filesystem": {"command": "npx", "args": ["..."]},
        "github":     {"command": "npx", "args": ["..."]},
    }
})
```

**CognitiveLayer inference** — automatic from tool name + description:

| Layer    | Trigger keywords (name or description) |
|----------|----------------------------------------|
| RETRIEVE | search, fetch, read, get, list, query, find, lookup, load, browse |
| ACT      | write, create, update, delete, send, post, execute, run, deploy |
| EVALUATE | check, validate, test, verify, audit, review, inspect, compare |
| PERCEIVE | monitor, watch, listen, observe, subscribe, detect, capture |
| REPORT   | report, summarise, export, format, render, generate, produce |
| REASON   | default (no keyword match) |

**Key design decisions:**
- `mcp` package is a soft dependency — AFMX starts without it. `ImportError`
  with install instructions is raised only when adapter methods are called.
- Short-lived connections per tool call — no dangling connections in
  long-running AFMX executions.
- Stateless adapter — all server config captured in handler closure at
  registration time; handlers are fully self-contained.
- Deduplication in `from_desktop_config()` — duplicate handler keys skipped;
  failed servers logged and skipped, not raised.

**Install:**
```bash
pip install afmx[mcp]       # adds mcp>=1.0.0
pip install afmx[adapters]  # all adapters including mcp
```

### Fixed — `ExecutionRecord.matrix_snapshot` (ad-hoc matrix resume)

**Bug:** `POST /afmx/resume/{execution_id}` failed silently for matrices that
were never saved to `MatrixStore` (i.e., submitted directly as a dict to
`POST /afmx/execute` without a prior `POST /afmx/matrices` save call).

**Root cause:** `ExecutionRecord` stored `matrix_id` and `matrix_name` but not
the matrix definition itself. The resume endpoint called `MatrixStore.get(name)`
and raised 404 for any ad-hoc matrix.

**Fix:** Added `matrix_snapshot: Optional[Dict[str, Any]]` to `ExecutionRecord`.
Both execute endpoints (`POST /execute` and `POST /execute/async`) now capture
`matrix.model_dump()` into this field at execution start. The resume endpoint
now falls back to this snapshot when the matrix is not in `MatrixStore`.

Fully backward-compatible: existing records without the field load with
`matrix_snapshot=None`. No migration needed.

### Fixed — `EventType.LAYER_STARTED` / `LAYER_COMPLETED` (diagonal events)

**Bug:** `_run_diagonal()` emitted `EventType.EXECUTION_STARTED` with
`data={"diagonal_layer": "REASON", "batch_size": 3}` to signal cognitive-layer
boundaries. Webhook receivers and the Agentability integration could not
distinguish a layer boundary from the run start without inspecting the `data`
payload — violating the contract of typed events.

**Fix:** Added two new `EventType` values:
- `EventType.LAYER_STARTED = "layer.started"` — emitted before each layer batch
  with `data={"layer": "REASON", "batch_size": 3}`
- `EventType.LAYER_COMPLETED = "layer.completed"` — emitted after each layer
  batch with `data={"layer": "REASON", "success": 3, "failed": 0}`

`_run_diagonal()` now emits `LAYER_STARTED` / `LAYER_COMPLETED` instead of the
oveloaded `EXECUTION_STARTED`. The single `EXECUTION_STARTED` event per run is
preserved and unaffected.

Webhook and Agentability consumers subscribed to `EXECUTION_STARTED` are
unaffected. Consumers that inspected `data["diagonal_layer"]` should migrate to
`LAYER_STARTED`.

### Changed

- `afmx/adapters/__init__.py` — exports `MCPAdapter`, `MCPServerConfig`,
  `infer_cognitive_layer`.
- `afmx/adapters/registry.py` — `mcp` added to `_ensure_builtins()` spec list.
- `pyproject.toml` — version `1.2.1`; `mcp = ["mcp>=1.0.0"]` optional dep;
  `mcp` and `model-context-protocol` added to keywords; `mcp>=1.0.0` added
  to `adapters` extras group.

### Tests

- `tests/unit/test_week1_week2_fixes.py` — 50+ tests covering:
  - `ExecutionRecord.matrix_snapshot` field, round-trip, backward compat.
  - `EventType.LAYER_STARTED` / `LAYER_COMPLETED` values and isolation.
  - DIAGONAL engine emits correct event types (integration test with real engine).
  - `infer_cognitive_layer()` — 25 parametrised cases.
  - `MCPAdapter` unit tests (no mcp package required).
  - `MCPAdapter` integration tests with mocked MCP SDK session.

---

## [1.2.0] — 2026-03-22 — Open Column Axis + Domain Packs

### Summary

v1.2 fixes the core architectural flaw in v1.1: the `AgentRole` column axis was
a hardcoded 7-value Python enum locked to tech/SRE vocabulary. This made the
Cognitive Matrix unusable for every industry outside software engineering.

The fix: `agent_role` is now an **open string field** (`Optional[str]`) with a
validation regex. Any domain vocabulary is valid. Five built-in domain packs
ship with the framework. Custom domains take 8 lines of Python.

All v1.1 code is fully backward-compatible — `AgentRole.OPS` still works because
`AgentRole` is now a namespace class of string constants, not an enum.

### New — `afmx/domains/` package

- **`afmx/domains/__init__.py`** — `DomainPack` frozen dataclass, `DomainRegistry`,
  and global `domain_registry`. `DomainPack` defines name, description, roles
  dict (role_name → description), and tags. Immutable after construction.

- **`afmx/domains/tech.py`** — `TechDomain` + `AgentRole` backward-compat namespace.
  Roles: `RESEARCHER`, `CODER`, `ANALYST`, `OPS`, `COMPLIANCE`, `VERIFIER`, `PLANNER`.
  Auto-registers on import.

- **`afmx/domains/finance.py`** — `FinanceDomain` + `FinanceRole`.
  Roles: `QUANT`, `TRADER`, `RISK_MANAGER`, `PORTFOLIO_MANAGER`, `COMPLIANCE_OFFICER`,
  `ANALYST`, `AUDITOR`. Tags: finance, trading, risk, capital-markets, fintech.

- **`afmx/domains/healthcare.py`** — `HealthcareDomain` + `HealthcareRole`.
  Roles: `CLINICIAN`, `PHARMACIST`, `RADIOLOGIST`, `NURSE`, `ADMINISTRATOR`,
  `RESEARCHER`, `ASSESSOR`. Tags: healthcare, clinical, hospital, digital-health.

- **`afmx/domains/legal.py`** — `LegalDomain` + `LegalRole`.
  Roles: `PARALEGAL`, `ASSOCIATE`, `PARTNER`, `EXPERT_WITNESS`, `CLERK`, `JUDGE`,
  `NOTARY`. Tags: legal, law, compliance, legaltech, litigation.

- **`afmx/domains/manufacturing.py`** — `ManufacturingDomain` + `ManufacturingRole`.
  Roles: `ENGINEER`, `QUALITY_INSPECTOR`, `MAINTENANCE_TECH`, `SAFETY_OFFICER`,
  `PROCESS_MANAGER`, `OPERATOR`, `SUPPLY_PLANNER`.
  Tags: manufacturing, industrial, iot, predictive-maintenance, quality.

### Changed — Core Models

- **`afmx/models/node.py`**:
  - `AgentRole` enum removed. Re-exported from `afmx.domains.tech` as a plain
    namespace class. `AgentRole.OPS == "OPS"` (backward-compatible).
  - `Node.agent_role: Optional[str]` — open string field. Validates against
    `[A-Z][A-Z0-9_]{0,63}`. Accepts any domain vocabulary.
  - `Node.has_matrix_address` still works: `True` when both `cognitive_layer`
    and `agent_role` are set.
  - Docstring updated with full axis explanation and domain pack imports.

- **`afmx/models/matrix.py`**:
  - `MatrixAddress.role: str` (was `AgentRole` enum). Open string. Hashable.
    `MatrixAddress(layer=CognitiveLayer.REASON, role="QUANT")` is valid.
  - `get_nodes_at_role(role: str)` — now accepts any string.
  - `roles_in_matrix()` — new method, returns sorted list of unique role strings
    present in the matrix.
  - `matrix_coverage_summary()` — `cells_possible` is now dynamic
    (7 layers × N unique roles observed), not a fixed constant.

### Changed — API

- **`GET /afmx/matrix-view/{execution_id}`**: `roles` field is now dynamic
  (discovered from execution's node results, not a hardcoded enum list).
  New `role_meta` field: per-role descriptions and domain attribution from
  registered domain packs.

- **`GET /afmx/domains`** (new): list all registered domain packs.

- **`GET /afmx/domains/{name}`** (new): get a specific domain pack by name.

### Changed — Dashboard

- **`MatrixView.tsx`** — fully rewritten:
  - Column headers are now dynamic — rendered from `view.roles` (API response),
    not from a hardcoded constant array.
  - Each column header shows the domain badge (tech, finance, healthcare, etc.)
    from `role_meta`.
  - Detail panel shows role description and domain attribution.
  - Summary strip shows detected domain and role count.
  - Role vocabulary panel shows all roles detected in the execution.
  - Empty state shows domain-selector with example snippets for each built-in domain.

- **`Domains.tsx`** (new page): Domain Pack Explorer.
  - Lists all registered domain packs with expandable role tables.
  - Search by domain name, role name, or tag.
  - Shows per-role descriptions.
  - Includes usage example code per domain.
  - Layer reference sidebar.
  - Custom domain registration code snippet.
  - API endpoint reference.

- **`RunMatrix.tsx`** — four cross-domain templates added:
  - `cognitive` — Tech/SRE incident response (existing)
  - `finance` — Capital markets risk analysis (QUANT, TRADER, RISK_MANAGER, …)
  - `healthcare` — Clinical decision support (CLINICIAN, NURSE, PHARMACIST, …)
  - `legal` — Legal research and litigation (PARALEGAL, ASSOCIATE, PARTNER, …)

- **`types.ts`**: `AgentRole = string` (was fixed union type). `RoleMeta`,
  `DomainPack`, `DomainListResponse` types added. `MatrixViewResponse` includes
  `role_meta: Record<string, RoleMeta>`.

- **`api.ts`**: `domains()` and `domain(name)` methods added.

- **`useApi.ts`**: `useDomains()` and `useDomain(name)` hooks added.

- **`Sidebar.tsx`**: Domain Packs nav link added to Intelligence group.
  `IconDomains` SVG icon added.

- **`App.tsx`**: `/domains` route registered.

### Changed — Public API

- **`afmx/__init__.py`**: all five domain packs and their role constant classes
  exported at the top level. Version: `1.2.0`.

- **`pyproject.toml`**: version `1.2.0`.

### Tests

- `tests/unit/test_cognitive_matrix.py` — completely rewritten for v1.2:
  60+ tests covering open string validation, all five domain packs, cross-domain
  matrices, `matrix_coverage_summary()` dynamic `cells_possible`, backward
  compatibility, `CognitiveModelRouter` role-agnostic routing.

### Backward compatibility

Fully backward-compatible. All v1.1 code continues to work:

```python
# v1.1 — still works
from afmx.models.node import AgentRole
node = Node(agent_role=AgentRole.OPS, ...)   # AgentRole.OPS == "OPS"

# MatrixAddress with old-style role
addr = MatrixAddress(layer=CognitiveLayer.ACT, role=AgentRole.OPS)
assert str(addr) == "ACT×OPS"

# v1.2 — new cross-industry usage
from afmx.domains.finance import FinanceRole
node = Node(agent_role=FinanceRole.QUANT, ...)
node = Node(agent_role="CLINICIAN", ...)
```

---

## [1.1.0] — 2026-03-22 — Cognitive Execution Matrix

### New — Cognitive Execution Matrix (v1.1)

- **`CognitiveLayer` enum** (`afmx/models/node.py`) — 7 cognitive layer values:
  `PERCEIVE`, `RETRIEVE`, `REASON`, `PLAN`, `ACT`, `EVALUATE`, `REPORT`.
  Represents the ROW axis of the Cognitive Execution Matrix.

- **`AgentRole` enum** (`afmx/models/node.py`) — 7 functional domain values:
  `RESEARCHER`, `CODER`, `ANALYST`, `OPS`, `COMPLIANCE`, `VERIFIER`, `PLANNER`.
  Represents the COLUMN axis of the Cognitive Execution Matrix.

- **`Node.cognitive_layer` / `Node.agent_role`** — Optional fields on every Node.
  Existing matrices without these fields continue to work unchanged (fully backward-compatible).
  `Node.has_matrix_address` property — `True` when both fields are set.

- **`MatrixAddress`** (`afmx/models/matrix.py`) — Frozen Pydantic model:
  `MatrixAddress(layer, role)` — hashable, usable as dict/set key.
  String representation: `"REASON×COMPLIANCE"`.

- **`ExecutionMode.DIAGONAL`** (`afmx/models/matrix.py`) — New execution mode.
  Groups nodes by `CognitiveLayer` and runs each layer's nodes in parallel.
  Layers execute in canonical order: `PERCEIVE → RETRIEVE → REASON → PLAN → ACT → EVALUATE → REPORT`.
  Nodes without `cognitive_layer` run in a final unclassified batch.

- **`ExecutionMatrix` helpers** (`afmx/models/matrix.py`):
  - `get_matrix_address(node_id)` — returns `MatrixAddress` or `None`.
  - `get_nodes_at_layer(layer)` — all nodes at a given cognitive row.
  - `get_nodes_at_role(role)` — all nodes at a given agent column.
  - `build_matrix_map()` — `Dict[MatrixAddress, Node]` for all coordinated nodes.
  - `matrix_coverage_summary()` — coverage stats: coordinated/uncoordinated counts,
    populated cells, coverage_pct.

- **`CognitiveModelRouter`** (`afmx/core/cognitive_router.py`) — New module.
  Routes LLM model selection by `CognitiveLayer`:
  - `PERCEIVE`, `RETRIEVE`, `ACT`, `REPORT` → cheap model (Haiku, gpt-4o-mini).
  - `REASON`, `PLAN`, `EVALUATE` → premium model (Opus, o3).
  - Configured via `AFMX_COGNITIVE_CHEAP_MODEL` / `AFMX_COGNITIVE_PREMIUM_MODEL`.
  - `inject_hint(node, context)` — injects `__model_hint__`, `__model_tier__`,
    `__cognitive_layer__`, `__agent_role__` into `ExecutionContext.metadata`
    before each node's handler is called.
  - `list_layer_assignments()` — returns full tier map for all 7 layers.

- **`AFMXEngine` wiring** (`afmx/core/engine.py`):
  - `CognitiveModelRouter` injected at construction (configurable).
  - `cognitive_router.inject_hint()` called before every node with `cognitive_layer` set.
  - `cognitive_layer` and `agent_role` captured in `NodeResult` after execution.
  - All NODE_STARTED / NODE_COMPLETED events include `cognitive_layer`, `agent_role`,
    `model_tier` in event data.
  - `_run_diagonal()` — full DIAGONAL mode implementation.

- **`GET /afmx/matrix-view/{execution_id}`** (`afmx/api/routes.py`) — New endpoint.
  Returns 2D cell map keyed as `"LAYER:ROLE"`, with status, duration, model tier,
  model string, error, and attempt per cell. Includes summary (coverage_pct, success_rate).

- **Settings** (`afmx/config.py`):
  - `AFMX_COGNITIVE_CHEAP_MODEL` (default: `claude-haiku-4-5-20251001`)
  - `AFMX_COGNITIVE_PREMIUM_MODEL` (default: `claude-opus-4-6`)

- **7 cognitive-aware built-in handlers** (`afmx/startup_handlers.py`):
  `perceive`, `retrieve`, `reason`, `plan`, `act`, `evaluate`, `report`.
  Each reads `__model_hint__` / `__model_tier__` from metadata and includes
  routing telemetry in output for dashboard visibility.

- **`NodeType.MCP`** — New node type for native MCP server nodes (adapter coming in v1.1.1).

### New — Dashboard UI

- **Cognitive Matrix page** (`afmx/dashboard/src/pages/MatrixView.tsx`) — New page.
  Interactive 7×7 heatmap (CognitiveLayer × AgentRole).
  - Cell status colour-coded (green=success, red=failed, purple=fallback).
  - Model tier badges per cell (◇ cheap / ★ premium).
  - Click any cell → detail panel (status, duration, model, error, node ID).
  - Summary strip (active cells, coverage%, success rate, failed count).
  - Layer guide legend with descriptions.
  - Execution selector (picks from last 50 executions).
  - Empty-state callout with usage example JSON.

- **Navigation** (`afmx/dashboard/src/components/layout/Sidebar.tsx`):
  New "Intelligence" nav group with "Cognitive Matrix" link and custom `IconMatrix` SVG.

- **Run Matrix template** (`afmx/dashboard/src/pages/RunMatrix.tsx`):
  `cognitive` template — 10-node DIAGONAL SRE incident response matrix.

- **Types** (`afmx/dashboard/src/types.ts`):
  `CognitiveLayer`, `AgentRole`, `MatrixCell`, `MatrixViewSummary`, `MatrixViewResponse`.

- **API client** (`afmx/dashboard/src/api.ts`): `matrixView(executionId)` method.

- **Hook** (`afmx/dashboard/src/hooks/useApi.ts`): `useMatrixView(executionId)` hook.

### New — Tests

- `tests/unit/test_cognitive_matrix.py` — 35+ unit tests covering enums,
  `MatrixAddress`, `CognitiveModelRouter`, `ExecutionMatrix` helpers, backward compat.

- `tests/unit/test_diagonal_engine.py` — 9 integration tests covering DIAGONAL
  execution order, model tier injection, NodeResult capture, mixed coordinated/uncoordinated
  nodes, failure/abort handling.

### Changed

- `afmx/models/__init__.py` — exports `CognitiveLayer`, `AgentRole`, `MatrixAddress`.
- `afmx/core/__init__.py` — exports `CognitiveModelRouter`.
- `afmx/__init__.py` — exports all new v1.1 public types.
- `afmx/dashboard/src/App.tsx` — `/matrix` route registered.

### Backward compatibility

All changes are fully additive. Existing matrices, nodes, handlers, and API calls
are unaffected. `cognitive_layer` and `agent_role` are Optional with `None` defaults.
`SEQUENTIAL`, `PARALLEL`, and `HYBRID` execution modes are unchanged.

---

## [1.0.1] — 2026-03-21 — Production Polish + Agentability Integration

### New
- **Agentability integration** (`afmx/integrations/agentability_hook.py`)
  - Every AFMX node → Agentability Decision (agent_id = `matrix_name.node_name`)
  - Every matrix execution → Agentability Session (session_id = execution_id)
  - Circuit breaker events → Agentability Conflict (RESOURCE_CONFLICT)
  - Retry attempts → LLM metrics with finish_reason
  - Zero-overhead no-op when `agentability` package not installed
  - Failure never blocks AFMX execution (fully isolated try/except)
- **React 18 SPA dashboard** (`afmx/dashboard/`)
  - Vite 5 + TypeScript strict + TanStack Query v5 + Recharts
  - Pages: Overview, Executions, Live Stream, Run Matrix, Saved Matrices, Plugins, Audit Log, API Keys
  - Execution detail modal: Trace / Waterfall (Gantt) / Output tabs
  - AFMX Engine link in sidebar + AFMX session filter in Decisions page
  - Dark/light theme with no flash (synchronous localStorage read before React mounts)
  - `npm run build` outputs to `afmx/static/` — FastAPI serves automatically
- **Full RBAC system** (`afmx/auth/`)
  - 5 roles: VIEWER / SERVICE / DEVELOPER / OPERATOR / ADMIN
  - 16 granular permissions
  - `APIKeyStore` with memory + Redis backends
  - Bootstrap ADMIN key printed to stdout on first start
- **Audit log** (`afmx/audit/`)
  - Append-only `AuditStore` with 25+ `AuditAction` constants
  - Queryable via `GET /afmx/audit`
  - Export as JSON, CSV, NDJSON via `GET /afmx/audit/export/{format}`
- **Webhook notifier** (`afmx/observability/webhook.py`)
  - HTTP POST delivery with HMAC-SHA256 signing
  - Configurable event filter, retry count, and timeout
- **`NodeResult.started_at` and `NodeResult.finished_at`**
  - Wall-clock Unix timestamps per node
  - Enables accurate Gantt waterfall chart in dashboard
  - Exposed in `ExecutionResponse` via `schemas.py`
- **`realistic_handlers.py`** (project root)
  - Production-grade analyst, writer, reviewer stubs with:
    - Confidence scores (0.52–0.97, content-sensitive drift)
    - Reasoning chains (4-step per agent)
    - LLM token counts + cost estimates (GPT-4o pricing)
    - Constraint checking + violation reporting
    - 150–600ms realistic latency
  - Auto-loaded by `startup_handlers.py` on server start
- **`demo_multiagent.py`** — 7 live multi-agent scenarios against running server
- **`demo_agentability.py`** — AFMX + Agentability integration demo (4 scenarios)
- **`AFMX_AGENTABILITY_*` env vars** added to config, `.env.example`, and docs
- **`AFMX_RBAC_ENABLED`**, `AFMX_AUDIT_ENABLED`, `AFMX_WEBHOOK_*` vars fully documented
- **Admin routes** (`GET/POST/DELETE /afmx/admin/keys`, `GET /afmx/admin/stats`)
- **Audit routes** (`GET /afmx/audit`, `GET /afmx/audit/export/{format}`)
- **`agentability` field in `GET /health`** response: `{enabled, connected, db_path, api_url}`

### Fixed
- `config.py` `settings_customise_sources()` — replaced explicit parameter list with
  `(*args, **kwargs)` defensive extraction; works across all pydantic-settings versions (2.1–2.4+)
- `schemas.py` `NodeResultResponse` — added `started_at: Optional[float]` and
  `finished_at: Optional[float]`; waterfall bars were flat without these
- `Agentability platform/api/main.py` — CORS origins now read from
  `AGENTABILITY_CORS_ORIGINS` env var (comma-separated); was hardcoded to `localhost:3000`
- `Agentability platform/api/routers/decisions.py` — pagination `total` now uses
  a proper full-count query; was returning only rows in the current page slice
- `Agentability dashboard vite.config.ts` — `VITE_API_URL` injected at build via
  `define:`; `host: '0.0.0.0'` added; production builds now work behind nginx
- `dashboard App.tsx` — `BrowserRouter basename` now `"/"` in dev, `"/afmx/ui"` in prod;
  was causing blank screen in `npm run dev`
- `dashboard index.css` — dark theme tokens moved to `:root` as baseline; were
  only in `.dark {}` causing black screen before React mount
- `hooks/useApi.ts` — `useExecuteMutation` typed as `useMutation<ExecuteResult, Error, ExecuteRequest>`;
  TypeScript error TS2322 on union return type
- `pages/Executions.tsx` — `fallback_used` guard wrapped in `Boolean(...)`;
  TypeScript error TS2322 on `unknown` used as JSX condition

### Improved
- `.gitignore` — expanded to 50+ entries covering Python, Node, IDEs, secrets, SQLite, Docker
- `pyproject.toml` — classifier updated to `Production/Stable`; version bounds tightened;
  dead files excluded from coverage; `dev` extras updated to latest tool versions
- `requirements.txt` — updated to match `pyproject.toml` dev extras; added `websockets`
- `requirements-prod.txt` — documented update process; separated from dev tools
- `docs/index.md` — complete rewrite with accurate project layout (dashboard, integrations, realistic_handlers)
- `docs/quickstart.md` — rewritten with React dashboard build, realistic handlers, live demo steps
- `docs/configuration.md` — all `AGENTABILITY_*`, `RBAC_*`, `AUDIT_*`, `WEBHOOK_*` vars documented
- `docs/api_reference.md` — `NodeResult.started_at`/`finished_at` added; Admin + Audit sections added;
  Agentability field in health response documented
- `docs/architecture.md` — full AFMX vs Airflow/Temporal/LangGraph comparison table added;
  Auth, Audit, Integrations layers added to layer diagram
- `docs/observability.md` — complete rewrite with Agentability integration section
- `README.md` — complete rewrite: dashboard, demo scripts, Agentability, API table, AFMX vs LangGraph

### Removed
- `afmx/_ui_block.py` — leftover temp file from editing session (emptied)
- `afmx/_ui_spa_block.py` — leftover temp file (emptied)
- `afmx/core/_engine_patch.py` — patch merged into engine.py (emptied)
- `afmx/api/adapters_routes.py` — stub pointing to canonical `adapter_routes.py` (emptied)
- `_fix_snippet.py` — leftover debug artifact (emptied)

---

## [1.0.0] — 2026-03-18 — Initial Production Release

### Core Engine
- `AFMXEngine` — SEQUENTIAL, PARALLEL, HYBRID execution modes
- DAG-based `ExecutionMatrix` with Kahn's topological sort + parallel batch detection
- Full cycle detection with descriptive error messages
- Global timeout (`asyncio.wait_for`) wrapping entire matrix execution
- Per-node timeout enforcement inside `NodeExecutor`

### Fault Tolerance
- `RetryManager` — exponential backoff with configurable multiplier, jitter, max cap
- `CircuitBreaker` — CLOSED / OPEN / HALF_OPEN state machine, per-node registry
- Fallback node routing — activated on terminal failure when `fallback_node_id` set
- `AbortPolicy` — FAIL_FAST, CONTINUE (partial), CRITICAL_ONLY

### Routing & Dispatch
- `ToolRouter` — deterministic, rule-based routing; intent regex, metadata match, tag match
- `AgentDispatcher` — complexity range, capability set, sticky sessions, round-robin
- `HandlerRegistry` — short aliases + dotted module path resolution, sync & async handlers

### Variable Resolution
- `VariableResolver` — `{{input.field}}`, `{{node.id.output.field}}`, `{{memory.key}}`,
  `{{variables.name}}`, `{{metadata.key}}` template expressions
- Full typed resolution (returns original type, not stringified)

### Hooks
- `HookRegistry` — PRE_MATRIX, POST_MATRIX, PRE_NODE, POST_NODE
- Decorator-based registration, priority ordering, node_filter support
- Error isolation — hook failures never kill execution

### Concurrency
- `ConcurrencyManager` — global semaphore, queue timeout, live stats
- asyncio primitives lazy-initialized (safe for Python 3.10–3.12)

### Store
- `InMemoryStateStore` + `RedisStateStore` — TTL, eviction, async lock
- `InMemoryCheckpointStore` + `RedisCheckpointStore`
- `InMemoryMatrixStore` + `RedisMatrixStore`

### Observability
- `EventBus` — async, wildcard subscriptions, error-isolated handlers
- `AFMXMetrics` — Prometheus counters, gauges, histograms

### REST API
- Full execution lifecycle endpoints (execute, async, status, result, list, validate, cancel, retry)
- Matrix CRUD + execute-by-name
- WebSocket streaming per execution_id
- Plugin, adapter, concurrency, hook inspection endpoints

### Adapters
- LangChain, LangGraph, CrewAI, OpenAI — lazy imports, stateless wrappers

### CLI
- `afmx serve`, `run`, `status`, `result`, `list`, `validate`, `plugins`, `health`, `cancel`

### Tests
- 18 unit test files, 250+ test cases
- 4 integration test files, 40+ test cases
- pytest-asyncio auto mode

### Infrastructure
- 2-stage Dockerfile (builder + runtime, non-root user)
- `docker-compose.yml` — AFMX + Redis + Prometheus
- `prometheus.yml` scrape config
