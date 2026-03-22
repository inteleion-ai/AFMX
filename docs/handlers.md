# Writing Handlers

A handler is the unit of logic that AFMX executes. It is an async (or sync) Python function with a specific signature. You write the business logic; AFMX handles retry, timeout, fallback, hooks, and observability.

---

## Handler Signature

Every handler must follow this exact signature:

```python
async def my_handler(node_input: dict, context: ExecutionContext, node: Node) -> Any:
    ...
    return result   # Any JSON-serializable value
```

**Parameters:**

| Parameter | Type | What it contains |
|---|---|---|
| `node_input` | `dict` | All node inputs (see keys below) |
| `context` | `ExecutionContext` | Mutable execution context |
| `node` | `Node` | The node being executed (access config, metadata, etc.) |

**node_input keys:**

```python
node_input["input"]        # The matrix-level input payload (any type)
node_input["params"]       # Resolved node config params ({{templates}} expanded)
node_input["variables"]    # Runtime variables passed to ExecutionContext
node_input["node_outputs"] # Dict[node_id, output] from all previously completed nodes
node_input["memory"]       # Shared memory dict (snapshot at call time)
node_input["metadata"]     # Merged execution metadata + node metadata
```

---

## Basic Examples

### Echo handler (simplest possible)

```python
async def echo_handler(node_input: dict, context, node) -> dict:
    return {
        "echo": node_input["input"],
        "node": node.name,
    }
```

### Read upstream output

```python
async def summarise_handler(node_input: dict, context, node) -> dict:
    # Read output from a node with id "search_node"
    search_results = node_input["node_outputs"].get("search_node", {})
    raw_text = search_results.get("text", "")
    return {"summary": raw_text[:200] + "..."}
```

### Write to shared memory

```python
async def cache_handler(node_input: dict, context, node) -> dict:
    result = compute_expensive_thing(node_input["input"])
    context.set_memory("cached_result", result)
    return {"cached": True, "result": result}

# Later node reads from memory:
async def reader_handler(node_input: dict, context, node) -> dict:
    cached = context.get_memory("cached_result", default=None)
    return {"found": cached is not None, "value": cached}
```

### Use node config params (with template variables)

```python
async def search_handler(node_input: dict, context, node) -> dict:
    params = node_input["params"]
    # params["query"] might be "{{input.search_term}}" resolved to the actual value
    query = params.get("query", "")
    limit = params.get("limit", 10)
    results = my_search_api(query=query, limit=limit)
    return {"results": results, "count": len(results)}
```

Node config in the matrix:
```json
{
  "id": "search",
  "handler": "search_handler",
  "config": {
    "params": {
      "query": "{{input.search_term}}",
      "limit": "{{variables.page_size}}"
    }
  }
}
```

### Sync handler (runs in thread pool)

```python
import time

def slow_sync_handler(node_input: dict, context, node) -> dict:
    # Sync handlers are run in asyncio's ThreadPoolExecutor automatically
    time.sleep(0.1)
    return {"processed": node_input["input"]}
```

---

## Registering Handlers

### Method 1: HandlerRegistry (direct — most common)

```python
from afmx.core.executor import HandlerRegistry

async def my_tool(node_input, context, node):
    return {"done": True}

HandlerRegistry.register("my_tool", my_tool)
```

### Method 2: PluginRegistry (decorator style)

```python
from afmx.plugins.registry import default_registry

@default_registry.tool("web_search", description="Search the web", tags=["search"])
async def web_search(node_input, context, node):
    query = node_input["input"]
    return {"results": search(query)}

@default_registry.agent("analyst", description="Data analyst agent")
async def analyst(node_input, context, node):
    return {"analysis": "..."}

@default_registry.function("transform", description="Transform data")
async def transform(node_input, context, node):
    return node_input["input"]

# Sync plugin registry → HandlerRegistry at startup
default_registry.sync_to_handler_registry()
```

### Method 3: startup_handlers.py (loaded at server startup)

Edit `afmx/startup_handlers.py`:

```python
async def my_custom_handler(node_input: dict, context, node) -> dict:
    return {"custom": True}

def register_all():
    handlers = {
        "my_custom": my_custom_handler,
        # ... existing handlers
    }
    for key, fn in handlers.items():
        HandlerRegistry.register(key, fn)

register_all()
```

This file is imported automatically during server startup.

### Method 4: Dotted module path (no registration required)

```python
# In your matrix definition:
{
    "handler": "mypackage.tools.search.web_search_handler"
}

# AFMX resolves this via importlib at execution time
# Equivalent to: from mypackage.tools.search import web_search_handler
```

---

## Error Handling

**Do not catch and suppress all exceptions.** Let them propagate — AFMX catches them, classifies them, and records them in NodeResult.

```python
# CORRECT — let exceptions propagate
async def my_handler(node_input, context, node):
    result = call_external_api(node_input["input"])  # Raises on failure
    return result

# WRONG — swallowing exceptions defeats retry and fallback
async def bad_handler(node_input, context, node):
    try:
        return call_external_api(node_input["input"])
    except Exception:
        return None  # AFMX thinks this succeeded
```

**Raising specific exception types:**

| Exception | NodeStatus | Use when |
|---|---|---|
| Any `Exception` subclass | `FAILED` | Normal failures, retryable |
| `RuntimeError` | `ABORTED` | Non-retryable, signal circuit breaker |
| `ImportError` | `FAILED` | Handler resolution failure |

