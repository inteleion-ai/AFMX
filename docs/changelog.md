# Changelog

All production-significant changes to AFMX, in reverse chronological order.  
Format: `[file] — Bug / Feature — Fix applied`

---

## v1.0.1 — 2026-03-21 — Production Polish + Agentability Integration

### Critical Bug Fixes

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `config.py` | `settings_customise_sources()` explicit parameter list broke across pydantic-settings 2.1–2.4+ | Replaced with `(*args, **kwargs)` defensive extraction |
| 2 | `api/schemas.py` | `NodeResultResponse` missing `started_at` and `finished_at` fields | Added `Optional[float]` fields — waterfall chart was flat without these |
| 3 | `dashboard/src/App.tsx` | `BrowserRouter basename="/afmx/ui"` — router matched nothing in dev, blank screen | `BASENAME = "/afmx/ui"` in prod, `"/"` in dev via `import.meta.env.PROD` |
| 4 | `dashboard/src/index.css` | CSS colour tokens only in `.dark {}` class — black screen before React mount | Dark theme tokens moved to `:root` as baseline; `.light` overrides only |
| 5 | `dashboard/src/main.tsx` | Theme class applied in `useEffect` (post-paint) — flash of unstyled content | Synchronous `localStorage` read before `createRoot()` — applies class before first paint |
| 6 | `dashboard/src/hooks/useApi.ts` | `useMutation` inferred as `useMutation<ExecutionRecord>` but `mutationFn` returns union type | Explicit `useMutation<ExecuteResult, Error, ExecuteRequest>` with `ExecuteResult = ExecutionRecord \| AsyncResult` |
| 7 | `dashboard/src/pages/Executions.tsx` | `(metadata as Record<string, unknown>)?.fallback_used` typed as `unknown` — TS2322 | Wrapped in `Boolean(...)` to narrow `unknown → boolean` |
| 8 | `dashboard/src/components/ui/index.tsx` | Imported `statusColor`, `statusBg`, `statusRing`, `typeColor`, `roleColor` (all non-existent) — TypeScript compile crash | Replaced with empty deprecated stub; real barrel is `index.ts` |
| 9 | `dashboard/src/index.css` | 9 CSS custom properties used but never defined: `--font-mono`, `--font-sans`, `--bg-canvas`, `--green-ring`, `--red-ring`, `--amber-ring`, `--cyan-ring`, `--purple-ring`, `--ease-fast` | All 9 added to `:root` block |
| 10 | `Agentability platform/api/main.py` | CORS origins hardcoded to `localhost:3000` | Now reads `AGENTABILITY_CORS_ORIGINS` env var (comma-separated), falls back to localhost defaults |
| 11 | `Agentability platform/api/routers/decisions.py` | Pagination `total` returned `len(page)` (current page size) not true record count | Separate `store.query_decisions(limit=10_000)` call for count before applying slice |
| 12 | `Agentability dashboard vite.config.ts` | `VITE_API_URL` not injected at build; `host` not bound to `0.0.0.0` | `define: { __API_URL__: ... }` + `host: '0.0.0.0'` |
| 13 | `Agentability Makefile` | `api:` target used `agentability_api.main:app` — module does not exist | Fixed to `platform.api.main:app` |
| 14 | `Agentability README.md` | Dashboard section used same wrong module path | Fixed to `platform.api.main:app` |

### Dead Files Cleared

| File | Status |
|---|---|
| `afmx/api/adapters_routes.py` | Emptied — canonical file is `adapter_routes.py` |
| `afmx/core/_engine_patch.py` | Emptied — patch fully merged into `engine.py` |
| `_fix_snippet.py` | Emptied — dev debug artifact |

### Features Added

