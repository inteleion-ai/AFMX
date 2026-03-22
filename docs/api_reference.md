# API Reference

Base URL: `http://localhost:8100`
All POST/PUT requests: `Content-Type: application/json`
Optional auth header: `X-AFMX-API-Key: <key>` (required when `AFMX_RBAC_ENABLED=true`)

---

## System

### GET /health

Server health, concurrency stats, feature flags, and Agentability status.

**Response 200:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development",
  "store_backend": "memory",
  "uptime_seconds": 142.3,
  "active_executions": 2,
  "concurrency": {
    "active": 2,
    "queued": 0,
    "max_concurrent": 500,
    "utilization_pct": 0.4,
    "total_accepted": 47,
    "total_rejected": 0,
    "total_completed": 45,
    "peak_active": 5
  },
  "adapters": ["langchain", "langgraph", "crewai", "openai"],
  "rbac_enabled": false,
  "audit_enabled": true,
  "webhooks_enabled": false,
  "ui_enabled": true,
  "agentability": {
    "enabled": false,
    "connected": false,
    "db_path": null,
    "api_url": null
  }
}
```

---

### GET /

Root endpoint. Returns service identity and key URLs.

---

### GET /docs

Swagger UI (available only when `AFMX_DEBUG=true`).

---

## Execution

### POST /afmx/execute

Execute a matrix **synchronously**. Blocks until complete. Returns full result including all node outputs.

**Request body:**
```json
{
  "matrix": {
    "name": "research-pipeline",
    "mode": "SEQUENTIAL",
    "nodes": [
      {
        "id": "analyst",
        "name": "analyst",
        "type": "AGENT",
        "handler": "analyst_agent",
        "config": {
          "params": {"depth": "{{variables.depth}}"},
          "tags": []
        },
        "retry_policy": {
          "retries": 3,
          "backoff_seconds": 1.0,
          "backoff_multiplier": 2.0,
          "max_backoff_seconds": 60.0,
          "jitter": true
        },
        "timeout_policy": {"timeout_seconds": 30.0},
        "circuit_breaker": {
          "enabled": false,
          "failure_threshold": 5,
          "recovery_timeout_seconds": 60.0
        },
        "fallback_node_id": null,
        "priority": 5,
        "metadata": {}
      }
    ],
    "edges": [],
    "abort_policy": "FAIL_FAST",
    "max_parallelism": 10,
    "global_timeout_seconds": 300.0
  },
  "input": {"topic": "AI in 2026"},
  "memory": {},
  "variables": {"depth": "thorough"},
  "metadata": {"tenant_id": "acme"},
  "triggered_by": "scheduler",
  "tags": ["production", "research"]
}
```

Only `matrix` is required. All other fields are optional.

**Response 200:**
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "matrix_id": "a3f8b2c1-...",
  "matrix_name": "research-pipeline",
  "status": "COMPLETED",
  "total_nodes": 1,
  "completed_nodes": 1,
  "failed_nodes": 0,
  "skipped_nodes": 0,
  "duration_ms": 45.2,
  "error": null,
  "error_node_id": null,
  "node_results": {
    "analyst": {
      "node_id": "analyst",
      "node_name": "analyst",
      "status": "SUCCESS",
      "output": {
        "analysis": "Comprehensive analysis of: AI in 2026",
        "confidence": 0.87,
        "recommendations": ["action_a", "action_b"]
      },
      "error": null,
      "error_type": null,
      "attempt": 1,
      "duration_ms": 44.1,
      "started_at": 1710000000.001,
      "finished_at": 1710000000.045,
      "metadata": {}
    }
  },
  "queued_at": 1710000000.0,
  "started_at": 1710000000.001,
  "finished_at": 1710000000.046,
  "tags": ["production", "research"]
}
```

**`node_results` fields:**

