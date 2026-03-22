# Testing

AFMX has a comprehensive test suite with 290+ tests across unit and integration layers. All tests use `pytest` with `asyncio_mode="auto"` — no boilerplate needed.

---

## Test Layout

```
tests/
├── conftest.py                  # Shared fixtures (minimal — each file is self-contained)
├── unit/                        # 18 files, ~250 tests
│   ├── test_node.py             # Node model, NodeResult, RetryPolicy, TimeoutPolicy
│   ├── test_edge.py             # Edge, EdgeCondition, all 5 condition types
│   ├── test_matrix.py           # ExecutionMatrix, topological sort, cycle detection
│   ├── test_execution.py        # ExecutionContext, ExecutionRecord, all status transitions
│   ├── test_executor.py         # NodeExecutor: success, failure, timeout, retry, hooks
│   ├── test_retry.py            # RetryManager, CircuitBreaker, NODE_RETRYING events
│   ├── test_hooks.py            # HookRegistry: priority, isolation, node filter
│   ├── test_dispatcher.py       # AgentDispatcher: all 6 routing paths
│   ├── test_router.py           # ToolRouter: rules, tags, round-robin, default
│   ├── test_concurrency.py      # ConcurrencyManager: acquire, release, timeout rejection
│   ├── test_variable_resolver.py # VariableResolver: all template roots
│   ├── test_state_store.py      # InMemoryStateStore: CRUD, TTL, eviction
│   ├── test_matrix_store.py     # InMemoryMatrixStore: versioning, latest, delete
│   ├── test_checkpoint.py       # CheckpointStore: incremental update, apply_to_context
│   ├── test_plugin_registry.py  # PluginRegistry: decorators, sync, disable/enable
│   ├── test_adapters.py         # All 4 adapters (mocked framework imports)
│   └── test_openai_adapter.py   # OpenAI adapter in depth
└── integration/
    ├── test_engine.py           # AFMXEngine: all modes, policies, hooks, events, fallback
    ├── test_api.py              # FastAPI endpoints via TestClient
    └── test_adapters_integration.py # Adapter → engine execution (mocked frameworks)
```

---

## Running Tests

```bash
# Activate your virtualenv first
source .venv/bin/activate

# Full suite (290+ tests)
python3.10 -m pytest tests/ -v

# Quiet (just pass/fail counts)
python3.10 -m pytest tests/ -q

# With coverage report
python3.10 -m pytest tests/ --cov=afmx --cov-report=term-missing

# Specific file
python3.10 -m pytest tests/unit/test_executor.py -v

# Specific test
python3.10 -m pytest tests/integration/test_engine.py::TestFallbackExecution::test_fallback_node_activates_on_failure -v

# By marker
python3.10 -m pytest tests/ -m unit
python3.10 -m pytest tests/ -m integration
```

---

## Pytest Configuration

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"                      # Every async test is auto-wrapped
asyncio_default_fixture_loop_scope = "function"  # Fresh event loop per test
testpaths = ["tests"]
addopts = ["--tb=short", "--strict-markers", "-q"]
```

**`asyncio_mode = "auto"`** means all `async def test_*` functions run automatically as coroutines. No `@pytest.mark.asyncio` decorator needed (though it's harmless to include it).

**`asyncio_default_fixture_loop_scope = "function"`** gives each test its own event loop. This prevents `asyncio.Semaphore` and `asyncio.Lock` state leaking between tests.

---

## Writing Unit Tests

### Basic async test

```python
import pytest
from afmx.models.node import Node, NodeType

def test_node_creation():
    node = Node(name="test", type=NodeType.FUNCTION, handler="echo")
    assert node.name == "test"
    assert node.handler == "echo"

async def test_async_thing():
    # No @pytest.mark.asyncio needed — asyncio_mode="auto" handles it
    result = await some_async_function()
    assert result == expected
```

### Handler registry cleanup

Always clear `HandlerRegistry` before and after tests that register handlers. Failing to do so causes cross-test pollution since `HandlerRegistry._registry` is a class-level dict (global state):

```python
from afmx.core.executor import HandlerRegistry

@pytest.fixture(autouse=True)
def clean_registry():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()
```

### Testing NodeExecutor

```python
from afmx.core.executor import NodeExecutor, HandlerRegistry
from afmx.core.retry import RetryManager
from afmx.models.node import Node, NodeType, NodeStatus
from afmx.models.execution import ExecutionContext

@pytest.fixture(autouse=True)
def clean():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()

async def test_my_handler_succeeds():
    async def my_handler(inp, ctx, node):
        return {"result": inp["input"] * 2}

    HandlerRegistry.register("double", my_handler)

    executor = NodeExecutor(retry_manager=RetryManager())
    node = Node(id="n1", name="n1", type=NodeType.FUNCTION, handler="double")
    ctx = ExecutionContext(input=21)

    result = await executor.execute(node, ctx)

    assert result.status == NodeStatus.SUCCESS
    assert result.output == {"result": 42}
    assert result.attempt == 1
    assert result.duration_ms is not None
