# Platform Integrations

AFMX v1.3.0 ships four first-party integrations that connect the execution fabric to
the Agentdyne9 product ecosystem. All integrations use the PRE_NODE / POST_NODE hook
system — they are transparent to your handlers and require zero changes to existing matrices.

---

## HyperState — Cognitive Memory

HyperState is the long-term memory layer for AFMX agents. RETRIEVE-layer nodes
automatically receive relevant memories before execution. REASON, PLAN, and EVALUATE
outputs are persisted back for future runs.

**Install:** `pip install afmx[hyperstate]`

```python
from afmx.integrations.hyperstate import attach_hyperstate

attach_hyperstate(
    api_url="http://localhost:8000",
    api_key="hs_...",
    hook_registry=afmx_app.hook_registry,
    inject_into_memory=True,     # PRE_NODE: inject memories into RETRIEVE nodes
    persist_agent_outputs=True,  # POST_NODE: store REASON/PLAN/EVALUATE outputs back
)
```

### How it works

**PRE_NODE (RETRIEVE layer):** Before any RETRIEVE-layer node executes, AFMX queries
HyperState with the node input as the retrieval query. Retrieved memories are injected
into `node_input["memory"]["hyperstate"]` and `ExecutionContext.memory["hyperstate"]`.

**POST_NODE (REASON / PLAN / EVALUATE layers):** After a premium-tier node completes
successfully, its output is persisted to HyperState tagged with the matrix name, node
name, and execution ID.

### Built-in handlers

These are always available once `attach_hyperstate()` is called:

```python
# Retrieve memories matching a query
Node(handler="hyperstate:retrieve", ...)

# Explicitly store a value
Node(handler="hyperstate:store", ...)
```

### Constructor arguments

```python
attach_hyperstate(
    api_url,                  # HyperState server URL
    api_key,                  # API key
    hook_registry,            # AFMXApplication.hook_registry
    inject_into_memory=True,  # Wire PRE_NODE hook for RETRIEVE nodes
    persist_agent_outputs=True, # Wire POST_NODE hook for REASON/PLAN/EVALUATE
    retrieval_top_k=5,        # Max memories to retrieve per node
    min_relevance_score=0.7,  # Similarity threshold (0–1)
)
```

---

## MAP — Verified Context

MAP (Memory Augmentation Platform) provides SHA-256 verified, provenanced context to
RETRIEVE-layer nodes. Every context unit knows its origin document and position.
Conflicts between context units are detected before the LLM call.

**Install:** `pip install afmx[map]`

```python
from map.service import MAPService
from afmx.integrations.map_plugin import attach_map

map_svc = await MAPService.create(
    api_url="http://map.internal:9000",
    api_key="map_...",
)

await attach_map(
    service=map_svc,
    hook_registry=afmx_app.hook_registry,
    inject_into_memory=True,   # PRE_NODE: inject verified context into RETRIEVE nodes
    verify_outputs=False,      # POST_NODE: verify REASON outputs against stored context
)
```

### How it works

**PRE_NODE (RETRIEVE layer):** MAP queries for `ContextUnit[]` matching the node input.
Each unit is SHA-256 verified on retrieval. Verified units are injected into
`node_input["memory"]["map_context"]`. Conflicting units are logged and excluded.

**`map:retrieve` handler:** Available for explicit retrieval calls.

```python
Node(handler="map:retrieve", config={"params": {"query": "{{input.topic}}"}})
# Returns: {"units": [...], "verified": true, "conflict_count": 0}
```

**`map:verify` handler:** Verify integrity of a specific context unit by ID.

```python
Node(handler="map:verify", config={"params": {"unit_id": "{{input.unit_id}}"}})
# Returns: {"valid": true, "hash_match": true}
```

### Graceful degradation

If the `map-platform` package is not installed, all handlers return a
`{"error": "MAP not available"}` dict instead of raising. This allows matrices to run
without MAP in development environments.

---

## RHFL — Human Governance Gate

RHFL (Responsible Human-in-the-Loop Framework) intercepts every ACT-layer node and
requires human approval before execution. This provides a governance gate for any
action with real-world side effects.

**Install:** No extra install. `httpx` is already a core dependency.

