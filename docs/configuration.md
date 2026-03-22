# Configuration

All AFMX configuration is driven by environment variables with the `AFMX_` prefix.
Values can be set in a `.env` file (auto-loaded), shell environment, or Docker.
Pydantic-settings handles parsing, validation, and type coercion.

```bash
# .env file
AFMX_STORE_BACKEND=redis
AFMX_REDIS_URL=redis://localhost:6379/3
AFMX_LOG_LEVEL=DEBUG

# Shell (overrides .env)
export AFMX_MAX_CONCURRENT_EXECUTIONS=1000

# Docker
docker run -e AFMX_STORE_BACKEND=redis -e AFMX_REDIS_URL=redis://redis:6379/3 afmx:latest
```

Settings are case-insensitive. `AFMX_log_level=debug` and `AFMX_LOG_LEVEL=DEBUG` are equivalent.

---

## Application

| Variable | Default | Description |
|---|---|---|
| `AFMX_APP_NAME` | `AFMX` | Shown in health response and logs |
| `AFMX_APP_VERSION` | `1.0.0` | Version string |
| `AFMX_APP_ENV` | `development` | `development` · `staging` · `production` |
| `AFMX_DEBUG` | `true` | Enables `/docs`, `/redoc`, `/openapi.json`; verbose errors |

**Production:** `AFMX_DEBUG=false` + `AFMX_APP_ENV=production` disables the Swagger UI and returns generic error messages.

---

## Server

| Variable | Default | Description |
|---|---|---|
| `AFMX_HOST` | `0.0.0.0` | Bind address |
| `AFMX_PORT` | `8100` | Listen port |
| `AFMX_WORKERS` | `1` | Uvicorn worker processes (> 1 requires Redis store) |
| `AFMX_API_PREFIX` | `/afmx` | URL prefix for all API routes |

Multiple workers share state only via Redis. The in-memory store is per-process.

---

## Execution Engine Defaults

| Variable | Default | Description |
|---|---|---|
| `AFMX_DEFAULT_GLOBAL_TIMEOUT_SECONDS` | `300.0` | Matrix-level timeout when not specified in definition |
| `AFMX_DEFAULT_NODE_TIMEOUT_SECONDS` | `30.0` | Per-node timeout |
| `AFMX_DEFAULT_MAX_PARALLELISM` | `10` | Concurrent nodes in PARALLEL/HYBRID mode |
| `AFMX_DEFAULT_RETRY_COUNT` | `3` | Node retries before terminal failure |
| `AFMX_DEFAULT_RETRY_BACKOFF_SECONDS` | `1.0` | Base backoff delay |
| `AFMX_DEFAULT_RETRY_BACKOFF_MULTIPLIER` | `2.0` | Exponential multiplier (1s → 2s → 4s) |
| `AFMX_DEFAULT_RETRY_MAX_BACKOFF_SECONDS` | `60.0` | Backoff ceiling |
| `AFMX_DEFAULT_RETRY_JITTER` | `true` | ±25% random jitter on backoff delays |
| `AFMX_MAX_CONCURRENT_EXECUTIONS` | `500` | Global semaphore cap (across all matrices) |
| `AFMX_CONCURRENCY_QUEUE_TIMEOUT_SECONDS` | `30.0` | Wait time before returning HTTP 503 |

**Note:** `DEFAULT_*` engine variables document the values used in `startup_handlers.py`. Per-matrix and per-node values are set in the matrix definition itself and override these defaults.

---

## State Store

| Variable | Default | Description |
|---|---|---|
| `AFMX_STORE_BACKEND` | `memory` | `memory` or `redis` |
| `AFMX_STATE_STORE_TTL_SECONDS` | `86400` | Execution record lifetime (1 day) |
| `AFMX_STATE_STORE_MAX_RECORDS` | `10000` | In-memory eviction threshold |

- **`memory`**: In-process, lost on restart, single-process only. Best for development.
- **`redis`**: Persistent, survives restarts, multi-worker safe. Required for production.

---

## Redis

| Variable | Default | Description |
|---|---|---|
| `AFMX_REDIS_URL` | `redis://localhost:6379/3` | Connection URL |
| `AFMX_REDIS_KEY_PREFIX` | `afmx:exec:` | Key prefix in state store |

**Database allocation (defaults):**

| DB | Store |
|---|---|
| 3 | StateStore (execution records) |
| 4 | CheckpointStore (per-node checkpoints) |
| 5 | MatrixStore (named matrix definitions) |

```bash
# Connection URL formats
redis://localhost:6379/3                          # no auth
redis://:password@localhost:6379/3               # password only
redis://user:password@localhost:6379/3           # Redis 6+ ACL
rediss://user:password@redis-endpoint:6380/3     # TLS (ElastiCache, Redis Cloud)
```

---

## Observability

| Variable | Default | Description |
|---|---|---|
| `AFMX_PROMETHEUS_ENABLED` | `true` | Metrics at `GET /metrics` |
| `AFMX_LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` · `CRITICAL` |
| `AFMX_LOG_EVENTS` | `true` | Log every EventBus event (set `false` in high-throughput prod) |

---

## Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `AFMX_RATE_LIMIT_ENABLED` | `false` | Per-IP token-bucket rate limiting |
| `AFMX_RATE_LIMIT_PER_MINUTE` | `120` | Sustained request rate |
| `AFMX_RATE_LIMIT_BURST` | `30` | Initial burst capacity |

Rate-limited requests receive `HTTP 429` with `Retry-After: 60`.
Exempt: `/health`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`, `/`.

---

## CORS

| Variable | Default | Description |
|---|---|---|
| `AFMX_CORS_ORIGINS` | `["*"]` | Allowed origins (comma-separated or JSON array) |
| `AFMX_CORS_ALLOW_CREDENTIALS` | `false` | Allow cookies/credentials |
| `AFMX_CORS_ALLOW_METHODS` | `["*"]` | Allowed HTTP methods |
| `AFMX_CORS_ALLOW_HEADERS` | `["*"]` | Allowed request headers |

```bash
# Production
AFMX_CORS_ORIGINS=https://app.mycompany.com,https://admin.mycompany.com
AFMX_CORS_ALLOW_CREDENTIALS=true
```

---

## RBAC (Role-Based Access Control)

| Variable | Default | Description |
|---|---|---|
| `AFMX_RBAC_ENABLED` | `false` | Enable API key enforcement |
| `AFMX_API_KEY_HEADER` | `X-AFMX-API-Key` | Header name |
| `AFMX_ADMIN_BOOTSTRAP_KEY` | (auto-generated) | Bootstrap ADMIN key on first start |

When `AFMX_RBAC_ENABLED=true` and no keys exist, a bootstrap ADMIN key is printed to stdout once on startup. Copy it immediately.

Five roles with 16 permissions:

| Role | Permissions |
|---|---|
| `VIEWER` | `execution:read`, `matrix:read`, `plugin:read`, `metrics:read`, `audit:read` |
| `SERVICE` | `execution:execute`, `execution:read`, `matrix:read`, `matrix:execute` |
| `DEVELOPER` | All SERVICE + `execution:cancel`, `execution:retry`, `execution:resume`, `plugin:read`, `metrics:read` |
| `OPERATOR` | All DEVELOPER + `matrix:write`, `matrix:delete`, `audit:read`, `audit:export` |
| `ADMIN` | All OPERATOR + `admin:read`, `admin:write` |

---

## Audit Log

| Variable | Default | Description |
|---|---|---|
| `AFMX_AUDIT_ENABLED` | `true` | Record all operations to audit store |
| `AFMX_AUDIT_MAX_RECORDS` | `100000` | In-memory eviction threshold |

Audit events are queryable via `GET /afmx/audit` and exportable as JSON, CSV, or NDJSON via `GET /afmx/audit/export/{format}`.

---

## Webhooks

| Variable | Default | Description |
|---|---|---|
| `AFMX_WEBHOOK_URL` | — | HTTP endpoint for event delivery |
| `AFMX_WEBHOOK_EVENTS` | `execution.completed,execution.failed` | Comma-separated event filter |
| `AFMX_WEBHOOK_SECRET` | — | HMAC-SHA256 signing secret (sets `X-AFMX-Signature` header) |
| `AFMX_WEBHOOK_TIMEOUT_SECONDS` | `10` | Per-request timeout |
| `AFMX_WEBHOOK_RETRIES` | `3` | Delivery retry count |

---

## UI Dashboard

| Variable | Default | Description |
|---|---|---|
| `AFMX_UI_ENABLED` | `true` | Serve the React SPA at `/afmx/ui` |

The dashboard is a React 18 SPA built with Vite. Build it once with:
```bash
cd afmx/dashboard && npm install && npm run build
```
The build outputs to `afmx/static/`. FastAPI serves it automatically at `/afmx/ui`.

For dev with hot reload: `npm run dev` → `http://localhost:5173` (proxies API to `:8100`).

---

## Agentability Integration

| Variable | Default | Description |
|---|---|---|
| `AFMX_AGENTABILITY_ENABLED` | `false` | Enable the intelligence observability bridge |
| `AFMX_AGENTABILITY_DB_PATH` | `agentability.db` | SQLite file path (offline mode) |
| `AFMX_AGENTABILITY_API_URL` | — | Agentability platform URL (online mode) |
| `AFMX_AGENTABILITY_API_KEY` | — | API key for platform authentication |

**How it works:** When enabled, every AFMX node execution is captured as an Agentability Decision. The two systems share the same SQLite file in offline mode — zero network overhead, zero extra infrastructure.

```bash
# Minimal setup (offline mode)
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db

# With live platform
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=agentability.db
AFMX_AGENTABILITY_API_URL=http://localhost:8000
AFMX_AGENTABILITY_API_KEY=your-key-here
```

Requires: `pip install agentability`. Zero-overhead no-op if package not installed.

---

## Accessing Settings in Code

```python
from afmx.config import settings

print(settings.STORE_BACKEND)               # "memory" or "redis"
print(settings.PORT)                        # 8100
print(settings.MAX_CONCURRENT_EXECUTIONS)   # 500
print(settings.RBAC_ENABLED)               # False
print(settings.AGENTABILITY_ENABLED)       # False
```

The `settings` singleton is instantiated at import time. To override in tests:
```python
import os
os.environ["AFMX_STORE_BACKEND"] = "redis"
# import afmx.config AFTER setting env vars
```
