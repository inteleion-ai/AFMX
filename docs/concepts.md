# Core Concepts

AFMX has five primitive concepts. Everything else is built from these.

---

## 1. Node

A `Node` is the **atomic unit of execution**. It declares what to run and how to run it safely.

```python
from afmx.models.node import Node, NodeType, RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy

node = Node(
    id="search-1",               # Unique within the matrix
    name="web_search",           # Human-readable label
    type=NodeType.FUNCTION,      # FUNCTION | TOOL | AGENT
    handler="my_search_handler", # Registry key or dotted module path

    # Retry: exponential backoff with optional jitter
    retry_policy=RetryPolicy(
        retries=3,
        backoff_seconds=1.0,
        backoff_multiplier=2.0,  # 1s, 2s, 4s
        max_backoff_seconds=60.0,
        jitter=True,
    ),

    # Timeout: wraps the entire retry loop
    timeout_policy=TimeoutPolicy(
        timeout_seconds=30.0,
        hard_kill=True,
    ),

    # Circuit breaker: trips after N failures, auto-recovers
    circuit_breaker=CircuitBreakerPolicy(
        enabled=True,
        failure_threshold=5,
        recovery_timeout_seconds=60.0,
        half_open_max_calls=2,
    ),

    # Optional: run this node if the primary fails terminally
    fallback_node_id="search-fallback",

    # Priority within a batch (1=highest, 10=lowest, default=5)
    priority=3,

    # Arbitrary metadata passed into node_input["metadata"]
    metadata={"team": "search", "version": "v2"},

    # Node-local config — params support {{template}} variables
    config=NodeConfig(
        params={"max_results": 10, "query": "{{input.query}}"},
        tags=["search"],
    ),
)
```

### Node Types

| Type | Routed through | Typical use |
|---|---|---|
| `FUNCTION` | `HandlerRegistry` directly | Pure Python functions, utilities |
| `TOOL` | `ToolRouter` → `HandlerRegistry` | External APIs, retrieval, data transforms |
| `AGENT` | `AgentDispatcher` → handler | LLM calls, reasoning steps |

If the router/dispatcher can't resolve the handler, the engine falls back to `HandlerRegistry` directly.

### Node Status Lifecycle

```
PENDING → RUNNING → SUCCESS
                  → FAILED      (exception caught, retries exhausted)
                  → ABORTED     (circuit breaker open, or RuntimeError)
                  → SKIPPED     (edge condition not met)
                  → RETRYING    (emitted as event between retry attempts)
                  → FALLBACK    (sentinel — node ran as fallback for another)
```

### NodeResult

Every node execution produces a `NodeResult`:

```python
result.status        # NodeStatus enum value
result.output        # Any JSON-serializable value
result.error         # Error message (if failed)
result.error_type    # Exception class name
result.attempt       # Which attempt succeeded (1 = first try)
result.duration_ms   # Wall clock time in milliseconds
result.metadata      # {"fallback_used": True, ...} if applicable
result.started_at    # Unix timestamp when node began executing
result.finished_at   # Unix timestamp when node finished
result.is_success    # True if status == SUCCESS
result.is_terminal_failure  # True if FAILED or ABORTED
```

---

## 2. Edge

An `Edge` is a **directed connection** between two nodes. Edges are the routing fabric — they declare what executes after what, and under what condition.

```python
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType

# Unconditional
edge = Edge(**{"from": "n1", "to": "n2"})

# Only if n1 succeeded
edge = Edge(**{
    "from": "n1", "to": "n2",
    "condition": EdgeCondition(type=EdgeConditionType.ON_SUCCESS)
})

# Only if n1 failed (error handler / fallback routing)
edge = Edge(**{
    "from": "n1", "to": "error_handler",
    "condition": EdgeCondition(type=EdgeConditionType.ON_FAILURE)
})

# Only if n1's output["category"] == "urgent"
edge = Edge(**{
    "from": "classifier", "to": "urgent_path",
    "condition": EdgeCondition(
        type=EdgeConditionType.ON_OUTPUT,
        output_key="category",      # Dot-notation: "user.role"
        output_value="urgent",
    )
})

# Python expression against {output, context}
edge = Edge(**{
    "from": "scorer", "to": "high_confidence_path",
    "condition": EdgeCondition(
        type=EdgeConditionType.EXPRESSION,
        expression="output['score'] > 0.85",
    )
})
```

### Edge Condition Types

| Type | When edge is traversed |
|---|---|
| `ALWAYS` | Always (default) |
| `ON_SUCCESS` | Upstream node succeeded |
| `ON_FAILURE` | Upstream node failed |
| `ON_OUTPUT` | `output[output_key] == output_value` |
| `EXPRESSION` | Python expression evaluates to `True` |

`EXPRESSION` has no access to builtins. Available names: `output`, `context`, `True`, `False`, `None`.

---

## 3. ExecutionMatrix

An `ExecutionMatrix` is a **DAG of nodes and edges**. It is the complete declaration of a unit of work.

```python
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy

matrix = ExecutionMatrix(
    name="research-pipeline",
    version="1.0.0",
    mode=ExecutionMode.SEQUENTIAL,      # SEQUENTIAL | PARALLEL | HYBRID
    nodes=[analyst_node, writer_node, reviewer_node],
    edges=[
        Edge(**{"from": "analyst", "to": "writer"}),
        Edge(**{"from": "writer",  "to": "reviewer"}),
    ],
    abort_policy=AbortPolicy.FAIL_FAST, # FAIL_FAST | CONTINUE | CRITICAL_ONLY
    max_parallelism=10,                 # PARALLEL/HYBRID concurrency cap
    global_timeout_seconds=300.0,       # Hard timeout for entire matrix
    tags=["research", "agents"],
)
```

