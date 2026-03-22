"""
AFMX Audit Store
In-memory circular buffer (dev) and Redis sorted-set (production) backends.

Both stores expose identical async interfaces:
  append(event)             — write one audit event
  query(**filters)          — filtered paginated read
  count()                   — total records
  export_json(**filters)    — JSON array string
  export_ndjson(**filters)  — newline-delimited JSON
  export_csv(**filters)     — CSV with header row

Query filters (all optional):
  since, until   — Unix timestamps
  action         — AuditAction value string
  actor          — actor name
  actor_id       — actor key ID
  tenant_id      — tenant scope
  resource_type  — "execution" | "matrix" | "key" | "server"
  resource_id    — specific resource ID
  outcome        — "success" | "failure" | "denied"
  limit          — max results (default 100, hard max 100_000)
  offset         — pagination offset
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional

from afmx.audit.model import AuditEvent, AuditAction

logger = logging.getLogger(__name__)

_REDIS_SORTED_SET_KEY = "afmx:audit:events"
_REDIS_DATA_PREFIX    = "afmx:audit:data:"


class InMemoryAuditStore:
    """
    Thread-safe in-memory audit store.

    Implements a circular buffer capped at `max_records`.
    Oldest records are evicted when the cap is reached.
    Not suitable for multi-process deployments.

    asyncio.Lock is lazy — created on first coroutine call.
    """

    def __init__(self, max_records: int = 100_000):
        self._events: List[AuditEvent] = []
        self._max = max_records
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def append(self, event: AuditEvent) -> None:
        async with self._get_lock():
            self._events.append(event)
            if len(self._events) > self._max:
                # Drop oldest 10% to avoid per-record eviction overhead
                trim = max(1, self._max // 10)
                self._events = self._events[trim:]

    async def query(
        self,
        *,
        since: Optional[float] = None,
        until: Optional[float] = None,
        action: Optional[str] = None,
        actor: Optional[str] = None,
        actor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        async with self._get_lock():
            events = list(self._events)

        # Apply filters
        if since is not None:
            events = [e for e in events if e.timestamp >= since]
        if until is not None:
            events = [e for e in events if e.timestamp <= until]
        if action is not None:
            events = [e for e in events if str(e.action) == action]
        if actor is not None:
            events = [e for e in events if e.actor == actor]
        if actor_id is not None:
            events = [e for e in events if e.actor_id == actor_id]
        if tenant_id is not None:
            events = [e for e in events if e.tenant_id == tenant_id]
        if resource_type is not None:
            events = [e for e in events if e.resource_type == resource_type]
        if resource_id is not None:
            events = [e for e in events if e.resource_id == resource_id]
        if outcome is not None:
            events = [e for e in events if e.outcome == outcome]

        # Newest first
        events.sort(key=lambda e: e.timestamp, reverse=True)

        limit = min(limit, 100_000)
        return events[offset: offset + limit]

    async def count(self) -> int:
        async with self._get_lock():
            return len(self._events)

    # ─── Export helpers ───────────────────────────────────────────────────────

    async def export_json(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        return json.dumps([e.to_dict() for e in events], indent=2, default=str)

    async def export_ndjson(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        return "\n".join(json.dumps(e.to_dict(), default=str) for e in events)

    async def export_csv(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        if not events:
            return ""

        columns = [
            "id", "timestamp", "action", "actor", "actor_id", "actor_role",
            "tenant_id", "resource_type", "resource_id", "outcome",
            "ip_address", "user_agent", "duration_ms", "error",
        ]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            row = e.to_dict()
            # Flatten details as JSON string for CSV
            row.pop("details", None)
            writer.writerow(row)

        return buf.getvalue()


class RedisAuditStore:
    """
    Redis-backed audit store using a sorted set (score = timestamp) for
    time-ordered queries and efficient range scans.

    Layout:
      ZADD afmx:audit:events <timestamp> <event_id>
      SET  afmx:audit:data:<event_id>   <JSON>  EX <ttl>
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/7",
        ttl_seconds: int = 86400 * 90,  # 90 days
        max_records: int = 1_000_000,
    ):
        self._url = redis_url
        self._ttl = ttl_seconds
        self._max = max_records
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = await aioredis.from_url(
                self._url, encoding="utf-8", decode_responses=True
            )
        return self._client

    async def append(self, event: AuditEvent) -> None:
        client = await self._get_client()
        async with client.pipeline(transaction=True) as pipe:
            pipe.zadd(_REDIS_SORTED_SET_KEY, {event.id: event.timestamp})
            pipe.setex(
                f"{_REDIS_DATA_PREFIX}{event.id}",
                self._ttl,
                json.dumps(event.to_dict(), default=str),
            )
            await pipe.execute()

        # Trim to max_records
        total = await client.zcard(_REDIS_SORTED_SET_KEY)
        if total > self._max:
            trim_count = total - self._max
            old_ids = await client.zrange(_REDIS_SORTED_SET_KEY, 0, trim_count - 1)
            if old_ids:
                async with client.pipeline() as pipe:
                    pipe.zrem(_REDIS_SORTED_SET_KEY, *old_ids)
                    for eid in old_ids:
                        pipe.delete(f"{_REDIS_DATA_PREFIX}{eid}")
                    await pipe.execute()

    async def query(
        self,
        *,
        since: Optional[float] = None,
        until: Optional[float] = None,
        action: Optional[str] = None,
        actor: Optional[str] = None,
        actor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        client = await self._get_client()

        min_score = since if since is not None else "-inf"
        max_score = until if until is not None else "+inf"

        # Fetch event IDs in reverse chronological order
        all_ids = await client.zrevrangebyscore(
            _REDIS_SORTED_SET_KEY,
            max_score,
            min_score,
            start=0,
            num=100_000,
        )

        events: List[AuditEvent] = []
        for eid in all_ids:
            raw = await client.get(f"{_REDIS_DATA_PREFIX}{eid}")
            if not raw:
                continue
            try:
                data = json.loads(raw)
                e = AuditEvent(
                    action=AuditAction(data["action"]),
                    id=data["id"],
                    timestamp=data["timestamp"],
                    actor=data.get("actor", ""),
                    actor_id=data.get("actor_id", ""),
                    actor_role=data.get("actor_role", ""),
                    tenant_id=data.get("tenant_id", "default"),
                    resource_type=data.get("resource_type", ""),
                    resource_id=data.get("resource_id", ""),
                    outcome=data.get("outcome", "success"),
                    details=data.get("details", {}),
                    ip_address=data.get("ip_address"),
                    user_agent=data.get("user_agent"),
                    duration_ms=data.get("duration_ms"),
                    error=data.get("error"),
                )
                # Apply filters
                if action and str(e.action) != action:
                    continue
                if actor and e.actor != actor:
                    continue
                if actor_id and e.actor_id != actor_id:
                    continue
                if tenant_id and e.tenant_id != tenant_id:
                    continue
                if resource_type and e.resource_type != resource_type:
                    continue
                if resource_id and e.resource_id != resource_id:
                    continue
                if outcome and e.outcome != outcome:
                    continue
                events.append(e)
            except Exception as exc:
                logger.debug(f"[RedisAuditStore] Skipping malformed event {eid}: {exc}")

        limit = min(limit, 100_000)
        return events[offset: offset + limit]

    async def count(self) -> int:
        client = await self._get_client()
        return await client.zcard(_REDIS_SORTED_SET_KEY)

    async def export_json(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        return json.dumps([e.to_dict() for e in events], indent=2, default=str)

    async def export_ndjson(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        return "\n".join(json.dumps(e.to_dict(), default=str) for e in events)

    async def export_csv(self, **filters) -> str:
        events = await self.query(limit=100_000, **filters)
        if not events:
            return ""
        columns = [
            "id", "timestamp", "action", "actor", "actor_id", "actor_role",
            "tenant_id", "resource_type", "resource_id", "outcome",
            "ip_address", "user_agent", "duration_ms", "error",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            row = e.to_dict()
            row.pop("details", None)
            writer.writerow(row)
        return buf.getvalue()
