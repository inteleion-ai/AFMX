# Matrix Design

A complete guide to designing effective `ExecutionMatrix` DAGs — modes, edge conditions, abort policies, variable templates, and common patterns.

---

## Matrix Anatomy

```json
{
  "name": "my-pipeline",
  "version": "1.0.0",
  "mode": "SEQUENTIAL",
  "abort_policy": "FAIL_FAST",
  "max_parallelism": 10,
  "global_timeout_seconds": 300,
  "nodes": [ ... ],
  "edges": [ ... ],
  "tags": ["production", "research"]
}
```

| Field | Default | Description |
|---|---|---|
| `name` | `"unnamed-matrix"` | Human-readable identifier |
| `version` | `"1.0.0"` | Used by matrix store versioning |
| `mode` | `SEQUENTIAL` | Execution scheduling strategy |
| `abort_policy` | `FAIL_FAST` | What happens when a node fails |
| `max_parallelism` | `10` | Max concurrent nodes (PARALLEL/HYBRID) |
| `global_timeout_seconds` | `300.0` | Hard timeout wrapping entire matrix |
| `entry_node_id` | `null` | Explicit start node (auto-detected if null) |
| `tags` | `[]` | For filtering in list endpoints |

---

## Execution Modes

### SEQUENTIAL

Nodes execute one at a time. Order is determined by topological sort (Kahn's algorithm). Nodes with equal topological depth are sorted by `priority` (1 = runs first).

```
n1 → n2 → n3
     ↓
     n4
```

Execution order: n1, n2, n3, n4 (or n1, n2, n4, n3 depending on priorities)

**Use when:** Pipeline stages depend on each other's outputs. Conditional routing (some nodes may be skipped). Debugging and predictability.

**JSON:**
```json
{"mode": "SEQUENTIAL"}
```

### PARALLEL

All nodes fire simultaneously under a semaphore. No topological ordering. No edge conditions evaluated.

**Use when:** All nodes are independent. Maximum throughput. Fan-out data enrichment.

```json
{"mode": "PARALLEL", "max_parallelism": 20}
```

### HYBRID

Topological level sets run in parallel. Each batch is a set of nodes with no dependency on each other.

```
Batch 1: [root]
Batch 2: [left, right]       ← run simultaneously
Batch 3: [final]
```

**Use when:** DAG structure with some parallelism. Most complex agent pipelines. Best of both worlds.

```json
{"mode": "HYBRID", "max_parallelism": 10}
```

---

## Abort Policies

### FAIL_FAST (default)

The moment any node reaches FAILED or ABORTED status, the engine:
1. Sets record status to FAILED
2. Marks all remaining nodes as SKIPPED
3. Stops execution

**Use when:** Node failures are blockers. You want fast feedback.

### CONTINUE

The engine runs all independent branches regardless of failures. Final status is `PARTIAL` if any nodes failed.

```json
{"abort_policy": "CONTINUE"}
```

**Use when:** Nodes are independent. Best-effort collection. Logging/audit pipelines where partial results are useful.

Example: Enrich three data sources. If one source fails, return results from the other two.

```
[source_a]  [source_b]  [source_c]   ← all run independently
     ↓            ↓           ↓
              [aggregator]           ← receives whatever succeeded
```

### CRITICAL_ONLY

Functionally equivalent to FAIL_FAST in the current implementation. Intended for future use where specific nodes can be flagged as non-critical.

---

## Node Configuration

### Retry Policy

```json
{
  "retry_policy": {
    "retries": 3,
    "backoff_seconds": 1.0,
    "backoff_multiplier": 2.0,
    "max_backoff_seconds": 60.0,
    "jitter": true
  }
}
```

Backoff delays: 1s, 2s, 4s (with jitter applied as `delay × (0.5 + random × 0.5)`).

`retries=0` means try once with no retry. `retries=3` means up to 4 total attempts.

### Timeout Policy

```json
{
  "timeout_policy": {
    "timeout_seconds": 30.0
  }
}
```

The timeout wraps the **entire retry loop**, not a single attempt. If retries are configured, all attempts must complete within this window.

Minimum: `0.01` seconds (useful in tests).

### Circuit Breaker Policy

```json
{
  "circuit_breaker": {
    "enabled": true,
    "failure_threshold": 5,
    "recovery_timeout_seconds": 60.0,
    "half_open_max_calls": 2
  }
}
```

State machine: CLOSED → OPEN (after 5 failures) → HALF_OPEN (after 60s) → CLOSED (on success).

When OPEN, the node raises `RuntimeError` immediately and the status becomes `ABORTED`.

### Fallback Node

```json
{
  "id": "primary",
  "handler": "primary_handler",
  "fallback_node_id": "backup"
}
```

If `primary` reaches FAILED or ABORTED, the engine immediately executes the `backup` node. If backup succeeds:
- The result is stored under `primary`'s ID
- `node_results["primary"]["metadata"]["fallback_used"] = true`
- Record status reflects the fallback's success

**Important:** Declare an `ON_FAILURE` edge from the primary to the fallback so the sequential loop doesn't execute the fallback node again as a standalone entry node:

```json
{
  "edges": [
    {"from": "primary", "to": "backup", "condition": {"type": "ON_FAILURE"}}
  ]
}
```

---

## Edge Conditions

### ALWAYS (default)

```json
{"from": "n1", "to": "n2"}
```

### ON_SUCCESS

```json
{
  "from": "n1", "to": "n2",
  "condition": {"type": "ON_SUCCESS"}
}
```

### ON_FAILURE

```json
{
  "from": "n1", "to": "error_handler",
  "condition": {"type": "ON_FAILURE"}
}
```

### ON_OUTPUT — value match

```json
{
  "from": "classifier", "to": "urgent_handler",
  "condition": {
    "type": "ON_OUTPUT",
    "output_key": "category",
    "output_value": "urgent"
  }
}
```

`output_key` supports dot notation for nested fields: `"user.role"`, `"results.0.score"`.

### EXPRESSION — Python expression

```json
{
  "from": "scorer", "to": "high_path",
  "condition": {
    "type": "EXPRESSION",
    "expression": "output['confidence'] > 0.85 and output['count'] > 0"
  }
}
```

Available names: `output` (node result), `context` (execution context snapshot). No builtins.

---

## Variable Resolver

Node params support `{{template}}` expressions resolved at execution time against the live context.

### Template Syntax

| Expression | What it resolves to |
|---|---|
| `{{input}}` | Root input value |
| `{{input.field}}` | `context.input["field"]` |
| `{{input.a.b.c}}` | Nested dict traversal |
| `{{node.n1.output}}` | Entire output of node n1 |
| `{{node.n1.output.field}}` | Specific field from node n1's output |
| `{{memory.key}}` | `context.memory["key"]` |
| `{{variables.key}}` | `context.variables["key"]` |
| `{{metadata.key}}` | `context.metadata["key"]` |

### Full-expression params

When a param value is **only** a template, it resolves to the typed value:

```json
{
  "params": {
    "limit": "{{variables.page_size}}"
  }
}
```

If `variables.page_size` is `10` (int), then `params["limit"]` is `10` (int), not `"10"` (str).

### Mixed-string params

When a template is embedded in a string, it resolves via string interpolation:

```json
{
  "params": {
    "message": "Hello {{input.name}}, your query was: {{input.query}}"
  }
}
```

### Nested params

Templates are resolved recursively in nested dicts and lists:

```json
{
  "params": {
    "config": {
      "query": "{{input.search_term}}",
      "filters": ["{{variables.region}}", "active"]
    }
  }
}
```

---

## Common Patterns

### 1. Linear Pipeline

Each node feeds the next. Classic for sequential data transforms.

```json
{
  "nodes": [
    {"id": "fetch",    "handler": "fetcher"},
    {"id": "parse",    "handler": "parser"},
    {"id": "enrich",   "handler": "enricher"},
    {"id": "store",    "handler": "storer"}
  ],
  "edges": [
    {"from": "fetch",  "to": "parse"},
    {"from": "parse",  "to": "enrich"},
    {"from": "enrich", "to": "store"}
  ],
  "mode": "SEQUENTIAL"
}
```

### 2. Fan-Out / Fan-In

One coordinator → multiple parallel workers → one aggregator.

```json
{
  "nodes": [
    {"id": "root",        "handler": "coordinator"},
    {"id": "source_a",    "handler": "fetch_a"},
    {"id": "source_b",    "handler": "fetch_b"},
    {"id": "source_c",    "handler": "fetch_c"},
    {"id": "aggregator",  "handler": "aggregate"}
  ],
  "edges": [
    {"from": "root",      "to": "source_a"},
    {"from": "root",      "to": "source_b"},
    {"from": "root",      "to": "source_c"},
    {"from": "source_a",  "to": "aggregator"},
    {"from": "source_b",  "to": "aggregator"},
    {"from": "source_c",  "to": "aggregator"}
  ],
  "mode": "HYBRID"
}
```

### 3. Conditional Routing

Classifier node sends work to different paths based on output.

```json
{
  "nodes": [
    {"id": "classify",      "handler": "route"},
    {"id": "urgent_path",   "handler": "urgent_handler"},
    {"id": "normal_path",   "handler": "normal_handler"},
    {"id": "error_path",    "handler": "error_handler"}
  ],
  "edges": [
    {
      "from": "classify", "to": "urgent_path",
      "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "urgent"}
    },
    {
      "from": "classify", "to": "normal_path",
      "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "normal"}
    },
    {
      "from": "classify", "to": "error_path",
      "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "error"}
    }
  ],
  "mode": "SEQUENTIAL"
}
```

### 4. Retry with Fallback

Primary node retries automatically. If exhausted, fallback node takes over.

```json
{
  "nodes": [
    {
      "id": "primary",
      "handler": "unreliable_api",
      "fallback_node_id": "backup",
      "retry_policy": {"retries": 3, "backoff_seconds": 1.0}
    },
    {"id": "backup", "handler": "cache_fallback"}
  ],
  "edges": [
    {
      "from": "primary", "to": "backup",
      "condition": {"type": "ON_FAILURE"}
    }
  ],
  "mode": "SEQUENTIAL"
}
```

### 5. Multi-Agent Research Pipeline

```json
{
  "name": "research-pipeline",
  "mode": "HYBRID",
  "nodes": [
    {
      "id": "planner",
      "name": "Research Planner",
      "type": "AGENT",
      "handler": "planner_agent",
      "timeout_policy": {"timeout_seconds": 60.0}
    },
    {
      "id": "searcher",
      "name": "Web Searcher",
      "type": "TOOL",
      "handler": "web_search",
      "config": {"params": {"max_results": 10, "query": "{{node.planner.output.query}}"}}
    },
    {
      "id": "analyst",
      "name": "Data Analyst",
      "type": "AGENT",
      "handler": "analyst_agent"
    },
    {
      "id": "writer",
      "name": "Report Writer",
      "type": "AGENT",
      "handler": "writer_agent"
    }
  ],
  "edges": [
    {"from": "planner",  "to": "searcher"},
    {"from": "planner",  "to": "analyst"},
    {"from": "searcher", "to": "writer"},
    {"from": "analyst",  "to": "writer"}
  ]
}
```

---

## Saving and Reusing Matrices

Named matrices are stored in the MatrixStore and can be executed by name:

```bash
# Save
curl -X POST http://localhost:8100/afmx/matrices \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-pipeline",
    "version": "2.0.0",
    "description": "Production research pipeline",
    "tags": ["production"],
    "definition": { ... }
  }'

# Execute by name (uses latest version)
curl -X POST http://localhost:8100/afmx/matrices/my-pipeline/execute \
  -H "Content-Type: application/json" \
  -d '{"input": {"query": "..."}, "triggered_by": "scheduler"}'

# Execute specific version
curl -X POST http://localhost:8100/afmx/matrices/my-pipeline/execute \
  -d '{"version": "1.0.0", "input": {...}}'
```

---

## Validation

Always validate before execution, especially during development:

```bash
curl -X POST http://localhost:8100/afmx/validate \
  -H "Content-Type: application/json" \
  -d '{"matrix": { ... }}'
```

Response:
```json
{
  "valid": true,
  "errors": [],
  "node_count": 4,
  "edge_count": 3,
  "execution_order": ["planner", "searcher", "analyst", "writer"]
}
```

Common validation errors:
- Edge references node ID that doesn't exist
- `entry_node_id` not found in nodes list
- `fallback_node_id` not found in nodes list
- Cycle detected (DAG required)