### Execution Modes

**SEQUENTIAL** — One node at a time, in topological order (Kahn's algorithm with priority tie-breaking). Edge conditions are evaluated after each node. Unreachable nodes are marked SKIPPED.

**PARALLEL** — All nodes fire concurrently under `max_parallelism` semaphore. No edge conditions. All nodes are independent entry nodes.

**HYBRID** — DAG-derived level batches. Nodes with the same topological depth run in parallel; batches are sequential. Respects edge structure like SEQUENTIAL but gains parallelism where the DAG allows it.

### Abort Policies

| Policy | Behaviour on node failure |
|---|---|
| `FAIL_FAST` | Abort matrix immediately, mark remaining nodes SKIPPED |
| `CONTINUE` | Keep running all independent branches, final status = PARTIAL |
| `CRITICAL_ONLY` | Same as FAIL_FAST (abort on any terminal failure) |

### Validation

`ExecutionMatrix` validates on construction:
- All edge `from`/`to` references must point to real node IDs
- `entry_node_id` must exist if provided
- `fallback_node_id` on any node must exist

```python
# This raises ValidationError immediately — n2 doesn't exist
ExecutionMatrix(
    nodes=[n1],
    edges=[Edge(**{"from": "n1", "to": "n2_nonexistent"})]
)
```

---

## 4. ExecutionContext

`ExecutionContext` is the **mutable state container** that flows between nodes during execution. Every node receives the same context object.

```python
from afmx.models.execution import ExecutionContext

ctx = ExecutionContext(
    input={"query": "AFMX architecture"},  # Initial payload
    memory={},                              # Shared inter-node memory
    variables={"page_size": 10},            # Accessible via {{variables.page_size}}
    metadata={"tenant_id": "acme"},         # Caller-supplied metadata
)

# During execution, handlers can:
ctx.set_memory("processed", True)
ctx.get_memory("processed", default=False)

ctx.set_node_output("analyst", {"summary": "..."})
ctx.get_node_output("analyst")

# Node outputs are also accessible via VariableResolver:
# {{node.analyst.output.summary}} in params
```

**Context fields available inside every handler:**

```python
async def my_handler(node_input: dict, context: ExecutionContext, node: Node) -> Any:
    node_input["input"]        # The matrix-level input payload
    node_input["params"]       # Resolved node config params (templates expanded)
    node_input["variables"]    # Runtime variables dict
    node_input["node_outputs"] # All upstream node outputs keyed by node_id
    node_input["memory"]       # Shared memory snapshot at time of call
    node_input["metadata"]     # Merged execution + node metadata
```

### Variable Resolver

Params support `{{template}}` expressions that are resolved against the context at the moment a node is about to run:

| Expression | Resolves to |
|---|---|
| `{{input}}` | Root input value (any type) |
| `{{input.field.nested}}` | Nested field via dot notation |
| `{{node.node_id.output.field}}` | Specific field from upstream node |
| `{{node.node_id.output}}` | Entire output of upstream node |
| `{{memory.key}}` | Shared memory value |
| `{{variables.key}}` | Runtime variable |
| `{{metadata.key}}` | Execution metadata field |

Full expressions resolve to typed values (int, dict, etc). Mixed expressions interpolate to strings.

---

## 5. ExecutionRecord

An `ExecutionRecord` is the **persisted lifecycle record** of a matrix execution. It is created before execution, updated throughout, and stored in the StateStore.

```python
record.id                 # UUID — the execution_id in API responses
record.matrix_id          # UUID of the ExecutionMatrix
record.matrix_name        # Name string
record.status             # ExecutionStatus enum
record.total_nodes        # Count declared in matrix
record.completed_nodes    # Count that reached SUCCESS
record.failed_nodes       # Count that reached FAILED or ABORTED
record.skipped_nodes      # Count skipped via edge conditions
record.duration_ms        # started_at to finished_at in milliseconds
record.node_results       # Dict[node_id, NodeResult.model_dump()]
record.error              # Error message for FAILED status
record.error_node_id      # Which node caused the FAILED status
record.queued_at          # Unix timestamp when record was created
record.started_at         # Unix timestamp when execution began
record.finished_at        # Unix timestamp when execution ended
record.triggered_by       # Caller identifier
record.tags               # List of string tags
record.is_terminal        # True if status is final
```

### ExecutionStatus Values

| Status | Meaning |
|---|---|
| `QUEUED` | Record created, not yet started |
| `RUNNING` | Execution in progress |
| `COMPLETED` | All nodes succeeded (or fallbacks succeeded) |
| `FAILED` | One or more nodes failed under FAIL_FAST / CRITICAL_ONLY |
| `PARTIAL` | Some nodes failed but CONTINUE policy allowed completion |
| `ABORTED` | Cancelled via API or circuit breaker cascade |
| `TIMEOUT` | Global timeout exceeded |

---

## How the Primitives Connect

```
ExecutionMatrix
  ├── [Node, Node, Node, ...]   ← what to execute
  ├── [Edge, Edge, ...]         ← when and in what order
  ├── mode=HYBRID               ← how to schedule
  └── abort_policy=CONTINUE     ← what to do on failure

          +

ExecutionContext
  ├── input={"query": "..."}    ← initial data
  ├── variables={"k": "v"}      ← injectable into params
  └── memory={}                 ← shared state between nodes

          +

ExecutionRecord
  └── tracks status + results throughout

          ↓

AFMXEngine.execute(matrix, context, record)

          ↓

Per node: handler(node_input, context, node) → output
          output → context.node_outputs[node.id]
          output → record.node_results[node.id]
          output available via {{node.node_id.output}} in next node
```
