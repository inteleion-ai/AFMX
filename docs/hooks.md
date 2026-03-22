# Hooks

Hooks are middleware functions that fire at specific points in the execution lifecycle. They are isolated — a hook that raises never kills execution.

---

## Hook Types

| Type | When it fires | What you can do |
|---|---|---|
| `PRE_MATRIX` | Before any node runs in the matrix | Set up tracing, validate context, inject globals |
| `POST_MATRIX` | After matrix finishes (success, failure, or timeout) | Audit logging, cleanup, alerting |
| `PRE_NODE` | Before each individual node executes | Enrich `node_input`, inject trace IDs, add auth tokens |
| `POST_NODE` | After each node completes (success or failure) | Audit the result, collect metrics, alert on failures |

---

## HookPayload

Every hook receives and returns a `HookPayload`:

```python
@dataclass
class HookPayload:
    hook_type: HookType         # Which hook type fired
    execution_id: str           # Current execution UUID
    matrix_id: str              # Matrix UUID
    matrix_name: str            # Matrix name

    # Node-level only (None for matrix hooks)
    node: Optional[Node]                # The node about to run / just ran
    node_input: Optional[Dict]          # PRE_NODE: hooks can mutate this
    node_result: Optional[NodeResult]   # POST_NODE: hooks can read this

    # Always available
    context: Optional[ExecutionContext]
    record: Optional[ExecutionRecord]
    metadata: Dict[str, Any]           # Extra data hooks can attach
```

**What hooks CAN mutate:**
- `payload.node_input` (PRE_NODE) — enriched input is passed to the handler
- `payload.context.memory` — shared memory visible to all downstream nodes
- `payload.metadata` — inter-hook communication

**What hooks must NOT mutate:**
- `payload.node` — Node definition is immutable during execution
- `payload.record` counters directly — the engine manages those

---

## Registering Hooks

### Decorator style

```python
from afmx.core.hooks import HookRegistry, HookPayload

hooks = HookRegistry()

@hooks.pre_matrix("setup_tracing")
async def setup_tracing(payload: HookPayload) -> HookPayload:
    import uuid
    trace_id = str(uuid.uuid4())
    payload.context.set_memory("trace_id", trace_id)
    payload.metadata["trace_id"] = trace_id
    return payload

@hooks.post_matrix("audit_matrix", priority=50)
async def audit_matrix(payload: HookPayload) -> HookPayload:
    status = payload.record.status if payload.record else "unknown"
    print(f"[AUDIT] Matrix '{payload.matrix_name}' finished: {status}")
    return payload

@hooks.pre_node("inject_auth")
async def inject_auth(payload: HookPayload) -> HookPayload:
    token = get_auth_token()
    payload.node_input["params"]["auth_token"] = token
    return payload

@hooks.post_node("log_result")
async def log_result(payload: HookPayload) -> HookPayload:
    result = payload.node_result
    if result and result.is_terminal_failure:
        print(f"[ALERT] Node '{result.node_name}' failed: {result.error}")
    return payload
```

### Programmatic style

```python
hooks.register(
    name="my_hook",
    fn=my_async_fn,
    hook_type=HookType.PRE_NODE,
    priority=10,
    node_filter="specific_node_name",  # Only runs for this node
)
```

### Node filter

Run a hook only for a specific node:

```python
@hooks.post_node("alert_on_llm_node", node_filter="llm_call")
async def alert(payload: HookPayload) -> HookPayload:
    # Only fires when payload.node.name == "llm_call" or payload.node.id == "llm_call"
    if payload.node_result and payload.node_result.duration_ms > 5000:
        send_alert(f"LLM call took {payload.node_result.duration_ms:.0f}ms")
    return payload
```

---

## Priority

Lower priority number = runs first. Default = 100.

```python
@hooks.pre_node("first",  priority=10)   # Runs first
@hooks.pre_node("second", priority=50)   # Runs second
@hooks.pre_node("third",  priority=100)  # Runs third (default)
```

---

## Wire Hooks into the Engine

Hooks are attached to the engine via `NodeExecutor`:

```python
from afmx.core.hooks import HookRegistry
from afmx.core.executor import NodeExecutor
from afmx.core.retry import RetryManager
from afmx.core.engine import AFMXEngine
from afmx.observability.events import EventBus

hooks = HookRegistry()

# ... register your hooks ...

bus = EventBus()
rm = RetryManager(event_bus=bus)
executor = NodeExecutor(
    retry_manager=rm,
    hook_registry=hooks,   # ← attach hooks here
)
engine = AFMXEngine(event_bus=bus, node_executor=executor)
```

