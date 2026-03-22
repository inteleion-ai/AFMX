# Architecture

## Overview

AFMX is a layered system. Each layer has one responsibility and communicates downward through explicit interfaces. Nothing leaks between layers.

```
┌───────────────────────────────────────────────────────────────────┐
│                    HTTP / WebSocket API                            │
│           FastAPI  ·  REST  ·  WS Streaming  ·  Admin             │
├───────────────────────────────────────────────────────────────────┤
│                       AFMXEngine                                  │
│    Sequential  ·  Parallel  ·  Hybrid  ·  Hooks  ·  EventBus     │
├──────────────┬───────────────┬───────────────┬─────────────────────┤
│ NodeExecutor │  RetryManager │   ToolRouter  │  AgentDispatcher   │
│  (per node)  │  + CB state   │   (tools)     │  (agents)          │
├──────────────┴───────────────┴───────────────┴─────────────────────┤
│                      HandlerRegistry                               │
│           key → async callable  (user or built-in)                │
├───────────────────────────────────────────────────────────────────┤
│                         Adapters                                  │
│         LangChain  ·  LangGraph  ·  CrewAI  ·  OpenAI            │
├───────────────────────────────────────────────────────────────────┤
│                          Models                                   │
│  Node  ·  Edge  ·  ExecutionMatrix  ·  ExecutionContext  ·  Record │
├─────────────────────────────┬─────────────────────────────────────┤
│     State / Matrix /        │          Observability              │
│     Checkpoint / Audit /    │  EventBus · Prometheus · WS · Hook  │
│     APIKey Stores           │  Agentability integration           │
└─────────────────────────────┴─────────────────────────────────────┘
```

---

## Layers

### API Layer (`afmx/api/`)

Entry point for all external interactions. Built on FastAPI with full async support.

| File | Responsibility |
|---|---|
| `routes.py` | Core execution: execute, execute/async, status, result, list, validate, cancel, retry |
| `matrix_routes.py` | Named matrix CRUD + execute-by-name |
| `websocket.py` | Real-time event streaming over WebSocket |
| `adapter_routes.py` | Adapter registry inspection |
| `admin_routes.py` | RBAC key management (create, revoke, delete) + admin stats |
| `audit_routes.py` | Audit log query + export (JSON/CSV/NDJSON) |
| `schemas.py` | Pydantic v2 request/response models |

Every execute endpoint:
1. Parses and validates the matrix definition via Pydantic
2. Constructs `ExecutionContext` from request fields
3. Creates `ExecutionRecord`, persists it to StateStore
4. Acquires a global concurrency slot (returns 503 on timeout)
5. Calls `AFMXEngine.execute()`
6. Releases slot, persists final record, returns response

### Engine (`afmx/core/engine.py`)

The orchestration core. Knows nothing about HTTP, databases, or AI reasoning.

**On every execution:**
- Injects `__matrix_id__` and `__matrix_name__` into `ExecutionContext.metadata` so hooks always have context
- Computes topological order **once** (O(V+E)) and reuses it — no redundant traversals
- Builds a `Dict[node_id, Node]` index for O(1) lookups
- Fires PRE_MATRIX hooks before the first node
- Dispatches to `_run_sequential`, `_run_parallel`, or `_run_hybrid`
- Fires POST_MATRIX hooks after execution settles (even on failure/timeout)
- Resolves final `ExecutionStatus`
- Emits one lifecycle event per state transition

**Execution modes:**

| Mode | Implementation |
|---|---|
| `SEQUENTIAL` | Kahn's topological sort, one node at a time, edge conditions evaluated after each node. Unreachable nodes marked SKIPPED. |
| `PARALLEL` | `asyncio.gather` on all nodes under `asyncio.Semaphore(max_parallelism)`. |
| `HYBRID` | Level-set decomposition (`get_parallel_batches()`). Nodes in same level run in parallel; levels are sequential. Best for real DAGs. |