- **Agentability integration** (`afmx/integrations/agentability_hook.py`) — PRE_NODE + POST_NODE hooks map every AFMX execution to Agentability Decisions/Sessions/Conflicts. Zero-overhead when package not installed.
- **React 18 SPA dashboard** (`afmx/dashboard/`) — Vite + TypeScript strict + TanStack Query v5 + Recharts. 8 pages including Waterfall chart, Audit log, API key management.
- **`NodeResult.started_at` / `finished_at`** — per-node timestamps enabling accurate Gantt waterfall in dashboard.
- **`realistic_handlers.py`** — analyst/writer/reviewer stubs with confidence scores, reasoning chains, token costs, constraint checking. Auto-loaded by `startup_handlers.py`.
- **`demo_multiagent.py`** — 7 live multi-agent scenarios (research, parallel, routing, retry, document, swarm, burst).
- **`demo_agentability.py`** — 4 AFMX + Agentability integration scenarios.
- **Full RBAC system** (`afmx/auth/`) — 5 roles × 16 permissions, bootstrap key, memory + Redis backends.
- **Audit log** (`afmx/audit/`) — append-only store, 25+ action types, JSON/CSV/NDJSON export.
- **Webhook notifier** (`afmx/observability/webhook.py`) — HMAC-signed HTTP delivery with retry.
- **Agentability `docs/README.md`** — full SDK reference, platform API, dashboard guide, AFMX integration guide.
- **`platform/.env.example`** — added `AGENTABILITY_CORS_ORIGINS` and all missing vars.

### Infrastructure

- `.gitignore` — expanded from 181 bytes to 50+ proper entries
- `pyproject.toml` — `Development Status :: 5 - Production/Stable`; tighter version bounds; dead files excluded from coverage
- `requirements.txt` / `requirements-prod.txt` — updated to match; added `websockets`

### Documentation Updated

| Doc | Change |
|---|---|
| `README.md` | Complete rewrite — dashboard, demo scripts, Agentability, full API table |
| `docs/index.md` | Accurate layout including dashboard, integrations, realistic_handlers |
| `docs/quickstart.md` | React dashboard build, live demo, all 15 pre-registered handlers |
| `docs/configuration.md` | All `AGENTABILITY_*`, `RBAC_*`, `AUDIT_*`, `WEBHOOK_*` vars added |
| `docs/api_reference.md` | `started_at`/`finished_at` in NodeResult; Admin + Audit endpoints; 401/403 errors |
| `docs/architecture.md` | AFMX vs Airflow/Temporal/LangGraph comparison; Auth/Audit/Integrations layers |
| `docs/concepts.md` | `started_at`/`finished_at` added to NodeResult field reference |
| `docs/observability.md` | Complete rewrite with Agentability integration section |
| `docs/testing.md` | Unit file count corrected: 17 → 18 |
| `CHANGELOG.md` | v1.0.1 fully documented |

---

## v1.0.0 — Production Release

### Critical Bug Fixes (23 total across 2 audit sessions)

#### Models

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `models/node.py` | Pydantic v1 `class Config` — deprecation warning on every import | Replaced with `model_config = ConfigDict(use_enum_values=True)` |
| 2 | `models/edge.py` | Pydantic v1 `class Config: populate_by_name = True` | Replaced with `model_config = ConfigDict(populate_by_name=True)` |
| 3 | `models/matrix.py` | `topological_order()` called `get_node_by_id()` (O(n)) inside sort key → O(n² log n) for large graphs | Pre-built `priority: Dict[str, int]` for O(1) lookup per node |

#### Core Engine

| # | File | Bug | Fix |
|---|---|---|---|
| 4 | `core/engine.py` | `CRITICAL_ONLY` abort policy fell through to `mark_completed()` even when nodes failed | Now handled in `_ABORT_POLICIES` set alongside `FAIL_FAST` |
| 5 | `core/engine.py` | `topological_order()` called twice per SEQUENTIAL execution (validation + execution) | Called once in `execute()`, result passed as `topo_order` param to all methods |
| 6 | `core/engine.py` | PRE_MATRIX / POST_MATRIX hooks registered but never fired | Added `_run_matrix_hook("pre_matrix")` before dispatch and `_run_matrix_hook("post_matrix")` after |
| 7 | `core/engine.py` | Node hooks received `matrix_id=""` and `matrix_name=""` — always empty | Engine injects `__matrix_id__` and `__matrix_name__` into `context.metadata` before dispatch |
| 8 | `core/engine.py` | Fallback node double-execution — after running as fallback, it re-ran as standalone entry node in sequential loop | Added `if node_id in record.node_results: continue` in `_run_sequential`; fallback marked with `NodeStatus.FALLBACK` sentinel |
| 9 | `core/engine.py` | `event_bus` assigned after `RetryManager` — NODE_RETRYING events never reached the bus | `event_bus` assigned first; `RetryManager(event_bus=self.event_bus)` |
| 10 | `core/engine.py` | `get_node_by_id()` (O(n) scan) called per node in all loops | Pre-built `node_index: Dict[str, Node]` at start of `execute()`, passed through all mode methods |