| Field | Type | Description |
|---|---|---|
| `node_id` | string | Node ID from the matrix definition |
| `node_name` | string | Node name from the matrix definition |
| `status` | enum | `SUCCESS` · `FAILED` · `SKIPPED` · `ABORTED` · `TIMEOUT` · `FALLBACK` |
| `output` | any | Handler return value (JSON-serializable) |
| `error` | string\|null | Error message if failed |
| `error_type` | string\|null | Exception class name |
| `attempt` | int | Which attempt succeeded (1 = first try, 2+ = after retry) |
| `duration_ms` | float\|null | Wall-clock time in milliseconds |
| `started_at` | float\|null | Unix timestamp when node began |
| `finished_at` | float\|null | Unix timestamp when node ended |
| `metadata` | object | e.g. `{"fallback_used": true, "fallback_node_id": "..."}` |

**Error responses:**
- `422` — Invalid matrix definition (Pydantic validation failure)
- `503` — Global concurrency cap reached

---

### POST /afmx/execute/async

Submit execution and return immediately. Poll `/afmx/status/{id}` or stream via WebSocket.

**Request body:** Same as `/afmx/execute`

**Response 202:**
```json
{
  "execution_id": "550e8400-...",
  "status": "QUEUED",
  "message": "Execution queued",
  "poll_url": "/afmx/status/550e8400-...",
  "stream_url": "/afmx/ws/stream/550e8400-..."
}
```

---

### GET /afmx/status/{execution_id}

Lightweight status poll. No node outputs — use `/afmx/result/{id}` when terminal.

**Response 200:**
```json
{
  "execution_id": "550e8400-...",
  "status": "RUNNING",
  "matrix_id": "a3f8b2c1-...",
  "matrix_name": "research-pipeline",
  "total_nodes": 3,
  "completed_nodes": 1,
  "failed_nodes": 0,
  "skipped_nodes": 0,
  "duration_ms": null,
  "error": null,
  "queued_at": 1710000000.0,
  "started_at": 1710000000.001,
  "finished_at": null
}
```

`404` if execution not found.

---

### GET /afmx/result/{execution_id}

Full execution result with all node outputs. Same shape as `POST /afmx/execute` response.

`404` if execution not found.

---

### GET /afmx/executions

List recent executions.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 20 | Max results (1–100) |
| `status_filter` | string | — | `COMPLETED` · `FAILED` · `RUNNING` · `PARTIAL` · `TIMEOUT` · `ABORTED` · `QUEUED` |
| `matrix_name` | string | — | Exact name match |

**Response 200:**
```json
{
  "count": 3,
  "executions": [
    {
      "execution_id": "550e8400-...",
      "matrix_name": "research-pipeline",
      "status": "COMPLETED",
      "total_nodes": 3,
      "completed_nodes": 3,
      "failed_nodes": 0,
      "duration_ms": 142.1,
      "queued_at": 1710000000.0,
      "triggered_by": "scheduler",
      "tags": ["production"]
    }
  ]
}
```

---

### POST /afmx/cancel/{execution_id}

Cancel a running execution (best-effort — does not interrupt currently executing nodes).

**Response 200:**
```json
{"message": "Cancellation requested", "status": "ABORTED"}
```

If already terminal:
```json
{"message": "Execution already terminal: COMPLETED", "status": "COMPLETED"}
```

---

### POST /afmx/retry/{execution_id}

Retry a failed or aborted execution with the same matrix and input.

**Response 200:**
```json
{
  "original_execution_id": "550e8400-...",
  "new_execution_id": "661f9511-...",
  "status": "COMPLETED",
  "duration_ms": 38.2
}
```

`404` if not found · `409` if not in terminal state, or was COMPLETED

---

### POST /afmx/validate

Validate a matrix without executing. Returns topological order.

**Request:** `{"matrix": {...}}`

**Response 200:**
```json
{
  "valid": true,
  "errors": [],
  "node_count": 4,
  "edge_count": 3,
  "execution_order": ["planner", "analyst", "writer", "reviewer"]
}
```

---

## Matrix Store

### POST /afmx/matrices

Save a named, versioned matrix.

```json
{
  "name": "research-pipeline",
  "version": "1.0.0",
  "description": "3-agent research chain",
  "tags": ["research"],
  "created_by": "raman",
  "definition": { ... }
}
```

`201` on success · `422` if definition invalid

---

### GET /afmx/matrices

List saved matrices. Query param: `tag` (string filter).

---

### GET /afmx/matrices/{name}

Latest version. Query param: `version` for a specific version.

---

