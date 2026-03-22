"""
AFMX Utility Helpers
Common utilities used across the AFMX codebase.
"""
from __future__ import annotations
import asyncio
import functools
import hashlib
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def generate_id(prefix: str = "") -> str:
    """Generate a short unique ID with optional prefix."""
    uid = str(uuid.uuid4()).replace("-", "")[:16]
    return f"{prefix}{uid}" if prefix else uid


def now_ms() -> float:
    """Current time in milliseconds."""
    return time.time() * 1000


def elapsed_ms(start: float) -> float:
    """Milliseconds since start (start should be time.time())."""
    return (time.time() - start) * 1000


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dicts. override values win.
    Does not mutate either input.
    """
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def resolve_dotted_path(obj: Any, path: str, default: Any = None) -> Any:
    """
    Navigate a nested object/dict using dot notation.
    e.g. resolve_dotted_path(data, "user.address.city")
    """
    try:
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            else:
                current = getattr(current, part)
        return current
    except (KeyError, AttributeError, TypeError):
        return default


def hash_matrix(matrix_data: Dict[str, Any]) -> str:
    """Compute a stable hash of a matrix definition for deduplication."""
    normalized = json.dumps(matrix_data, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def truncate(value: Any, max_len: int = 500) -> str:
    """Safe string truncation for logging."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + f"... [{len(s) - max_len} chars truncated]"
    return s


def async_retry(
    retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for simple async retry without the full RetryManager.
    Useful for utility functions (store reads, health checks, etc.)
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < retries:
                        await asyncio.sleep(backoff * attempt)
            raise last_exc
        return wrapper  # type: ignore
    return decorator


class Timer:
    """Context manager for timing code blocks."""

    def __init__(self, label: str = "", log: bool = False):
        self.label = label
        self.log = log
        self.start: float = 0.0
        self.end: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.end = time.perf_counter()
        self.elapsed_ms = (self.end - self.start) * 1000
        if self.log:
            logger.debug(f"[Timer] {self.label}: {self.elapsed_ms:.2f}ms")

    async def __aenter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    async def __aexit__(self, *_) -> None:
        self.end = time.perf_counter()
        self.elapsed_ms = (self.end - self.start) * 1000
        if self.log:
            logger.debug(f"[Timer] {self.label}: {self.elapsed_ms:.2f}ms")
