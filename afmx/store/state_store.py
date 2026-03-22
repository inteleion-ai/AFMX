"""
AFMX State Store
In-memory + Redis-backed execution state store.
Stores ExecutionRecords and supports status polling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from afmx.models.execution import ExecutionRecord, ExecutionStatus

logger = logging.getLogger(__name__)


class InMemoryStateStore:
    """
    Pure in-memory state store for development and testing.
    Thread-safe via asyncio lock.
    Not suitable for multi-process deployments.
    """

    def __init__(self, max_records: int = 10_000, ttl_seconds: float = 3600.0):
        self._store: Dict[str, ExecutionRecord] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._max_records = max_records
        self._ttl_seconds = ttl_seconds

    async def save(self, record: ExecutionRecord) -> None:
        async with self._lock:
            self._store[record.id] = record
            self._timestamps[record.id] = time.time()
            await self._evict_if_needed()

    async def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        async with self._lock:
            record = self._store.get(execution_id)
            if record is None:
                return None
            ts = self._timestamps.get(execution_id, 0)
            if time.time() - ts > self._ttl_seconds:
                del self._store[execution_id]
                del self._timestamps[execution_id]
                return None
            return record

    async def update_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
        **kwargs: Any,
    ) -> bool:
        async with self._lock:
            record = self._store.get(execution_id)
            if not record:
                return False
            record.status = status
            for k, v in kwargs.items():
                if hasattr(record, k):
                    setattr(record, k, v)
            self._timestamps[execution_id] = time.time()
            return True

    async def list_recent(
        self,
        limit: int = 50,
        status_filter: Optional[ExecutionStatus] = None,
    ) -> List[ExecutionRecord]:
        async with self._lock:
            records = list(self._store.values())
            if status_filter:
                records = [r for r in records if r.status == status_filter]
            records.sort(key=lambda r: r.queued_at, reverse=True)
            return records[:limit]

    async def delete(self, execution_id: str) -> bool:
        async with self._lock:
            existed = execution_id in self._store
            self._store.pop(execution_id, None)
            self._timestamps.pop(execution_id, None)
            return existed

    async def count(self) -> int:
        async with self._lock:
            return len(self._store)

    async def _evict_if_needed(self) -> None:
        if len(self._store) <= self._max_records:
            return
        # Evict oldest entries first
        sorted_ids = sorted(self._timestamps.items(), key=lambda x: x[1])
        evict_count = len(self._store) - self._max_records
        for exec_id, _ in sorted_ids[:evict_count]:
            self._store.pop(exec_id, None)
            self._timestamps.pop(exec_id, None)
        logger.debug(f"[StateStore] Evicted {evict_count} old records")


class RedisStateStore:
    """
    Redis-backed state store for production multi-process deployments.
    Records are serialized as JSON and stored with TTL.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/3",
        ttl_seconds: int = 86400,
        key_prefix: str = "afmx:exec:",
    ):
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = await aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except ImportError:
                raise ImportError(
                    "redis package required for RedisStateStore. "
                    "Install: pip install redis[asyncio]"
                )
        return self._client

    def _key(self, execution_id: str) -> str:
        return f"{self._key_prefix}{execution_id}"

    async def save(self, record: ExecutionRecord) -> None:
        client = await self._get_client()
        data = record.model_dump_json()
        await client.setex(self._key(record.id), self._ttl_seconds, data)

    async def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        client = await self._get_client()
        raw = await client.get(self._key(execution_id))
        if raw is None:
            return None
        try:
            return ExecutionRecord.model_validate_json(raw)
        except Exception as exc:
            logger.error(f"[RedisStateStore] Failed to deserialize record '{execution_id}': {exc}")
            return None

    async def update_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
        **kwargs: Any,
    ) -> bool:
        record = await self.get(execution_id)
        if not record:
            return False
        record.status = status
        for k, v in kwargs.items():
            if hasattr(record, k):
                setattr(record, k, v)
        await self.save(record)
        return True

    async def delete(self, execution_id: str) -> bool:
        client = await self._get_client()
        result = await client.delete(self._key(execution_id))
        return result > 0

    async def list_recent(
        self,
        limit: int = 50,
        status_filter: Optional[ExecutionStatus] = None,
    ) -> List[ExecutionRecord]:
        # Redis doesn't support efficient range queries without sorted sets
        # For MVP, this is a scan — production should use a sorted set index
        client = await self._get_client()
        keys = []
        async for key in client.scan_iter(f"{self._key_prefix}*", count=200):
            keys.append(key)
            if len(keys) >= limit * 5:
                break

        records = []
        for key in keys:
            raw = await client.get(key)
            if raw:
                try:
                    record = ExecutionRecord.model_validate_json(raw)
                    if status_filter is None or record.status == status_filter:
                        records.append(record)
                except Exception:
                    continue

        records.sort(key=lambda r: r.queued_at, reverse=True)
        return records[:limit]