#### Core Executor & Retry

| # | File | Bug | Fix |
|---|---|---|---|
| 11 | `core/executor.py` | `'node_input' in dir()` pattern — unreliable scope check | Pre-declared `node_input: Dict = {}` before try block so it is always defined |
| 12 | `core/retry.py` | `NODE_RETRYING` event type defined but never emitted | `RetryManager` takes `event_bus=` param, calls `_emit_retrying()` before each `asyncio.sleep()` |

#### Core Router & Dispatcher

| # | File | Bug | Fix |
|---|---|---|---|
| 13 | `core/router.py` | `from typing import Pattern` — removed in Python 3.12 | Changed to `from re import Pattern` |
| 14 | `core/dispatcher.py` | Round-robin always returned `available[0]` (always first, never distributed) | Added persistent `self._rr_counter: int` that increments across calls |

#### ConcurrencyManager

| # | File | Bug | Fix |
|---|---|---|---|
| 15 | `core/concurrency.py` | `asyncio.Semaphore()` and `asyncio.Lock()` created in `__init__` outside a running event loop → DeprecationWarning in Python 3.10+, crash in Python 3.12 | Lazy initialization on first `acquire()` call |

#### API Layer

| # | File | Bug | Fix |
|---|---|---|---|
| 16 | `api/routes.py` | `'updated' in dir()` broken pattern in `execute_async` | Replaced with proper `result_record = _record` scoping in the closure |
| 17 | `api/matrix_routes.py` | `execute_named_matrix` bypassed `ConcurrencyManager` entirely — no backpressure | Added `concurrency=Depends(get_concurrency_manager)` with acquire/release |
| 18 | `api/schemas.py` | Pydantic v1 `class Config` in `ExecuteRequest` and other schemas | Replaced with `ConfigDict` throughout |
| 19 | `api/matrix_routes.py` | `SaveMatrixRequest` used Pydantic v1 `class Config` | Replaced with `ConfigDict` |

#### Configuration & Infrastructure

| # | File | Bug | Fix |
|---|---|---|---|
| 20 | `config.py` | Pydantic v1 `class Config` in `AFMXSettings` | Replaced with `SettingsConfigDict(env_prefix="AFMX_", extra="ignore")` |
| 21 | `pyproject.toml` | `build-backend = "setuptools.backends.legacy:build"` — doesn't exist | Fixed to `"setuptools.build_meta"` |
| 22 | `models/node.py` | `TimeoutPolicy.ge=1.0` blocked sub-second timeouts (needed for tests) | Changed to `ge=0.01` |
| 23 | `tests/conftest.py` | Session-scoped `event_loop` fixture — deprecated in pytest-asyncio >= 0.21 | Removed entirely; `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` |

---

### Features Added / Completed

#### Engine

- `AFMXEngine._run_matrix_hook()` — fires PRE_MATRIX / POST_MATRIX hooks through the executor's `HookRegistry`
- `context.metadata["__matrix_id__"]` and `["__matrix_name__"]` injection — PRE_NODE / POST_NODE hooks now receive accurate matrix context
- Fallback result stored under primary node ID with `metadata["fallback_used"] = True` and `metadata["fallback_node_id"]`
- Fallback node receives `NodeStatus.FALLBACK` sentinel in `record.node_results` to prevent double-execution

#### RetryManager

- `RetryManager(event_bus=None)` — optional EventBus parameter
- `RetryManager.set_event_bus(bus)` — wire bus after construction
- `RetryManager._emit_retrying()` — emits `EventType.NODE_RETRYING` before each retry sleep
- `RetryManager.execute_with_retry()` — emits NODE_RETRYING on every retry attempt (not on the final failure)

