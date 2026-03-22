# Deployment

Production deployment guide for AFMX — Oracle Cloud Linux, Docker, Redis, and production tuning.

---

## Oracle Cloud Linux (Direct)

This is the primary deployment target — Python 3.10 on Oracle Linux 8/9.

### One-shot setup

```bash
cd /home/opc/afmx

# Auto-detects Python 3.10+, creates venv, installs
bash scripts/setup.sh

# Or manually:
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Start the server (development)

```bash
source .venv/bin/activate
python3.10 -m afmx serve --reload
```

### Start the server (production)

```bash
source .venv/bin/activate

# Multi-worker (requires Redis store backend)
AFMX_STORE_BACKEND=redis \
AFMX_REDIS_URL=redis://localhost:6379/3 \
AFMX_DEBUG=false \
AFMX_APP_ENV=production \
AFMX_LOG_EVENTS=false \
python3.10 -m uvicorn afmx.main:app \
  --host 0.0.0.0 \
  --port 8100 \
  --workers 4 \
  --log-level info \
  --no-access-log
```

### Systemd service

```ini
# /etc/systemd/system/afmx.service
[Unit]
Description=AFMX Agent Flow Matrix Engine
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/afmx
EnvironmentFile=/home/opc/afmx/.env
ExecStart=/home/opc/afmx/.venv/bin/python -m uvicorn afmx.main:app \
    --host 0.0.0.0 \
    --port 8100 \
    --workers 4 \
    --log-level info \
    --no-access-log
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable afmx
sudo systemctl start afmx
sudo systemctl status afmx

# View logs
sudo journalctl -u afmx -f
```

---

## Docker

### Single container

```bash
# Build
docker build -t afmx:latest .

# Run (in-memory store — development only)
docker run -p 8100:8100 afmx:latest

# Run with Redis (production)
docker run -p 8100:8100 \
  -e AFMX_STORE_BACKEND=redis \
  -e AFMX_REDIS_URL=redis://my-redis-host:6379/3 \
  -e AFMX_DEBUG=false \
  -e AFMX_APP_ENV=production \
  afmx:latest
```

### Docker Compose (AFMX + Redis + Prometheus)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f afmx

# Stop
docker-compose down

# Stop and remove volumes (wipes Redis data)
docker-compose down -v
```

Services exposed:
- AFMX API: `http://localhost:8100`
- Redis: `localhost:6379`
- Prometheus: `http://localhost:9090`

### Dockerfile notes

The included Dockerfile uses a **2-stage build**:
1. `builder` — installs dependencies
2. `runtime` — lean image with non-root `afmx` user

Key environment variables set by the Dockerfile (overridable at `docker run`):

```
AFMX_HOST=0.0.0.0
AFMX_PORT=8100
AFMX_APP_ENV=production
AFMX_DEBUG=false
AFMX_LOG_LEVEL=INFO
AFMX_STORE_BACKEND=memory
AFMX_PROMETHEUS_ENABLED=true
```

---

## Redis Backend

Redis is required for production deployments with multiple workers, horizontal scaling, or state persistence across restarts.

### Install Redis (Oracle Linux)

```bash
sudo dnf install redis -y
sudo systemctl enable redis
sudo systemctl start redis
redis-cli ping   # Should return PONG
```

### Redis database layout

| DB | Key prefix | Store | TTL |
|---|---|---|---|
| 3 | `afmx:exec:` | ExecutionRecord (state store) | 24 hours |
| 4 | `afmx:ckpt:` | Checkpoint (per-node resume state) | 7 days |
| 5 | `afmx:matrix:` | Named matrix definitions | None (permanent) |

### Redis configuration for AFMX

Add to `/etc/redis/redis.conf`:

```ini
# Memory limit — evict LRU when full
maxmemory 2gb
maxmemory-policy allkeys-lru

# Persistence — survives restart
save 60 1
save 300 10
save 900 1

# Connection limit
maxclients 1000

# Slow log (queries > 100ms)
slowlog-log-slower-than 100000
```

### Redis with password

```ini
requirepass your-strong-password-here
```

```bash
# In .env or environment
AFMX_REDIS_URL=redis://:your-strong-password-here@localhost:6379/3
```

### Redis TLS (Redis Cloud, ElastiCache)

```bash
AFMX_REDIS_URL=rediss://user:password@your-redis-endpoint.com:6380/3
```

The `rediss://` scheme enables TLS. The `redis-py` client handles certificate verification automatically.

---

## Production Checklist

### Security

- [ ] `AFMX_DEBUG=false` — disables Swagger UI, generic error messages
- [ ] `AFMX_AUTH_ENABLED=true` with strong API keys set in `AFMX_API_KEYS`
- [ ] `AFMX_CORS_ORIGINS` set to specific domains, not `*`
- [ ] Redis password configured
- [ ] Run as non-root user (Docker image already does this)
- [ ] Firewall: only port 8100 exposed externally (Redis/Prometheus on internal network)

