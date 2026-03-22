"""
AFMX Global Concurrency Manager

FIX: asyncio.Semaphore and asyncio.Lock are created lazily on first use,
     NOT in __init__. Creating asyncio primitives outside a running event loop
     is deprecated in Python 3.10+ and raises in 3.12+.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyStats:
    active: int = 0
    queued: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    total_completed: int = 0
    peak_active: int = 0
    last_updated: float = field(default_factory=time.time)


class ConcurrencyManager:
    """
    Global semaphore-based concurrency manager for AFMX.

    asyncio primitives are created on first use (lazy) so this class
    is safe to instantiate at module import time or in __init__.
    """

    def __init__(
        self,
        max_concurrent: int = 500,
        queue_timeout_seconds: float = 30.0,
        per_matrix_cap: int = 0,
    ):
        self._max = max_concurrent
        self._queue_timeout = queue_timeout_seconds
        self._per_matrix_cap = per_matrix_cap
        self._stats = ConcurrencyStats()

        # FIX: asyncio primitives initialized lazily, not here
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._lock: Optional[asyncio.Lock] = None
        self._per_matrix: Dict[str, asyncio.Semaphore] = {}

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max)
        return self._semaphore

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self, execution_id: str, matrix_name: str = "") -> bool:
        lock = self._get_lock()
        semaphore = self._get_semaphore()

        async with lock:
            self._stats.queued += 1
            self._stats.last_updated = time.time()

        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=self._queue_timeout)
        except asyncio.TimeoutError:
            async with lock:
                self._stats.queued -= 1
                self._stats.total_rejected += 1
            logger.warning(
                f"[ConcurrencyManager] '{execution_id}' rejected — "
                f"queue timeout after {self._queue_timeout}s"
            )
            return False

        # Per-matrix cap
        if self._per_matrix_cap > 0 and matrix_name:
            if matrix_name not in self._per_matrix:
                self._per_matrix[matrix_name] = asyncio.Semaphore(self._per_matrix_cap)
            try:
                await asyncio.wait_for(
                    self._per_matrix[matrix_name].acquire(), timeout=5.0,
                )
            except asyncio.TimeoutError:
                semaphore.release()
                async with lock:
                    self._stats.queued -= 1
                    self._stats.total_rejected += 1
                return False

        async with lock:
            self._stats.queued -= 1
            self._stats.active += 1
            self._stats.total_accepted += 1
            if self._stats.active > self._stats.peak_active:
                self._stats.peak_active = self._stats.active
            self._stats.last_updated = time.time()

        logger.debug(
            f"[ConcurrencyManager] Acquired '{execution_id}' "
            f"(active={self._stats.active}/{self._max})"
        )
        return True

    async def release(self, execution_id: str, matrix_name: str = "") -> None:
        semaphore = self._get_semaphore()
        lock = self._get_lock()

        semaphore.release()

        if self._per_matrix_cap > 0 and matrix_name and matrix_name in self._per_matrix:
            self._per_matrix[matrix_name].release()

        async with lock:
            self._stats.active = max(0, self._stats.active - 1)
            self._stats.total_completed += 1
            self._stats.last_updated = time.time()

        logger.debug(
            f"[ConcurrencyManager] Released '{execution_id}' "
            f"(active={self._stats.active}/{self._max})"
        )

    def get_stats(self) -> Dict:
        return {
            "active": self._stats.active,
            "queued": self._stats.queued,
            "max_concurrent": self._max,
            "utilization_pct": round(self._stats.active / self._max * 100, 1),
            "total_accepted": self._stats.total_accepted,
            "total_rejected": self._stats.total_rejected,
            "total_completed": self._stats.total_completed,
            "peak_active": self._stats.peak_active,
        }

    def is_at_capacity(self) -> bool:
        return self._stats.active >= self._max