### NodeExecutor (`afmx/core/executor.py`)

Executes one node. **Never raises** — all exceptions are captured into `NodeResult`.

```
1. Resolve handler (registry, ToolRouter, or AgentDispatcher)
2. Build node_input dict from context
3. Apply VariableResolver to params ({{template}} substitution)
4. Run PRE_NODE hooks (may modify node_input)
5. asyncio.wait_for(retry_wrapped, node.timeout_policy.timeout_seconds)
   └─ RetryManager.execute_with_retry()
      └─ handler(node_input, context, node)  ← your code runs here
6. On success: checkpoint_store.update_node_complete()
7. Run POST_NODE hooks (always fires, even on failure)
8. Return NodeResult
```

**Error → NodeStatus mapping:**

| Exception | NodeStatus |
|---|---|
| `asyncio.TimeoutError` | `FAILED` (error_type = TimeoutError) |
| `RuntimeError` | `ABORTED` (circuit breaker open or explicit abort) |
| `ImportError` | `FAILED` (handler key not found) |
| Any other exception | `FAILED` |

### RetryManager (`afmx/core/retry.py`)

Retry loops with exponential backoff and per-node circuit breakers.

- Emits `NODE_RETRYING` event on each retry (not on the final failure)
- Backoff formula: `min(base × multiplier^(attempt-1), max_backoff)`
- Jitter: computed delay × `(0.5 + random() × 0.5)`
- **CircuitBreaker** state machine per node_id:
  - `CLOSED` → normal operation
  - `OPEN` → all requests rejected immediately (raises RuntimeError)
  - `HALF_OPEN` → limited requests allowed to probe recovery
  - Returns to `CLOSED` after `recovery_timeout_seconds`

### HandlerRegistry (`afmx/core/executor.py`)

Class-level (global) dict. Supports string aliases and dotted module paths.

```python
HandlerRegistry.register("web_search", search_handler)
HandlerRegistry.resolve("web_search")                  # direct lookup
HandlerRegistry.resolve("mypackage.tools.search_fn")   # importlib + cache
```

Sync handlers are wrapped in `loop.run_in_executor(None, ...)` automatically — you never need to worry about blocking the event loop.

### ToolRouter (`afmx/core/router.py`)

Used for `NodeType.TOOL` nodes. Deterministic, rule-based routing:
1. Direct handler key match
2. Intent regex pattern matching
3. Metadata field matching
4. Tag-based matching
5. Default tool fallback
6. `RuntimeError` if nothing matches

### AgentDispatcher (`afmx/core/dispatcher.py`)

Used for `NodeType.AGENT` nodes. Routes by:
1. Explicit `handler_key`
2. Sticky session (`same session_id → same agent registration`)
3. Capability matching (`required_capabilities` subset check)
4. Complexity range (`complexity_min ≤ complexity ≤ complexity_max`)
5. Round-robin (persistent counter — true distribution, not always-first)
6. Default agent fallback
7. `RuntimeError` if nothing matches

Each `AgentRegistration` has `max_concurrent` and `acquire()`/`release()`. The engine enforces this around every AGENT node execution.

### Adapters (`afmx/adapters/`)

Thin, stateless bridges between external frameworks and AFMX.

```
LangChain Runnable / LangGraph Graph / CrewAI Crew / OpenAI client
        ↓  adapter.to_afmx_node()
AFMX Node (handler registered in HandlerRegistry)
        ↓  engine executes node
adapter callable invoked via handler
        ↓
AdapterResult → stored in NodeResult.output
```

All framework imports are **lazy** — the framework only needs to be installed if you use that adapter.

### Models (`afmx/models/`)

Pure Pydantic v2. No side effects, no database calls, no I/O.

