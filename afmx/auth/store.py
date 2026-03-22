"""
AFMX API Key Store
In-memory (dev/single-process) and Redis (production) backends.

Both stores support:
  - O(1) lookup by raw key value
  - lookup by key_id
  - list all / filter by tenant
  - revoke (mark inactive) / hard delete
  - last-used timestamp update (async, non-blocking)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

from afmx.auth.rbac import APIKey, Role

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "afmx:apikey:"


# ─── In-Memory ────────────────────────────────────────────────────────────────

class InMemoryAPIKeyStore:
    """
    Thread-safe in-memory API key store.

    Two indexes:
      _by_value[key_value] → APIKey   (primary — used for every auth check)
      _by_id[key_id]       → APIKey   (secondary — used for admin operations)

    asyncio.Lock is lazy to avoid Python 3.12 event-loop bootstrap issues.
    """

    def __init__(self):
        self._by_value: Dict[str, APIKey] = {}
        self._by_id: Dict[str, APIKey] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def create(self, key: APIKey) -> APIKey:
        async with self._get_lock():
            self._by_value[key.key] = key
            self._by_id[key.id] = key
        logger.info(
            f"[APIKeyStore] Created key '{key.name}' id={key.id[:8]} "
            f"role={key.role} tenant={key.tenant_id}"
        )
        return key

    async def get_by_key(self, key_value: str) -> Optional[APIKey]:
        async with self._get_lock():
            return self._by_value.get(key_value)

    async def get_by_id(self, key_id: str) -> Optional[APIKey]:
        async with self._get_lock():
            return self._by_id.get(key_id)

    async def list_all(
        self,
        *,
        tenant_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[APIKey]:
        async with self._get_lock():
            keys = list(self._by_id.values())
        if tenant_id:
            keys = [k for k in keys if k.tenant_id == tenant_id]
        if active_only:
            keys = [k for k in keys if k.is_valid()]
        keys.sort(key=lambda k: k.created_at, reverse=True)
        return keys

    async def revoke(self, key_id: str) -> bool:
        """Mark a key as inactive (soft delete)."""
        async with self._get_lock():
            key = self._by_id.get(key_id)
            if not key:
                return False
            key.active = False
        logger.info(f"[APIKeyStore] Revoked key id={key_id[:8]}")
        return True

    async def delete(self, key_id: str) -> bool:
        """Hard delete — remove from both indexes."""
        async with self._get_lock():
            key = self._by_id.pop(key_id, None)
            if not key:
                return False
            self._by_value.pop(key.key, None)
        logger.info(f"[APIKeyStore] Deleted key id={key_id[:8]}")
        return True

    async def update_last_used(self, key_value: str) -> None:
        """Non-blocking last-used timestamp update — never raises."""
        try:
            async with self._get_lock():
                key = self._by_value.get(key_value)
                if key:
                    key.last_used_at = time.time()
        except Exception:
            pass

    async def count(self, *, active_only: bool = False) -> int:
        async with self._get_lock():
            if active_only:
                return sum(1 for k in self._by_id.values() if k.is_valid())
            return len(self._by_id)


# ─── Redis ────────────────────────────────────────────────────────────────────

class RedisAPIKeyStore:
    """
    Redis-backed API key store for production multi-process deployments.

    Storage layout:
      {prefix}val:{key_value}  → JSON-serialised APIKey (for auth lookup)
      {prefix}id:{key_id}      → raw key value            (for id→key lookup)
      {prefix}idx:tenant:{tid} → Redis Set of key_ids     (for tenant listing)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/6",
        prefix: str = _REDIS_KEY_PREFIX,
    ):
        self._url = redis_url
        self._prefix = prefix
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = await aioredis.from_url(
                    self._url, encoding="utf-8", decode_responses=True
                )
            except ImportError:
                raise ImportError(
                    "redis package required for RedisAPIKeyStore. "
                    "Install: pip install redis[asyncio]"
                )
        return self._client

    def _val_key(self, key_value: str) -> str:
        return f"{self._prefix}val:{key_value}"

    def _id_key(self, key_id: str) -> str:
        return f"{self._prefix}id:{key_id}"

    def _tenant_idx(self, tenant_id: str) -> str:
        return f"{self._prefix}idx:tenant:{tenant_id}"

    async def create(self, key: APIKey) -> APIKey:
        client = await self._get_client()
        data = json.dumps(key.to_dict(redact=False))
        async with client.pipeline(transaction=True) as pipe:
            pipe.set(self._val_key(key.key), data)
            pipe.set(self._id_key(key.id), key.key)
            pipe.sadd(self._tenant_idx(key.tenant_id), key.id)
            await pipe.execute()
        return key

    async def get_by_key(self, key_value: str) -> Optional[APIKey]:
        client = await self._get_client()
        raw = await client.get(self._val_key(key_value))
        if not raw:
            return None
        return self._deserialize(json.loads(raw))

    async def get_by_id(self, key_id: str) -> Optional[APIKey]:
        client = await self._get_client()
        key_value = await client.get(self._id_key(key_id))
        if not key_value:
            return None
        return await self.get_by_key(key_value)

    async def list_all(
        self,
        *,
        tenant_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[APIKey]:
        client = await self._get_client()
        if tenant_id:
            key_ids = await client.smembers(self._tenant_idx(tenant_id))
        else:
            # Scan all id keys
            key_ids = []
            async for k in client.scan_iter(f"{self._prefix}id:*"):
                key_ids.append(k.split(":")[-1])

        keys = []
        for kid in key_ids:
            key = await self.get_by_id(kid)
            if key:
                if active_only and not key.is_valid():
                    continue
                keys.append(key)

        keys.sort(key=lambda k: k.created_at, reverse=True)
        return keys

    async def revoke(self, key_id: str) -> bool:
        key = await self.get_by_id(key_id)
        if not key:
            return False
        key.active = False
        client = await self._get_client()
        await client.set(self._val_key(key.key), json.dumps(key.to_dict(redact=False)))
        return True

    async def delete(self, key_id: str) -> bool:
        key = await self.get_by_id(key_id)
        if not key:
            return False
        client = await self._get_client()
        async with client.pipeline(transaction=True) as pipe:
            pipe.delete(self._val_key(key.key))
            pipe.delete(self._id_key(key_id))
            pipe.srem(self._tenant_idx(key.tenant_id), key_id)
            await pipe.execute()
        return True

    async def update_last_used(self, key_value: str) -> None:
        try:
            key = await self.get_by_key(key_value)
            if key:
                key.last_used_at = time.time()
                client = await self._get_client()
                await client.set(
                    self._val_key(key_value),
                    json.dumps(key.to_dict(redact=False)),
                )
        except Exception:
            pass

    async def count(self, *, active_only: bool = False) -> int:
        keys = await self.list_all(active_only=active_only)
        return len(keys)

    @staticmethod
    def _deserialize(data: dict) -> APIKey:
        return APIKey(
            id=data["id"],
            key=data["key"],
            name=data.get("name", ""),
            role=Role(data["role"]),
            tenant_id=data.get("tenant_id", "default"),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            active=data.get("active", True),
            permission_overrides=set(data.get("permissions", [])),
            description=data.get("description", ""),
            last_used_at=data.get("last_used_at"),
            created_by=data.get("created_by"),
        )