```python
from afmx.integrations.rhfl import attach_rhfl, RHFLBlockedError, RHFLTimeoutError

attach_rhfl(
    api_url="http://rhfl.internal:4000/api/v1",
    token=os.getenv("RHFL_TOKEN"),
    hook_registry=afmx_app.hook_registry,
    gate_act_nodes=True,   # intercept all ACT-layer nodes
    max_wait=300.0,        # seconds before RHFLTimeoutError
    poll_interval=2.0,     # poll interval for REVIEW decisions
)
```

### Decision states

| RHFL Decision | AFMX behaviour |
|---|---|
| `AUTO` | Proceed immediately — no human required |
| `REVIEW` | Poll until approved or rejected (up to `max_wait` seconds) |
| `BLOCK` | Raise `RHFLBlockedError` — node fails, matrix aborts if FAIL_FAST |
| `ESCALATE` | Wait for escalation resolution (up to `max_wait` seconds) |

### Handling errors

```python
from afmx.integrations.rhfl import RHFLBlockedError, RHFLTimeoutError

try:
    record = await engine.execute(matrix, context, record)
except RHFLBlockedError as e:
    print(f"Node blocked by RHFL: {e.node_id} — {e.reason}")
except RHFLTimeoutError as e:
    print(f"RHFL approval timed out after {e.waited_seconds}s")
```

### What RHFL receives

When a node is intercepted, AFMX sends RHFL:

```json
{
  "node_id":      "deploy-to-prod",
  "node_name":    "deploy-to-prod",
  "matrix_name":  "release-pipeline",
  "execution_id": "550e8400-...",
  "cognitive_layer": "ACT",
  "agent_role":   "OPS",
  "input_summary": {"environment": "production", "version": "1.3.0"}
}
```

---

## Agentability — Observability

Agentability captures every AFMX node execution as a structured Decision — including
confidence score, reasoning chain, token count, estimated cost, and constraint violations.

**Install:** `pip install agentability`

```python
from afmx.integrations.agentability_hook import attach_to_afmx

attach_to_afmx(
    hook_registry=afmx_app.hook_registry,
    event_bus=afmx_app.event_bus,
    db_path="agentability.db",      # SQLite file (offline mode)
    api_url="http://localhost:8000", # optional: live platform
    api_key="your-key",             # optional: live platform auth
)
```

### What gets captured

| AFMX event | Agentability record |
|---|---|
| Node execution | Decision (agent_id = `matrix_name.node_name`) |
| Matrix execution | Session (session_id = execution_id) |
| Circuit breaker open | Conflict (ConflictType.RESOURCE_CONFLICT) |
| Retry attempt | LLM metrics (retry_count, finish_reason) |

### Zero-overhead design

The integration installs PRE_NODE and POST_NODE hooks. If the `agentability` package is
not installed, the hooks are registered as no-ops — AFMX starts normally with zero
overhead. There is no conditional import logic in the engine itself.

### Environment variables

```bash
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db
# AFMX_AGENTABILITY_API_URL=http://localhost:8000
# AFMX_AGENTABILITY_API_KEY=your-key
```

---

## Writing a custom integration

All integrations use the standard `HookRegistry` API. No special extension points needed.

```python
from afmx.core.hooks import HookRegistry, HookType, HookPayload
from afmx.models.node import CognitiveLayer

def attach_my_integration(hook_registry: HookRegistry) -> None:
    """Attach a PRE_NODE hook that enriches RETRIEVE-layer nodes."""

    async def my_pre_node_hook(payload: HookPayload) -> HookPayload:
        node = payload.node
        # Only intercept RETRIEVE-layer nodes
        if node.cognitive_layer != CognitiveLayer.RETRIEVE.value:
            return payload

        # Enrich node_input with external data
        external_data = await fetch_external_data(payload.node_input["input"])
        payload.node_input["memory"]["my_integration"] = external_data
        return payload

    hook_registry.register(
        hook_type=HookType.PRE_NODE,
        fn=my_pre_node_hook,
        name="my_integration_pre_node",
        priority=10,   # lower = runs first
    )
```

See [Hooks](hooks.md) for full `HookPayload` field reference.