### Performance

- [ ] `AFMX_STORE_BACKEND=redis` (required for multi-worker)
- [ ] `AFMX_WORKERS=4` (or number of CPU cores)
- [ ] `AFMX_LOG_EVENTS=false` (reduces log volume in high-throughput scenarios)
- [ ] `AFMX_LOG_LEVEL=WARNING` (production — only warnings and above)
- [ ] `AFMX_MAX_CONCURRENT_EXECUTIONS` tuned for your workload
- [ ] Redis `maxmemory` set to prevent OOM

### Observability

- [ ] Prometheus scraping `http://afmx-host:8100/metrics`
- [ ] Alert on `afmx_active_executions` approaching `max_concurrent`
- [ ] Alert on `rate(afmx_executions_total{status="failed"}[5m])` spike
- [ ] Alert on `histogram_quantile(0.95, rate(afmx_execution_duration_seconds_bucket[5m]))` > SLA

### Reliability

- [ ] Systemd service with `Restart=always`
- [ ] Redis persistence enabled (`save` directives)
- [ ] Health check endpoint monitored by load balancer: `/health`
- [ ] `global_timeout_seconds` set on all matrices to prevent zombie executions

---

## Dashboard Deployment

The React SPA must be built once before the server can serve it:

```bash
cd afmx/dashboard
npm install
npm run build   # outputs to afmx/static/ — FastAPI serves at /afmx/ui
```

The build is included in the Docker image when you run `docker build` — the
`Dockerfile` runs `npm run build` in the builder stage.

For live development (with hot reload against a running AFMX server):

```bash
cd afmx/dashboard
npm run dev     # http://localhost:5173, proxies /afmx/* to :8100
```

---

## Agentability Co-Deployment

Deploy AFMX and Agentability on the same server sharing one SQLite file:

```bash
# /etc/systemd/system/agentability.service
[Unit]
Description=Agentability Platform API
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/agentability/Agentability
Environment=AGENTABILITY_DB=/home/opc/afmx/agentability.db
Environment=AGENTABILITY_CORS_ORIGINS=http://your-server:3000,http://your-server:8100
ExecStart=/home/opc/.venv/bin/uvicorn platform.api.main:app \
    --host 0.0.0.0 --port 8000 --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

In AFMX `.env`:
```bash
AFMX_AGENTABILITY_ENABLED=true
AFMX_AGENTABILITY_DB_PATH=/home/opc/afmx/agentability.db
```

Both services use the same absolute path. No network hop. No extra Redis DB.

---

## Nginx Reverse Proxy

```nginx
upstream afmx {
    server localhost:8100;
}

server {
    listen 443 ssl;
    server_name afmx.mycompany.com;

    ssl_certificate     /etc/ssl/certs/afmx.crt;
    ssl_certificate_key /etc/ssl/private/afmx.key;

    # Regular HTTP
    location / {
        proxy_pass http://afmx;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 310s;  # > global_timeout_seconds
        proxy_send_timeout 310s;
    }

    # WebSocket support
    location /afmx/ws/ {
        proxy_pass http://afmx;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;  # Keep WS alive for long executions
    }
}
```

---

## Scaling

### Vertical (single machine)

Increase `AFMX_WORKERS` and Redis memory. 4 workers on 4-core Oracle VM is a good baseline.

### Horizontal (multiple machines)

All machines must share the same Redis instance. Use a load balancer (Nginx, HAProxy) in front. WebSocket connections must be sticky (same client → same AFMX instance) since the `StreamManager` queue is in-process memory.

```
                    ┌─────────────────┐
Client ──────────► │  Load Balancer   │
                    │   (sticky WS)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌─────────┐  ┌─────────┐  ┌─────────┐
         │ AFMX 1  │  │ AFMX 2  │  │ AFMX 3  │
         └────┬────┘  └────┬────┘  └────┬────┘
              │             │             │
              └─────────────┴─────────────┘
                             │
                      ┌──────┴──────┐
                      │    Redis    │
                      └─────────────┘
```

---

## Environment Variables for Production

Minimal production `.env`:

```bash
# Application
AFMX_APP_ENV=production
AFMX_DEBUG=false

# Server
AFMX_HOST=0.0.0.0
AFMX_PORT=8100
AFMX_WORKERS=4

# Store
AFMX_STORE_BACKEND=redis
AFMX_REDIS_URL=redis://:strongpassword@localhost:6379/3

# Observability
AFMX_LOG_LEVEL=WARNING
AFMX_LOG_EVENTS=false
AFMX_PROMETHEUS_ENABLED=true

# Auth
AFMX_AUTH_ENABLED=true
AFMX_API_KEYS=key-prod-1,key-prod-2

# CORS
AFMX_CORS_ORIGINS=https://app.mycompany.com

# Concurrency
AFMX_MAX_CONCURRENT_EXECUTIONS=500
AFMX_CONCURRENCY_QUEUE_TIMEOUT_SECONDS=30
```
