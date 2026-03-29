"""
AFMX Application Bootstrap — complete production wiring

Startup sequence:
  1.  EventBus
  2.  Metrics (Prometheus) — wired to event bus
  3.  StreamManager — wired to event bus
  4.  Stores resolved (memory | redis): state, matrix, checkpoint, audit, api_key
  5.  Webhook notifier — wired to event bus (when AFMX_WEBHOOK_URL is set)
  6.  RetryManager — wired to event bus (NODE_RETRYING, CIRCUIT_BREAKER_* events)
  7.  NodeExecutor — wired: hooks + variable resolver + checkpoint_store
  8.  AFMXEngine
  9.  Startup handlers — registered to both HandlerRegistry + PluginRegistry
 10.  Plugin registry synced to HandlerRegistry
 11.  Adapter registry warmed
 12.  Agentability observability integration (when AFMX_AGENTABILITY_ENABLED=true)
 13.  RBAC bootstrap key created (when AFMX_RBAC_ENABLED and no keys exist)
 14.  Audit: server.started event written
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Optional, Union

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from afmx.adapters.registry import AdapterRegistry, adapter_registry
from afmx.api.adapter_routes import adapter_router
from afmx.api.admin_routes import admin_router
from afmx.api.audit_routes import audit_router
from afmx.api.matrix_routes import matrix_router
from afmx.api.routes import router as afmx_router
from afmx.api.websocket import stream_manager, ws_router
from afmx.audit.model import AuditAction, AuditEvent
from afmx.audit.store import InMemoryAuditStore, RedisAuditStore
from afmx.auth.rbac import APIKey, Role
from afmx.auth.store import InMemoryAPIKeyStore, RedisAPIKeyStore
from afmx.config import settings
from afmx.core.concurrency import ConcurrencyManager
from afmx.core.dispatcher import AgentDispatcher
from afmx.core.engine import AFMXEngine
from afmx.core.executor import NodeExecutor
from afmx.core.hooks import HookRegistry, default_hooks
from afmx.core.retry import RetryManager
from afmx.core.router import ToolRouter
from afmx.core.variable_resolver import VariableResolver
from afmx.middleware.logging import LoggingMiddleware
from afmx.middleware.rate_limit import RateLimitMiddleware
from afmx.middleware.rbac import RBACMiddleware
from afmx.observability.events import EventBus, LoggingEventHandler
from afmx.observability.metrics import AFMXMetrics
from afmx.plugins.registry import PluginRegistry, default_registry
from afmx.store.checkpoint import InMemoryCheckpointStore, RedisCheckpointStore
from afmx.store.matrix_store import InMemoryMatrixStore, RedisMatrixStore
from afmx.store.state_store import InMemoryStateStore, RedisStateStore
from afmx.utils.exceptions import AFMXException

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class AFMXApplication:
    """Central container for all AFMX singletons."""

    def __init__(self):
        self.started_at: float = 0.0

        self.event_bus: EventBus = EventBus()
        self.metrics: AFMXMetrics = AFMXMetrics()
        self.tool_router: ToolRouter = ToolRouter()
        self.agent_dispatcher: AgentDispatcher = AgentDispatcher()
        self.hook_registry: HookRegistry = default_hooks
        self.variable_resolver: VariableResolver = VariableResolver()
        self.concurrency_manager: ConcurrencyManager = ConcurrencyManager(
            max_concurrent=settings.MAX_CONCURRENT_EXECUTIONS,
        )
        self._retry_manager = RetryManager(event_bus=self.event_bus)

        self.state_store: Optional[Union[InMemoryStateStore, RedisStateStore]] = None
        self.matrix_store: Optional[Union[InMemoryMatrixStore, RedisMatrixStore]] = None
        self.checkpoint_store: Optional[Union[InMemoryCheckpointStore, RedisCheckpointStore]] = None
        self.audit_store: Optional[Union[InMemoryAuditStore, RedisAuditStore]] = None
        self.api_key_store: Optional[Union[InMemoryAPIKeyStore, RedisAPIKeyStore]] = None
        self._node_executor: Optional[NodeExecutor] = None
        self.engine: Optional[AFMXEngine] = None
        self.plugin_registry: PluginRegistry = default_registry
        self.adapter_registry: AdapterRegistry = adapter_registry
        self._agentability_tracer = None

    async def startup(self) -> None:
        self.started_at = time.time()

        if settings.LOG_EVENTS:
            self.event_bus.subscribe_all(LoggingEventHandler())
        if settings.PROMETHEUS_ENABLED:
            self.metrics.attach_to_event_bus(self.event_bus)
        stream_manager.attach_to_event_bus(self.event_bus)

        if settings.STORE_BACKEND == "redis":
            self.state_store      = RedisStateStore(redis_url=settings.REDIS_URL, ttl_seconds=settings.STATE_STORE_TTL_SECONDS, key_prefix=settings.REDIS_KEY_PREFIX)
            self.matrix_store     = RedisMatrixStore(redis_url=settings.REDIS_URL)
            self.checkpoint_store = RedisCheckpointStore(redis_url=settings.REDIS_URL)
            self.audit_store      = RedisAuditStore(redis_url=settings.REDIS_URL)
            self.api_key_store    = RedisAPIKeyStore(redis_url=settings.REDIS_URL)
            logger.info("[AFMX] Store backend: Redis")
        else:
            self.state_store      = InMemoryStateStore(max_records=settings.STATE_STORE_MAX_RECORDS, ttl_seconds=float(settings.STATE_STORE_TTL_SECONDS))
            self.matrix_store     = InMemoryMatrixStore()
            self.checkpoint_store = InMemoryCheckpointStore()
            self.audit_store      = InMemoryAuditStore(max_records=settings.AUDIT_MAX_RECORDS)
            self.api_key_store    = InMemoryAPIKeyStore()
            logger.info("[AFMX] Store backend: InMemory")

        if settings.WEBHOOK_URL:
            from afmx.observability.webhook import WebhookNotifier
            WebhookNotifier(url=settings.WEBHOOK_URL, events=settings.WEBHOOK_EVENTS, secret=settings.WEBHOOK_SECRET, timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS, retries=settings.WEBHOOK_RETRIES).attach_to_event_bus(self.event_bus)

        self._node_executor = NodeExecutor(retry_manager=self._retry_manager, hook_registry=self.hook_registry, variable_resolver=self.variable_resolver, checkpoint_store=self.checkpoint_store)

        # v1.1: Cognitive Model Router — reads cheap/premium model from settings
        from afmx.core.cognitive_router import CognitiveModelRouter
        self._cognitive_router = CognitiveModelRouter(
            cheap_model=settings.COGNITIVE_CHEAP_MODEL,
            premium_model=settings.COGNITIVE_PREMIUM_MODEL,
        )

        self.engine = AFMXEngine(
            tool_router=self.tool_router,
            agent_dispatcher=self.agent_dispatcher,
            event_bus=self.event_bus,
            node_executor=self._node_executor,
            cognitive_router=self._cognitive_router,
        )

        try:
            import afmx.startup_handlers  # noqa: F401
            logger.info("[AFMX] Startup handlers loaded")
        except Exception as exc:
            logger.warning(f"[AFMX] Could not load startup_handlers: {exc}")
        self.plugin_registry.sync_to_handler_registry()

        try:
            loaded = self.adapter_registry.list_adapters()
            logger.info(f"[AFMX] Adapters: {[a['name'] for a in loaded]}")
        except Exception as exc:
            logger.warning(f"[AFMX] Adapter warm-up warning: {exc}")

        if settings.AGENTABILITY_ENABLED:
            try:
                from afmx.integrations.agentability_hook import attach_to_afmx
                self._agentability_tracer = attach_to_afmx(hook_registry=self.hook_registry, event_bus=self.event_bus, db_path=settings.AGENTABILITY_DB_PATH, api_url=settings.AGENTABILITY_API_URL, api_key=settings.AGENTABILITY_API_KEY)
            except Exception as exc:
                logger.error(f"[AFMX] Agentability integration failed: {exc}")

        if settings.RBAC_ENABLED:
            await self._bootstrap_admin_key()

        if settings.AUDIT_ENABLED and self.audit_store:
            try:
                await self.audit_store.append(AuditEvent(action=AuditAction.SERVER_STARTED, actor="system", resource_type="server", resource_id="afmx", outcome="success", details={"version": settings.APP_VERSION, "env": settings.APP_ENV, "store": settings.STORE_BACKEND, "rbac": settings.RBAC_ENABLED, "agentability": settings.AGENTABILITY_ENABLED}))
            except Exception:
                pass

        logger.info(
            f"[AFMX] ✅ Engine online — {settings.APP_NAME} v{settings.APP_VERSION} "
            f"| env={settings.APP_ENV} | store={settings.STORE_BACKEND} "
            f"| rbac={settings.RBAC_ENABLED} | audit={settings.AUDIT_ENABLED} "
            f"| webhooks={'yes' if settings.WEBHOOK_URL else 'no'} "
            f"| agentability={'yes' if settings.AGENTABILITY_ENABLED else 'no'}"
        )

    async def shutdown(self) -> None:
        if self._agentability_tracer is not None:
            try:
                self._agentability_tracer.close()
            except Exception:
                pass
        if settings.AUDIT_ENABLED and self.audit_store:
            try:
                await self.audit_store.append(AuditEvent(action=AuditAction.SERVER_STOPPED, actor="system", resource_type="server", resource_id="afmx", outcome="success"))
            except Exception:
                pass
        logger.info("[AFMX] Shutting down gracefully.")

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    async def _bootstrap_admin_key(self) -> None:
        count = await self.api_key_store.count(active_only=True)
        if count > 0:
            return
        raw_key  = settings.ADMIN_BOOTSTRAP_KEY or f"afmx_{secrets.token_urlsafe(32)}"
        bootstrap = APIKey(key=raw_key, name="admin-bootstrap", role=Role.ADMIN, tenant_id="default", description="Auto-generated bootstrap admin key. Rotate after first use.")
        await self.api_key_store.create(bootstrap)
        print(f"\n╔══════════════════════════════════════════╗\n║  AFMX BOOTSTRAP KEY (shown once)         ║\n║  Key: {bootstrap.key[:40]:<42}║\n╚══════════════════════════════════════════╝\n", flush=True)


afmx_app = AFMXApplication()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await afmx_app.startup()
    yield
    await afmx_app.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AFMX — Agent Flow Matrix Execution Engine. Deterministic · Fault-tolerant · Observable · Framework-agnostic.",
        docs_url="/docs"         if settings.DEBUG else None,
        redoc_url="/redoc"       if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=settings.CORS_ALLOW_CREDENTIALS, allow_methods=settings.CORS_ALLOW_METHODS, allow_headers=settings.CORS_ALLOW_HEADERS)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(LoggingMiddleware)
    if settings.RATE_LIMIT_ENABLED:
        app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.RATE_LIMIT_PER_MINUTE, burst=settings.RATE_LIMIT_BURST)
    app.add_middleware(RBACMiddleware, header_name=settings.API_KEY_HEADER, enabled=settings.RBAC_ENABLED)

    @app.exception_handler(AFMXException)
    async def afmx_exc_handler(request: Request, exc: AFMXException):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": "VALIDATION_ERROR", "message": "Invalid payload", "details": exc.errors()})

    @app.exception_handler(Exception)
    async def general_exc_handler(request: Request, exc: Exception):
        logger.error(f"[AFMX] Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "INTERNAL_SERVER_ERROR", "message": str(exc) if settings.DEBUG else "An unexpected error occurred"})

    app.include_router(afmx_router,    prefix=settings.API_PREFIX, tags=["Execution"])
    app.include_router(matrix_router,  prefix=settings.API_PREFIX, tags=["Matrices"])
    app.include_router(ws_router,      prefix=settings.API_PREFIX, tags=["Streaming"])
    app.include_router(adapter_router, prefix=settings.API_PREFIX, tags=["Adapters"])
    app.include_router(admin_router,   prefix=settings.API_PREFIX, tags=["Admin"])
    app.include_router(audit_router,   prefix=settings.API_PREFIX, tags=["Audit"])

    # ── React SPA ─────────────────────────────────────────────────────────────
    if settings.UI_ENABLED:
        _static = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(_static):
            _assets = os.path.join(_static, "assets")
            if os.path.isdir(_assets):
                app.mount("/assets", StaticFiles(directory=_assets), name="assets")
            app.mount("/afmx/static", StaticFiles(directory=_static), name="static")

        @app.get("/afmx/ui",              include_in_schema=False)
        @app.get("/afmx/ui/{rest:path}",  include_in_schema=False)
        async def ui_spa(rest: str = ""):
            from fastapi.responses import FileResponse
            _dir = os.path.join(os.path.dirname(__file__), "static")
            # Built Vite SPA — index.html is the shell
            for name in ("index.html", "dashboard.html"):
                path = os.path.join(_dir, name)
                if os.path.exists(path):
                    return FileResponse(path, media_type="text/html")
            return JSONResponse(
                status_code=404,
                content={
                    "error": "UI not found",
                    "hint":  "cd afmx/dashboard && npm install && npm run build",
                },
            )

    # ── System endpoints ──────────────────────────────────────────────────────
    @app.get("/health", include_in_schema=False)
    async def health():
        store_count = 0
        try:
            if afmx_app.state_store and hasattr(afmx_app.state_store, "count"):
                store_count = await afmx_app.state_store.count()
        except Exception:
            pass
        return {
            "status":            "healthy",
            "version":           settings.APP_VERSION,
            "environment":       settings.APP_ENV,
            "store_backend":     settings.STORE_BACKEND,
            "uptime_seconds":    round(afmx_app.uptime_seconds, 2),
            "concurrency":       afmx_app.concurrency_manager.get_stats(),
            "active_executions": store_count,
            "adapters":          [a["name"] for a in afmx_app.adapter_registry.list_adapters()],
            "rbac_enabled":      settings.RBAC_ENABLED,
            "audit_enabled":     settings.AUDIT_ENABLED,
            "webhooks_enabled":  bool(settings.WEBHOOK_URL),
            "ui_enabled":        settings.UI_ENABLED,
            "agentability": {
                "enabled":   settings.AGENTABILITY_ENABLED,
                "connected": afmx_app._agentability_tracer is not None,
                "db_path":   settings.AGENTABILITY_DB_PATH if settings.AGENTABILITY_ENABLED else None,
                "api_url":   settings.AGENTABILITY_API_URL,
            },
        }

    @app.get("/afmx/concurrency", tags=["System"])
    async def concurrency_stats():
        return afmx_app.concurrency_manager.get_stats()

    @app.get("/afmx/hooks", tags=["System"])
    async def list_hooks():
        return {"hooks": afmx_app.hook_registry.list_hooks()}

    if settings.PROMETHEUS_ENABLED:
        try:
            from fastapi.responses import Response as FResponse
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            @app.get("/metrics", include_in_schema=False)
            async def prometheus_metrics():
                return FResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except ImportError:
            pass

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name":    settings.APP_NAME,
            "version": settings.APP_VERSION,
            "tagline": "Execution fabric for autonomous agents",
            "docs":    "/docs",
            "health":  "/health",
            "api":     settings.API_PREFIX,
            "ui":      "/afmx/ui" if settings.UI_ENABLED else None,
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "afmx.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
    )