| Model | Key behaviour |
|---|---|
| `Node` | Validates handler is non-empty; fallback_node_id must exist in matrix |
| `Edge` | Five condition types; EXPRESSION evaluated in restricted sandbox |
| `ExecutionMatrix` | Validates all edge references; checks for cycles on topological sort |
| `ExecutionContext` | Mutable state container flowing through the entire execution |
| `ExecutionRecord` | Full lifecycle: `mark_started()`, `mark_completed()`, `mark_failed()`, `mark_timeout()` |

### Store (`afmx/store/`)

Three independent stores, each with In-Memory and Redis backends:

| Store | Purpose | Redis DB |
|---|---|---|
| `StateStore` | `ExecutionRecord` lifecycle | 3 |
| `MatrixStore` | Named, versioned matrix definitions | 5 |
| `CheckpointStore` | Per-node incremental checkpoints | 4 |

Checkpoints allow resuming interrupted executions from the last completed node.

### Auth (`afmx/auth/`)

Full RBAC system:
- `rbac.py` — `APIKey` model, `Role` enum (5 roles: VIEWER/SERVICE/DEVELOPER/OPERATOR/ADMIN), 16 permission checks
- `store.py` — `APIKeyStore` (memory + Redis backends)
- `RBACMiddleware` in `afmx/middleware/rbac.py` — enforces role → permission mapping on every request

### Audit (`afmx/audit/`)

Append-only audit trail:
- `model.py` — `AuditEvent`, 25+ `AuditAction` constants
- `store.py` — `AuditStore` (memory + Redis), export to JSON/CSV/NDJSON
- Every execution, matrix, key, and auth operation emits an event

### Observability (`afmx/observability/`)

- **EventBus** — async pub/sub. Concurrent handlers. Error-isolated. Never blocks engine.
- **AFMXMetrics** — Prometheus counters, gauges, histograms. Attached to EventBus on startup. Safe against duplicate registration.
- **StreamManager** — bridges EventBus → WebSocket clients. Per-execution `asyncio.Queue`. EOF sent on terminal events.
- **WebhookNotifier** — HTTP POST delivery with HMAC signing and retry.

### Integrations (`afmx/integrations/`)

- **agentability_hook.py** — Attaches PRE_NODE + POST_NODE hooks and EventBus subscriber. Maps AFMX execution primitives to Agentability Decision/Session/Conflict records. Zero-overhead no-op when `agentability` package not installed.

---

## Request Lifecycle (Synchronous Execute)

```
POST /afmx/execute
    │
    ▼
routes.py: execute()
  ├─ Parse matrix → ExecutionMatrix (Pydantic validates DAG)
  ├─ Build ExecutionContext from request
  ├─ Create ExecutionRecord (status=QUEUED) → state_store.save()
  ├─ concurrency_manager.acquire()  [returns 503 on timeout]
    │
    ▼
AFMXEngine.execute(matrix, context, record)
  ├─ context.metadata["__matrix_id__"] = matrix.id
  ├─ emit EXECUTION_STARTED
  ├─ PRE_MATRIX hooks
  ├─ topological_order() → topo_order  [computed once]
  ├─ node_index = {n.id: n for n in matrix.nodes}  [O(1) lookup]
  ├─ asyncio.wait_for(_dispatch_mode(), global_timeout)
    │
    ▼
  _run_sequential / _run_parallel / _run_hybrid
    │
    └─ per node: _execute_node()
        ├─ emit NODE_STARTED
        ├─ _resolve_handler_and_reg()
        │    → ToolRouter.resolve() for TOOL
        │    → AgentDispatcher.dispatch() for AGENT
        │    → HandlerRegistry.resolve() fallback
        ├─ agent_reg.acquire()  [if AGENT node]
        ├─ NodeExecutor.execute()
        │    ├─ _build_input(node, context)
        │    ├─ VariableResolver.resolve_params(params, context)
        │    ├─ PRE_NODE hooks
        │    ├─ asyncio.wait_for(retry_wrapped, node_timeout)
        │    │    └─ RetryManager.execute_with_retry()
        │    │         └─ handler(node_input, context, node)  ← YOUR CODE
        │    ├─ checkpoint_store.update_node_complete()
        │    ├─ POST_NODE hooks
        │    └─ return NodeResult
        ├─ agent_reg.release()
        ├─ if terminal_failure and fallback_node_id: run fallback
        ├─ context.set_node_output(node.id, output)
        ├─ record.node_results[node.id] = node_result.model_dump()
        └─ emit NODE_COMPLETED or NODE_FAILED
    │
    ▼
  resolve final status (COMPLETED / FAILED / PARTIAL / TIMEOUT)
  emit EXECUTION_COMPLETED or EXECUTION_FAILED
  POST_MATRIX hooks
    │
    ▼
routes.py: execute()  (resumed)
  ├─ concurrency_manager.release()
  ├─ state_store.save(record)  [final state]
  └─ return ExecutionResponse
```