#### Metrics

- `AFMXMetrics._on_node_retrying()` — wired to `EventType.NODE_RETRYING`
- `AFMXMetrics.attach_to_event_bus()` — now subscribes to `NODE_RETRYING` in addition to the existing 8 event types
- `_safe_counter()`, `_safe_gauge()`, `_safe_histogram()` helpers — prevent duplicate metric registration crash across test runs

#### Startup

- `afmx/startup_handlers.py` — 15 default handlers registered at server startup: `echo`, `upper`, `concat`, `multiply`, `summarize`, `validate`, `enrich`, `route`, `analyst_agent`, `writer_agent`, `reviewer_agent`, `flaky`, `always_fail`, `fallback_recovery`, `slow`
- `main.py` startup sequence — imports `startup_handlers` automatically, `plugin_registry.sync_to_handler_registry()` follows

---

### Test Suite Additions (v1.0.0)

#### New test coverage

| Test file | New tests added |
|---|---|
| `tests/unit/test_retry.py` | `test_node_retrying_event_emitted`, `test_no_retrying_event_on_first_attempt_success`, `test_no_event_bus_does_not_crash`, `test_circuit_breaker_blocks_retry_manager` |
| `tests/unit/test_executor.py` | `test_result_always_has_timestamps`, `test_node_metadata_merged_into_input`, `test_unresolvable_template_stays_as_none`, `test_injected_handler_bypasses_registry`, `test_hook_error_does_not_kill_execution` |
| `tests/integration/test_engine.py` | `test_continue_policy_produces_partial_status`, `test_critical_only_aborts_on_failure`, `test_pre_post_matrix_hooks_fire`, `test_post_matrix_hook_fires_on_failure`, `test_pre_node_hook_receives_matrix_context`, `test_node_retrying_event_emitted`, `test_node_skipped_event_emitted`, `test_fallback_node_activates_on_failure`, `test_fallback_not_triggered_on_success` |

#### Test infrastructure fixes

- All test files that register handlers now use `autouse` fixtures calling `HandlerRegistry.clear()` before AND after each test
- Integration test fallback tests use `ON_FAILURE` edges — prevents fallback nodes from double-executing as standalone entry nodes
- Removed broken `asyncio.coroutine` lambda (removed in Python 3.11) from engine integration tests

---

### Documentation (v1.0.0)

12 documentation files written covering the entire codebase:

| File | Pages |
|---|---|
| `docs/index.md` | Project overview, layout, quick start, test summary |
| `docs/architecture.md` | System layers, request lifecycle, key design decisions |
| `docs/concepts.md` | Node, Edge, Matrix, Context, Record — full field reference |
| `docs/quickstart.md` | Install → first execution → pipeline → async → tests |
| `docs/handlers.md` | Handler signature, registration methods, 5 patterns, testing, checklist |
| `docs/matrix_design.md` | Modes, edge conditions, abort policies, variable resolver, 5 common patterns |
| `docs/api_reference.md` | Every endpoint with full request/response schemas, WebSocket protocol |
| `docs/adapters.md` | LangChain, LangGraph, CrewAI, OpenAI adapter guides + custom adapter template |
| `docs/hooks.md` | 4 hook types, HookPayload, priority, 5 practical examples |
| `docs/observability.md` | EventBus, Prometheus metrics, WebSocket streaming, custom observability |
| `docs/configuration.md` | All 30 AFMX_ environment variables with defaults and production guidance |
| `docs/testing.md` | Running tests, writing tests, real-time scripts, common pitfalls |
| `docs/deployment.md` | Oracle Cloud Linux, systemd, Docker, Redis, Nginx, scaling, production checklist |
| `docs/changelog.md` | This file |

---

### Real-Time Test Scripts (v1.0.0)

| Script | Description |
|---|---|
| `scripts/test_realtime.py` | 17 sections, 50+ assertions against live server |
| `scripts/test_api.sh` | Equivalent curl test suite |
| `scripts/test_ws.py` | 3 WebSocket streaming demos |
| `scripts/test_load.py` | Concurrent load test with p50/p95/p99 latency |
