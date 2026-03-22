# Observability

AFMX provides four observability layers: the EventBus, Prometheus metrics, WebSocket streaming, and optional Agentability integration.

---

## 1. EventBus

Every state transition inside the engine emits an `AFMXEvent` on the `EventBus`. Handlers run concurrently; errors in one handler never propagate to the engine.

### Event Types

| EventType | Emitted when |
|---|---|
| `EXECUTION_STARTED` | Matrix execution begins |
| `EXECUTION_COMPLETED` | All nodes finished successfully |
| `EXECUTION_FAILED` | Execution ended with failure |
| `EXECUTION_TIMEOUT` | Global timeout exceeded |
| `NODE_STARTED` | A node begins executing |
| `NODE_COMPLETED` | A node succeeds |
| `NODE_FAILED` | A node reaches terminal failure |
| `NODE_SKIPPED` | A node skipped by edge condition |
| `NODE_RETRYING` | A retry attempt is about to fire |
| `NODE_FALLBACK` | A fallback node was activated |

### Subscribing to events

```python
from afmx.observability.events import EventBus, EventType

bus = EventBus()

# Subscribe to one event type
@bus.subscribe(EventType.NODE_FAILED)
async def on_node_fail(event):
    await alert_pagerduty(
        execution_id=event.execution_id,
        node=event.data.get("node_name"),
        error=event.data.get("error"),
    )

# Subscribe to all events
@bus.subscribe_all
async def on_any(event):
    await metrics_counter.inc(event.type)
```

### AFMXEvent structure

```python
event.type           # EventType enum
event.execution_id   # UUID string
event.matrix_id      # UUID string
event.timestamp      # Unix float
event.data           # Dict with event-specific fields
```

**Event data fields by type:**

| Type | data fields |
|---|---|
| `EXECUTION_STARTED` | `mode`, `node_count` |
| `EXECUTION_COMPLETED` | `duration_ms`, `completed_nodes`, `failed_nodes`, `skipped_nodes`, `matrix_name`, `mode` |
| `EXECUTION_FAILED` | same as COMPLETED + `error` |
| `NODE_STARTED` | `node_id`, `node_name`, `type` |
| `NODE_COMPLETED` | `node_id`, `node_name`, `node_type`, `status`, `duration_ms`, `attempt`, `fallback_used` |
| `NODE_FAILED` | same as NODE_COMPLETED + `error` |
| `NODE_RETRYING` | `node_id`, `node_name`, `attempt`, `error`, `next_backoff_seconds` |
| `NODE_FALLBACK` | `original_node`, `fallback_node` |

---

## 2. Prometheus Metrics

Enable with `AFMX_PROMETHEUS_ENABLED=true`. Scrape at `GET /metrics`.

### Counter metrics

| Metric | Labels | Description |
|---|---|---|
| `afmx_executions_total` | `matrix_name`, `status` | Execution completions |
| `afmx_nodes_total` | `node_type`, `status` | Node completions |
| `afmx_node_retries_total` | `node_id`, `node_name` | Retry attempts |
| `afmx_circuit_breaker_trips_total` | `node_id` | Circuit breaker openings |

### Histogram metrics

| Metric | Labels | Description |
|---|---|---|
| `afmx_execution_duration_seconds` | `matrix_name`, `status` | Full execution wall time |
| `afmx_node_duration_seconds` | `node_type`, `status` | Per-node wall time |

### Gauge metrics

| Metric | Description |
|---|---|
| `afmx_active_executions` | Currently running executions |

### Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: afmx
    static_configs:
      - targets: ['localhost:8100']
    metrics_path: /metrics
    scrape_interval: 15s
```

### Example Grafana queries

```promql
# Execution success rate (5-minute window)
sum(rate(afmx_executions_total{status="COMPLETED"}[5m]))
/ sum(rate(afmx_executions_total[5m]))

# p95 execution latency
histogram_quantile(0.95, rate(afmx_execution_duration_seconds_bucket[5m]))

# Active executions
afmx_active_executions

# Node failure rate by type
sum(rate(afmx_nodes_total{status="FAILED"}[5m])) by (node_type)
```

---

## 3. WebSocket Streaming

Stream live execution events to any WebSocket client.

```
ws://localhost:8100/afmx/ws/stream/{execution_id}
```

**Python client example:**
```python
import asyncio
import json
import websockets

async def stream(execution_id: str):
    uri = f"ws://localhost:8100/afmx/ws/stream/{execution_id}"
    async with websockets.connect(uri) as ws:
        async for msg in ws:
            event = json.loads(msg)
            if event["type"] == "eof":
                break
            if event["type"] == "ping":
                continue
            print(f"  {event['type']:<30} {event.get('data', {})}")

