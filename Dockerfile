# ─── Build Stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-prod.txt


# ─── Runtime Stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Agentdyne9"
LABEL description="AFMX — Agent Flow Matrix Execution Engine"
LABEL version="1.0.0"

# Non-root user for security
RUN groupadd -r afmx && useradd -r -g afmx afmx

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY afmx/ ./afmx/

# Set ownership
RUN chown -R afmx:afmx /app

USER afmx

# Environment defaults (override via docker run -e or docker-compose)
ENV AFMX_HOST=0.0.0.0 \
    AFMX_PORT=8100 \
    AFMX_APP_ENV=production \
    AFMX_DEBUG=false \
    AFMX_LOG_LEVEL=INFO \
    AFMX_STORE_BACKEND=memory \
    AFMX_PROMETHEUS_ENABLED=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/health')"

CMD ["python", "-m", "uvicorn", "afmx.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8100", \
     "--workers", "4", \
     "--log-level", "info", \
     "--no-access-log"]