```

### Testing with the engine

```python
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry
from afmx.models.matrix import ExecutionMatrix, ExecutionMode
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.observability.events import EventBus

@pytest.fixture(autouse=True)
def clean():
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()

async def test_engine_sequential():
    async def echo(inp, ctx, node):
        return {"echo": inp["input"]}

    HandlerRegistry.register("echo", echo)

    engine = AFMXEngine(event_bus=EventBus())
    from afmx.models.node import Node, NodeType
    n = Node(id="n1", name="n1", type=NodeType.FUNCTION, handler="echo")
    matrix = ExecutionMatrix(nodes=[n], mode=ExecutionMode.SEQUENTIAL)
    ctx = ExecutionContext(input="hello")
    record = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)

    result = await engine.execute(matrix, ctx, record)

    assert result.status == ExecutionStatus.COMPLETED
    assert result.completed_nodes == 1
    assert result.node_results["n1"]["output"] == {"echo": "hello"}
```

### Testing event emission

```python
from afmx.observability.events import EventBus, EventType

async def test_events_emitted():
    bus = EventBus()
    captured = []

    async def capture(event):
        captured.append(event.type)

    bus.subscribe_all(capture)

    engine = AFMXEngine(event_bus=bus)
    # ... execute matrix ...

    assert EventType.EXECUTION_STARTED in captured
    assert EventType.EXECUTION_COMPLETED in captured
    assert EventType.NODE_STARTED in captured
```

---

## Writing Integration Tests (API)

Use FastAPI's `TestClient` (synchronous) for API tests. The `TestClient` handles the lifespan (startup/shutdown) automatically.

```python
from fastapi.testclient import TestClient
from afmx.main import app, afmx_app
from afmx.core.executor import HandlerRegistry

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module", autouse=True)
def register_handlers():
    async def echo(inp, ctx, node):
        return {"result": inp["input"]}
    HandlerRegistry.register("echo", echo)

def test_execute_endpoint(client):
    resp = client.post("/afmx/execute", json={
        "matrix": {
            "name": "test",
            "nodes": [{"id": "n1", "name": "n1", "type": "FUNCTION", "handler": "echo"}],
            "edges": [],
        },
        "input": "hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
```

---

## Real-Time Test Scripts

These scripts run against a **live server** at `http://localhost:8100`:

### Python async test suite

```bash
# Install dependencies
pip install httpx websockets

# Start server in one terminal
python3.10 -m afmx serve --reload

# Run tests in another terminal
python3.10 scripts/test_realtime.py
python3.10 scripts/test_realtime.py --url http://your-server:8100
```

**Covers (17 sections, 50+ assertions):** health, validate, single-node, 3-node chain, parallel, hybrid DAG, variable resolver, conditional routing, retry (flaky), CONTINUE→PARTIAL, async+poll, named matrices, list/filter, cancel, concurrency stats, adapters, error cases (422/404/400).

### curl test suite

```bash
bash scripts/test_api.sh
```

Same coverage as the Python suite but via raw curl. Easier to inspect raw JSON.

### WebSocket streaming demo

```bash
python3.10 scripts/test_ws.py
```

Three demos: stream a pipeline, stream retry events (`NODE_RETRYING`), connect before execution starts.

### Load test

```bash
# Default: 10 concurrent, 50 total
python3.10 scripts/test_load.py

# Stress test
python3.10 scripts/test_load.py --concurrency 20 --total 200

# Custom server
python3.10 scripts/test_load.py --url http://prod-server:8100 --concurrency 50 --total 500
```

Reports: wall time, throughput (req/s), p50/p95/p99 latency, per-status counts.

---

## Test Markers

```bash
# Run only unit tests (no server required)
pytest tests/ -m unit

# Run only integration tests
pytest tests/ -m integration

# Skip slow tests
pytest tests/ -m "not slow"
```

Define custom markers in `pyproject.toml` under `[tool.pytest.ini_options] markers`.

---

## Coverage

```bash
# Generate coverage report
pytest tests/ --cov=afmx --cov-report=term-missing --cov-report=html

# Open HTML report
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

Current coverage target: **70%** (enforced in CI via `fail_under = 70` in `pyproject.toml`).

Key modules with high coverage: `core/engine.py`, `core/executor.py`, `core/retry.py`, `models/*.py`.

---

## Common Test Pitfalls

**Stale handler registrations across tests**  
Every test file that registers handlers must clear `HandlerRegistry` with an `autouse` fixture. Shared handlers cause non-deterministic test ordering failures.

**asyncio primitive creation in `__init__`**  
`asyncio.Semaphore()` and `asyncio.Lock()` must not be created outside a running event loop. Use lazy initialization (see `ConcurrencyManager`).

**Session-scoped event_loop fixture**  
This was deprecated in `pytest-asyncio >= 0.21` and removed. Do not add a custom `event_loop` fixture — `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` is the correct approach.

**TestClient vs async**  
FastAPI's `TestClient` is synchronous. Don't use `asyncio.run()` or `await` inside `TestClient` tests. For async API tests, use `httpx.AsyncClient` instead.
