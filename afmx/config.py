"""
AFMX Configuration
All settings driven by AFMX_ prefixed environment variables or a .env file.

FIX 1: pydantic-settings v2 calls json.loads() on List[str] fields read from
        .env BEFORE field_validators run — comma-separated values like
        "execution.completed,execution.failed" would raise JSONDecodeError.
        Solution: subclass the source classes to override decode_complex_value()
        with a comma-split fallback.

FIX 2 (original): pydantic-settings ≥ 2.4 injects `file_secret_settings` as
        an extra keyword argument into settings_customise_sources().  The old
        explicit signature raised TypeError for an unexpected kwarg.

FIX 3 (this version): some pydantic-settings builds (both older and certain
        2.x patch releases) call settings_customise_sources() WITHOUT passing
        `secrets_settings` as a positional argument at all — so an explicit
        `secrets_settings` parameter raises:
            TypeError: … missing 1 required positional argument: 'secrets_settings'
        Solution: use (*args, **kwargs) to absorb every possible calling
        convention, then extract sources by position with safe defaults.

FIX 4: The source subclass constructors (_CommaDotEnvSource in particular)
        can fail with their own TypeError if the installed version changed the
        DotEnvSettingsSource constructor signature.  Every construction is now
        wrapped in try/except with a clean fallback.

Quick reference:
  AFMX_STORE_BACKEND              memory | redis           (default: memory)
  AFMX_RBAC_ENABLED               true | false             (default: false)
  AFMX_AUDIT_ENABLED              true | false             (default: true)
  AFMX_WEBHOOK_URL                https://...
  AFMX_WEBHOOK_EVENTS             comma-separated events
  AFMX_UI_ENABLED                 true | false             (default: true)
  AFMX_CORS_ORIGINS               comma-separated origins  (default: *)
  AFMX_API_KEYS                   comma-separated keys

  Agentability integration:
  AFMX_AGENTABILITY_ENABLED       true | false             (default: false)
  AFMX_AGENTABILITY_DB_PATH       path to SQLite file      (default: agentability.db)
  AFMX_AGENTABILITY_API_URL       http://localhost:8000    (optional — live export)
  AFMX_AGENTABILITY_API_KEY       key for the platform     (optional)
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple, Type

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# ─── Source class imports — 3-tier fallback ───────────────────────────────────
# pydantic-settings moved these between releases; try newest path first.

_EnvBase = None
_DotEnvBase = None

try:                                                            # ≥ 2.3 layout
    from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource as _DotEnvBase
    from pydantic_settings.sources.providers.env import EnvSettingsSource as _EnvBase
except ImportError:
    pass

if _EnvBase is None or _DotEnvBase is None:
    try:                                                        # < 2.3 layout
        from pydantic_settings import DotEnvSettingsSource as _DotEnvBase  # type: ignore
        from pydantic_settings import EnvSettingsSource as _EnvBase  # type: ignore
    except ImportError:
        pass

# Final fallback — no comma splitting, but the server still boots
if _EnvBase is None:
    _EnvBase = PydanticBaseSettingsSource        # type: ignore
if _DotEnvBase is None:
    _DotEnvBase = PydanticBaseSettingsSource     # type: ignore


# ─── Comma-split helper ───────────────────────────────────────────────────────

def _comma_fallback(value: Any) -> Any:
    """Split 'a,b,c' into ['a', 'b', 'c'] for List[str] fields in .env files."""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        return [v.strip() for v in stripped.split(",") if v.strip()]
    return value


# ─── Comma-aware source subclasses ────────────────────────────────────────────

class _CommaEnvSource(_EnvBase):
    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        try:
            return super().decode_complex_value(field_name, field, value)
        except Exception:
            return _comma_fallback(value)


class _CommaDotEnvSource(_DotEnvBase):
    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        try:
            return super().decode_complex_value(field_name, field, value)
        except Exception:
            return _comma_fallback(value)


# ─── Settings ─────────────────────────────────────────────────────────────────

class AFMXSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AFMX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str    = "AFMX"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str     = "development"
    DEBUG: bool      = True

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str       = "0.0.0.0"
    PORT: int       = 8100
    WORKERS: int    = 1
    API_PREFIX: str = "/afmx"

    # ── Execution Engine ──────────────────────────────────────────────────────
    DEFAULT_GLOBAL_TIMEOUT_SECONDS:    float = 300.0
    DEFAULT_NODE_TIMEOUT_SECONDS:      float = 30.0
    DEFAULT_MAX_PARALLELISM:           int   = 10
    DEFAULT_RETRY_COUNT:               int   = 3
    DEFAULT_RETRY_BACKOFF_SECONDS:     float = 1.0
    DEFAULT_RETRY_BACKOFF_MULTIPLIER:  float = 2.0
    DEFAULT_RETRY_MAX_BACKOFF_SECONDS: float = 60.0
    DEFAULT_RETRY_JITTER:              bool  = True
    MAX_CONCURRENT_EXECUTIONS:         int   = 500
    CONCURRENCY_QUEUE_TIMEOUT_SECONDS: float = 30.0

    # ── State Store ───────────────────────────────────────────────────────────
    STORE_BACKEND:           str = "memory"
    STATE_STORE_TTL_SECONDS: int = 86400
    STATE_STORE_MAX_RECORDS: int = 10_000

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL:        str = "redis://localhost:6379/3"
    REDIS_KEY_PREFIX: str = "afmx:exec:"

    # ── Observability ─────────────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    LOG_LEVEL:          str  = "INFO"
    LOG_EVENTS:         bool = True

    # ── RBAC ──────────────────────────────────────────────────────────────────
    RBAC_ENABLED:        bool          = False
    ADMIN_BOOTSTRAP_KEY: Optional[str] = None
    API_KEY_HEADER:      str           = "X-AFMX-API-Key"

    AUTH_ENABLED: bool      = False
    API_KEYS:     List[str] = Field(default_factory=list)

    # ── Audit ─────────────────────────────────────────────────────────────────
    AUDIT_ENABLED:     bool = True
    AUDIT_MAX_RECORDS: int  = 100_000

    # ── Webhooks ──────────────────────────────────────────────────────────────
    WEBHOOK_URL:             Optional[str] = None
    WEBHOOK_EVENTS:          List[str]     = Field(
        default_factory=lambda: ["execution.completed", "execution.failed"]
    )
    WEBHOOK_SECRET:          Optional[str] = None
    WEBHOOK_TIMEOUT_SECONDS: float         = 10.0
    WEBHOOK_RETRIES:         int           = 3

    # ── UI ────────────────────────────────────────────────────────────────────
    UI_ENABLED: bool = True

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED:    bool = False
    RATE_LIMIT_PER_MINUTE: int  = 120
    RATE_LIMIT_BURST:      int  = 30

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS:           List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool      = False
    CORS_ALLOW_METHODS:     List[str] = ["*"]
    CORS_ALLOW_HEADERS:     List[str] = ["*"]

    # ── v1.1: Cognitive Model Router ─────────────────────────────────────────
    # Controls which LLM model is used at each cognitive layer.
    # Override these to match your deployment (any model string your LLM client accepts).
    COGNITIVE_CHEAP_MODEL:   str = "claude-haiku-4-5-20251001"
    COGNITIVE_PREMIUM_MODEL: str = "claude-opus-4-6"

    # ── Agentability observability integration ────────────────────────────────
    # Set AFMX_AGENTABILITY_ENABLED=true to activate.
    # Requires: pip install agentability   (zero-overhead no-op if missing)
    #
    # Offline mode (default): decisions written to local SQLite file.
    # Online mode: set AFMX_AGENTABILITY_API_URL to push live to the platform.
    #
    # Every AFMX node execution becomes an Agentability Decision.
    # Every AFMX matrix run  becomes an Agentability Session (shared session_id).
    # Circuit breaker trips   become Agentability Conflicts.
    # Retry attempts          appear in the LLM metrics retry_count field.
    AGENTABILITY_ENABLED: bool          = False
    AGENTABILITY_DB_PATH: str           = "agentability.db"
    AGENTABILITY_API_URL: Optional[str] = None   # e.g. http://localhost:8000
    AGENTABILITY_API_KEY: Optional[str] = None

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return v.upper()

    @field_validator("STORE_BACKEND")
    @classmethod
    def validate_store_backend(cls, v: str) -> str:
        if v not in {"memory", "redis"}:
            raise ValueError("STORE_BACKEND must be 'memory' or 'redis'")
        return v

    @field_validator(
        "CORS_ORIGINS", "CORS_ALLOW_METHODS", "CORS_ALLOW_HEADERS",
        "API_KEYS", "WEBHOOK_EVENTS",
        mode="before",
    )
    @classmethod
    def _parse_str_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    # ── Version-agnostic source customisation ─────────────────────────────────

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        *args: Any,
        **kwargs: Any,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Override env + dotenv sources with comma-list-aware versions.

        Uses (*args, **kwargs) instead of explicit parameters so this method
        works across every pydantic-settings release regardless of whether it
        passes sources as positional args, keyword args, or a mix — and
        regardless of which extra sources (file_secret_settings, etc.) it
        injects in future versions.
        """
        def _get(pos: int, name: str) -> Any:
            if pos < len(args):
                return args[pos]
            return kwargs.get(name)

        init_settings    = _get(0, "init_settings")
        env_settings     = _get(1, "env_settings")
        dotenv_settings  = _get(2, "dotenv_settings")
        secrets_settings = _get(3, "secrets_settings")

        env_file = cls.model_config.get("env_file")

        custom_env = env_settings
        try:
            custom_env = _CommaEnvSource(settings_cls)
        except Exception:
            pass

        custom_dotenv = dotenv_settings
        if env_file:
            try:
                custom_dotenv = _CommaDotEnvSource(settings_cls, env_file=env_file)
            except TypeError:
                try:
                    custom_dotenv = _CommaDotEnvSource(settings_cls)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            try:
                custom_dotenv = _CommaDotEnvSource(settings_cls)
            except Exception:
                pass

        sources: list = [init_settings, custom_env, custom_dotenv]
        if secrets_settings is not None:
            sources.append(secrets_settings)
        for key in ("file_secret_settings",):
            extra = kwargs.get(key)
            if extra is not None:
                sources.append(extra)

        return tuple(s for s in sources if s is not None)


settings = AFMXSettings()