In the server (`main.py`), the `default_hooks` global registry is pre-wired. Register into it at startup:

```python
from afmx.core.hooks import default_hooks

@default_hooks.post_node("production_audit")
async def prod_audit(payload: HookPayload) -> HookPayload:
    # This runs for every node execution in the server
    ...
    return payload
```

---

## Practical Examples

### Example 1: Trace ID injection

Inject a trace ID into every node's metadata at matrix start, read it in every POST_NODE hook:

```python
@hooks.pre_matrix("inject_trace")
async def inject_trace(payload: HookPayload) -> HookPayload:
    import uuid
    payload.context.set_memory("__trace_id__", str(uuid.uuid4()))
    return payload

@hooks.post_node("audit_with_trace")
async def audit_with_trace(payload: HookPayload) -> HookPayload:
    trace_id = payload.context.get_memory("__trace_id__", "unknown")
    result = payload.node_result
    if result:
        log.info(f"[{trace_id}] {result.node_name}: {result.status} in {result.duration_ms:.1f}ms")
    return payload
```

### Example 2: Dynamic auth token injection

```python
@hooks.pre_node("auth_inject")
async def auth_inject(payload: HookPayload) -> HookPayload:
    if payload.node_input:
        token = await get_fresh_token()  # Refresh token per-node
        payload.node_input["params"]["auth"] = token
    return payload
```

### Example 3: Failure alerting

```python
@hooks.post_node("failure_alert", priority=200)
async def failure_alert(payload: HookPayload) -> HookPayload:
    result = payload.node_result
    if result and result.is_terminal_failure:
        await send_slack_alert(
            channel="#alerts",
            message=(
                f"❌ Node `{result.node_name}` failed in matrix `{payload.matrix_name}`\n"
                f"Error: {result.error}\n"
                f"Execution: {payload.execution_id}"
            )
        )
    return payload
```

### Example 4: Matrix-level resource cleanup

```python
@hooks.post_matrix("cleanup_resources", priority=10)
async def cleanup(payload: HookPayload) -> HookPayload:
    # Runs even if matrix failed — clean up DB connections, temp files, etc.
    session_id = payload.context.get_memory("db_session_id")
    if session_id:
        await close_db_session(session_id)
    return payload
```

### Example 5: Input validation hook

```python
@hooks.pre_node("validate_input", priority=5)
async def validate_input(payload: HookPayload) -> HookPayload:
    raw_input = payload.node_input.get("input") if payload.node_input else None
    if isinstance(raw_input, dict) and "required_field" not in raw_input:
        # Hooks can't raise to kill execution — set a sentinel value instead
        if payload.node_input:
            payload.node_input["params"]["validation_failed"] = True
    return payload
```

---

## Enable/Disable Hooks at Runtime

```python
hooks.disable("audit_with_trace")  # Temporarily disabled
hooks.enable("audit_with_trace")   # Re-enabled

# Check state
for h in hooks.list_hooks():
    print(f"{h['name']}: enabled={h['enabled']}, priority={h['priority']}")
```

**REST:** `GET /afmx/hooks` returns the current hook list.

---

## Hook Isolation

A hook that raises an exception is logged and skipped. The next hook in priority order runs normally. Execution continues regardless.

```python
@hooks.pre_node("buggy_hook")
async def buggy_hook(payload: HookPayload) -> HookPayload:
    raise RuntimeError("This hook is broken")
    # AFMX logs: [HookRegistry] Hook 'buggy_hook' raised RuntimeError: This hook is broken
    # Execution continues — next hook runs, handler runs
```

---

## Matrix vs Node Hook Context

| Field | PRE_MATRIX | POST_MATRIX | PRE_NODE | POST_NODE |
|---|---|---|---|---|
| `execution_id` | ✓ | ✓ | ✓ | ✓ |
| `matrix_id` | ✓ | ✓ | ✓ | ✓ |
| `matrix_name` | ✓ | ✓ | ✓ | ✓ |
| `context` | ✓ | ✓ | ✓ | ✓ |
| `record` | ✓ | ✓ | ✓ | ✓ |
| `node` | ✗ | ✗ | ✓ | ✓ |
| `node_input` | ✗ | ✗ | ✓ (mutable) | ✓ |
| `node_result` | ✗ | ✗ | ✗ | ✓ (read-only) |