asyncio.run(stream("your-execution-id-here"))
```

**JavaScript client example:**
```javascript
const ws = new WebSocket(`ws://localhost:8100/afmx/ws/stream/${executionId}`)

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.type === 'eof') { ws.close(); return }
  if (msg.type === 'ping') return
  console.log(msg.type, msg.data)
}
```

**Stream lifecycle:**
1. Client connects → server sends `{"type": "connected", ...}`
2. Events arrive as they happen (no buffering delay)
3. On terminal event → server sends `{"type": "eof", ...}` then closes
4. Every 30s of inactivity → server sends `{"type": "ping"}`

If you connect to an already-completed execution, the server sends `eof` immediately.

---

## 4. Webhook Notifications

Configure `AFMX_WEBHOOK_URL` to receive HTTP POST calls on execution events.

```bash
AFMX_WEBHOOK_URL=https://your-server.com/afmx-events
AFMX_WEBHOOK_EVENTS=execution.completed,execution.failed
AFMX_WEBHOOK_SECRET=your-hmac-secret
```

**Payload:**
```json
{
  "event": "execution.completed",
  "execution_id": "550e8400-...",
  "matrix_name": "research-pipeline",
  "status": "COMPLETED",
  "duration_ms": 142.3,
  "completed_nodes": 3,
  "failed_nodes": 0,
  "timestamp": 1710000000.0
}
```

**Signature verification (Python):**
```python
import hmac, hashlib

def verify(secret: str, payload: bytes, signature_header: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
```

The webhook is delivered with header `X-AFMX-Signature: sha256=<hmac>`.

---

## 5. Agentability Integration

Agentability is a separate agent intelligence observatory. When integrated with AFMX, it captures the *why* of every node execution — confidence scores, reasoning chains, token costs, and inter-agent conflicts.

### What maps to what

| AFMX concept | Agentability concept |
|---|---|
| Matrix execution | Session (`session_id = execution_id`) |
| Node execution | Decision (`agent_id = matrix_name.node_name`) |
| Node type TOOL | `DecisionType.EXECUTION` |
| Node type AGENT | `DecisionType.PLANNING` |
| Node type FUNCTION | `DecisionType.ROUTING` |
| Node output | `record_decision(output=...)` |
| Retry attempt | `record_llm_call(finish_reason="retry_N")` |
| Circuit breaker open | `record_conflict(RESOURCE_CONFLICT, severity=0.8)` |
| Constraint violation | `constraints_violated=[...]` |

### Setup (minimal — offline mode)

```bash
# 1. Install
pip install agentability

# 2. Enable in .env
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db

# 3. Restart AFMX
python3.10 -m afmx serve --reload
# → [startup_handlers] Realistic agents loaded — rich dashboard data enabled
# → Health shows: agentability.connected = true
```

### Setup (with live platform)

```bash
# Terminal 1 — AFMX (agentability.db in project root)
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=/home/opc/agentability.db
python3.10 -m afmx serve --reload

# Terminal 2 — Agentability platform (shares same SQLite file)
cd new_project/agentability/Agentability
AGENTABILITY_DB=/home/opc/agentability.db \
  uvicorn platform.api.main:app --host 0.0.0.0 --port 8000

# Terminal 3 — Agentability dashboard
cd new_project/agentability/Agentability/dashboard
VITE_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

### Making data meaningful

The `realistic_handlers.py` in the project root produces rich Agentability data:

```python
# Each realistic agent returns these extra fields that the hook captures:
{
    "confidence": 0.87,          # → Agentability confidence score
    "_llm_meta": {               # → token count + cost
        "model": "gpt-4o",
        "prompt_tokens": 312,
        "completion_tokens": 180,
        "total_tokens": 492,
        "cost_usd": 0.0000074,
    },
    "_reasoning": [              # → reasoning chain
        "Step 1: Parsed input",
        "Step 2: Applied analysis depth",
        "Step 3: Cross-referenced knowledge",
        "Step 4: Calibrated confidence",
    ],
    "_constraints_checked": ["input_not_empty", "model_available"],
    "_constraints_violated": [],  # populated for high-risk scenarios
}
```

`realistic_handlers.py` is auto-loaded by `startup_handlers.py` when found in the project root.

### Running the integration demo

```bash
python demo_agentability.py
```

This fires 4 scenarios designed specifically to produce interesting Agentability data:
- 3-agent research chain (confidence drift across agents)
- 5 concurrent pipelines (throughput + cost metrics)
- 5-agent parallel review with conflict (GOAL_CONFLICT detection)
- Retry chain (LLM call count per attempt)

### Verifying it works

```bash
curl http://localhost:8100/health | python3 -m json.tool
# Should show: "agentability": {"enabled": true, "connected": true, ...}

# After running demo:
curl http://localhost:8000/api/decisions?limit=5 | python3 -m json.tool
# Should show Agentability Decision records with confidence + reasoning
```