### GET /afmx/matrices/{name}/versions

All versions of a named matrix.

---

### DELETE /afmx/matrices/{name}

Delete all versions. Query param: `version` to delete one version only.

---

### POST /afmx/matrices/{name}/execute

Execute a saved matrix by name. Request body: `input`, `variables`, `metadata`, `triggered_by`, `tags`, `version` (all optional).

---

## WebSocket Streaming

### WS /afmx/ws/stream/{execution_id}

Connect: `ws://localhost:8100/afmx/ws/stream/{execution_id}`

**Protocol — server pushes only:**

```json
{"type": "connected",           "execution_id": "...", "message": "Streaming execution events"}
{"type": "execution.started",   "execution_id": "...", "data": {"mode": "HYBRID", "node_count": 4}}
{"type": "node.started",        "execution_id": "...", "data": {"node_id": "...", "node_name": "analyst", "type": "AGENT"}}
{"type": "node.retrying",       "execution_id": "...", "data": {"node_id": "...", "attempt": 2, "error": "Transient failure #1"}}
{"type": "node.fallback",       "execution_id": "...", "data": {"original_node": "...", "fallback_node": "..."}}
{"type": "node.completed",      "execution_id": "...", "data": {"node_name": "analyst", "duration_ms": 45.2, "status": "SUCCESS"}}
{"type": "node.failed",         "execution_id": "...", "data": {"node_name": "flaky", "error": "...", "attempt": 3}}
{"type": "node.skipped",        "execution_id": "...", "data": {"node_id": "...", "node_name": "n2"}}
{"type": "execution.completed", "execution_id": "...", "data": {"duration_ms": 142.3, "completed_nodes": 3}}
{"type": "execution.failed",    "execution_id": "...", "data": {"error": "...", "failed_nodes": 1}}
{"type": "execution.timeout",   "execution_id": "..."}
{"type": "eof",                 "execution_id": "..."}
{"type": "ping"}
```

`eof` signals the stream is complete. Heartbeat `ping` every 30s of inactivity.

---

## Admin (RBAC required)

### GET /afmx/admin/keys

List all API keys. Requires ADMIN role.

### POST /afmx/admin/keys

Create a new API key.
```json
{
  "name": "ci-pipeline",
  "role": "DEVELOPER",
  "tenant_id": "default",
  "description": "GitHub Actions deploy key",
  "expires_in_days": 90
}
```
Returns `{"key": "afmx_...", "id": "...", "message": "..."}` — key shown once only.

### POST /afmx/admin/keys/{id}/revoke

Revoke a key (blocks immediately, key entry preserved in audit).

### DELETE /afmx/admin/keys/{id}

Permanently delete a key record.

### GET /afmx/admin/stats

Engine stats: version, uptime, store records, audit events, handler count.

---

## Audit

### GET /afmx/audit

Query audit log.

**Query params:** `limit` · `action` · `outcome` (`success`/`failure`/`denied`) · `actor`

### GET /afmx/audit/export/{format}

Export audit log. `format` = `json` · `csv` · `ndjson`.
Returns file download.

---

## Observability

### GET /afmx/concurrency

Live concurrency stats (same object as `health.concurrency`).

### GET /afmx/hooks

List registered hook functions.

### GET /afmx/plugins

List registered handlers grouped by type (tools / agents / functions).

### GET /afmx/adapters

List framework adapters and availability.

### GET /metrics

Prometheus metrics (available when `AFMX_PROMETHEUS_ENABLED=true`).

---

## Error Responses

All errors follow this shape:
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Invalid payload",
  "details": [...]
}
```

| HTTP | Error Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Invalid query param |
| 401 | `UNAUTHORIZED` | Missing or invalid API key |
| 403 | `FORBIDDEN` | Insufficient permissions for role |
| 404 | `NOT_FOUND` | Execution, matrix, or key not found |
| 409 | `CONFLICT` | State conflict (retry on COMPLETED, cancel on terminal) |
| 422 | `VALIDATION_ERROR` | Invalid request body |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 503 | `SERVICE_UNAVAILABLE` | Concurrency cap reached |
| 500 | `INTERNAL_SERVER_ERROR` | Unexpected error |