---

## Key Design Decisions

**Why is the engine non-intelligent?**
AFMX makes zero AI calls in the execution loop. Reasoning happens inside handlers, not in the engine. This makes execution paths fully deterministic, testable, and auditable.

**Why are asyncio primitives lazy in ConcurrencyManager?**
`asyncio.Semaphore()` and `asyncio.Lock()` must be created inside a running event loop. Python 3.10 deprecates creating them at module import time; Python 3.12 raises. Lazy init on first `acquire()` is the correct pattern.

**Why does `node_input` get declared before the try block?**
`_run_post_hook` must always run — even on failure — and it needs `node_input`. Pre-declaring `{}` guarantees it is always defined in scope regardless of where an exception fires.

**Why does the fallback node get a sentinel entry in `record.node_results`?**
Without it, the sequential loop finds the fallback node in topological order and executes it again as a standalone node. The `status=FALLBACK` sentinel signals the loop to skip it.

**Why is `topological_order()` called once?**
It runs Kahn's algorithm (O(V+E)) on every call. Computing it for validation and then again for execution would be O(2(V+E)). The order is computed once and passed through all dispatch functions.

**Why split ToolRouter and AgentDispatcher?**
Tools are deterministic — same input, same tool, every time. Agents need routing intelligence — complexity, capability, session affinity. Mixing them into one router would conflate deterministic dispatch with policy-based dispatch.

---

## AFMX vs Similar Tools

| | AFMX | Airflow | Temporal | LangGraph |
|---|---|---|---|---|
| **Primary purpose** | Agent execution fabric | Data pipeline scheduler | Durable workflow orchestration | LLM reasoning flow |
| **Execution trigger** | API call (demand) | Time-based / sensor | Activity signal | Code / LLM call |
| **Execution unit** | AI agent / tool | Script / SQL / Spark job | Activity function | LLM node |
| **Data between nodes** | In-memory `node_outputs` | External storage (S3/DB) | Durable state | LangChain state dict |
| **Determinism** | ✅ Strong | ✅ Strong | ✅ Strong | ❌ LLM-dependent |
| **Agent-aware routing** | ✅ Complexity + capability | ❌ None | ❌ None | ⚠️ Limited |
| **Retry + circuit breaker** | ✅ Per-node | ✅ Task-level | ✅ Activity-level | ❌ Manual |
| **Parallel execution** | ✅ Native (PARALLEL/HYBRID) | ✅ Via executor | ✅ Via signals | ⚠️ Limited |
| **Scheduler** | ❌ None | ✅ Core feature | ✅ Core feature | ❌ None |
| **Time as concept** | ❌ Not present | ✅ Core (DAG dates) | ✅ Core (timers) | ❌ Not present |
| **Observability** | Events + Prometheus + WS + Agentability | UI + logs | UI + traces | Manual |

**Summary:**
- Use **Airflow** when you need time-based pipeline scheduling.
- Use **Temporal** when you need durable workflows with long-running activities.
- Use **LangGraph** when you need LLM-native reasoning graphs.
- Use **AFMX** when you need deterministic, fault-tolerant execution of agent graphs with full observability — and to bridge any of the above through adapters.
