# AFMX Changelog

All notable changes are documented here.

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