```python
async def strict_handler(node_input, context, node):
    data = node_input["input"]
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")
    if "required_key" not in data:
        raise ValueError("required_key missing from input")
    return process(data)
```

---

## Handler Patterns

### Pattern 1: Fan-in aggregator

Reads from multiple upstream nodes and merges:

```python
async def aggregator(node_input, context, node) -> dict:
    outs = node_input["node_outputs"]
    parts = []
    for node_id, output in outs.items():
        if isinstance(output, dict) and "result" in output:
            parts.append(str(output["result"]))
        else:
            parts.append(str(output))
    return {
        "combined": " | ".join(parts),
        "sources": list(outs.keys()),
    }
```

### Pattern 2: Classifier / router

Returns structured output that drives downstream edge conditions:

```python
async def classifier(node_input, context, node) -> dict:
    text = str(node_input["input"])
    if "error" in text.lower():
        category = "error"
    elif "urgent" in text.lower():
        category = "urgent"
    else:
        category = "normal"
    return {"category": category, "input": text}

# Matrix edges:
# {"from": "classifier", "to": "error_path",  "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "error"}}
# {"from": "classifier", "to": "urgent_path", "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "urgent"}}
# {"from": "classifier", "to": "normal_path", "condition": {"type": "ON_OUTPUT", "output_key": "category", "output_value": "normal"}}
```

### Pattern 3: Stateful accumulator (using memory)

```python
async def accumulate(node_input, context, node) -> dict:
    current = context.get_memory("accumulated", [])
    current.append(node_input["input"])
    context.set_memory("accumulated", current)
    return {"total": len(current), "latest": node_input["input"]}
```

### Pattern 4: External API with retry

The retry is handled by AFMX — just let the exception propagate:

```python
import httpx

async def call_external_api(node_input, context, node) -> dict:
    params = node_input["params"]
    url = params.get("url", "https://api.example.com/data")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params={"q": node_input["input"]})
        response.raise_for_status()  # Raises on 4xx/5xx → triggers retry
        return response.json()

# Node config:
# retry_policy: {retries: 3, backoff_seconds: 1.0, jitter: true}
```

### Pattern 5: Parallel sub-work (within one handler)

```python
async def parallel_enricher(node_input, context, node) -> dict:
    import asyncio
    
    items = node_input["input"].get("items", [])
    
    async def enrich_one(item):
        return {"item": item, "enriched": True}
    
    results = await asyncio.gather(*[enrich_one(item) for item in items])
    return {"results": results, "count": len(results)}
```

---

## Testing Handlers Locally

You can test handlers without the server:

```python
import asyncio
from afmx.models.execution import ExecutionContext
from afmx.models.node import Node, NodeType

async def test_my_handler():
    from myapp.handlers import my_handler

    # Build minimal context
    ctx = ExecutionContext(
        input={"query": "test"},
        variables={"page_size": 5},
    )
    
    # Minimal node_input (same shape as what NodeExecutor builds)
    node_input = {
        "input": ctx.input,
        "params": {"limit": 5},
        "variables": ctx.variables,
        "node_outputs": {},
        "memory": {},
        "metadata": {},
    }
    
    # Minimal node
    node = Node(id="test", name="test", type=NodeType.FUNCTION, handler="my_handler")
    
    result = await my_handler(node_input, ctx, node)
    print(result)

asyncio.run(test_my_handler())
```

---

## Realistic Agent Handlers

The project includes `realistic_handlers.py` (project root) which overrides the
stub `analyst_agent`, `writer_agent`, and `reviewer_agent` handlers with
production-grade implementations that produce Agentability-compatible output:

```python
# These extra keys are read by agentability_hook.py and recorded as
# Decision.confidence, Decision.reasoning, LLMMetrics, and constraints:
return {
    "analysis":    "...",
    "confidence":  0.87,              # → Decision.confidence
    "_llm_meta":  {                   # → LLMMetrics record
        "model":             "gpt-4o",
        "prompt_tokens":     312,
        "completion_tokens": 180,
        "total_tokens":      492,
        "cost_usd":          0.0000074,
    },
    "_reasoning": [                   # → Decision.reasoning
        "Step 1: Parsed input",
        "Step 2: Applied analysis depth",
    ],
    "_constraints_checked":  ["input_not_empty"],
    "_constraints_violated": [],      # populated for high-risk inputs
}
```

`realistic_handlers.py` is auto-loaded by `startup_handlers.py` at server
start when the file exists in the project root. No configuration needed.

To use it as a template for your own agents:

```python
# myapp/handlers.py
async def my_agent(node_input: dict, context, node) -> dict:
    # ... call your LLM ...
    return {
        "result":       "...",
        "confidence":   0.85,
        "_llm_meta":    {"model": "gpt-4o", "total_tokens": 400, "cost_usd": 0.000006},
        "_reasoning":   ["Step 1", "Step 2"],
    }
```

---

## Handler Checklist

Before shipping a handler to production:

- [ ] Returns a JSON-serializable value (dict, list, str, int, float, bool, None)
- [ ] Does not swallow exceptions silently
- [ ] Does not mutate `node_input` directly (use context.set_memory for state)
- [ ] Uses `node_input["params"]` for configuration, not hardcoded values
- [ ] Has a unit test using the pattern above
- [ ] Registered with a unique, descriptive key in `HandlerRegistry` or `PluginRegistry`
- [ ] If using Agentability: returns `confidence`, `_llm_meta`, `_reasoning` keys for rich observability
