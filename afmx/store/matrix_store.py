"""
AFMX Matrix Store
Named, versioned matrix definition persistence.
Store reusable matrices by name and retrieve them by name + version.

Enables:
    POST /afmx/matrices          — save a named matrix
    GET  /afmx/matrices          — list all saved matrices
    GET  /afmx/matrices/{name}   — get latest version of matrix
    GET  /afmx/matrices/{name}/{version} — get specific version
    DELETE /afmx/matrices/{name} — delete matrix
    POST /afmx/matrices/{name}/execute — execute a saved matrix by name
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StoredMatrix:
    name: str
    version: str
    definition: Dict[str, Any]     # Raw matrix JSON
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    created_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "definition": self.definition,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredMatrix":
        return cls(
            name=data["name"],
            version=data["version"],
            definition=data["definition"],
            description=data.get("description", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", time.time()),
            created_by=data.get("created_by"),
        )


class InMemoryMatrixStore:
    """
    In-memory versioned matrix store.
    Key = (name, version). Multiple versions of same name supported.
    """

    def __init__(self):
        # (name, version) → StoredMatrix
        self._store: Dict[Tuple[str, str], StoredMatrix] = {}
        self._lock = asyncio.Lock()

    async def save(self, matrix: StoredMatrix) -> None:
        async with self._lock:
            key = (matrix.name, matrix.version)
            self._store[key] = matrix
            logger.info(f"[MatrixStore] Saved '{matrix.name}' v{matrix.version}")

    async def get(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[StoredMatrix]:
        async with self._lock:
            if version:
                return self._store.get((name, version))
            # Return latest by created_at
            candidates = [v for (n, _), v in self._store.items() if n == name]
            if not candidates:
                return None
            return max(candidates, key=lambda m: m.created_at)

    async def list_all(
        self,
        tag_filter: Optional[str] = None,
    ) -> List[StoredMatrix]:
        async with self._lock:
            matrices = list(self._store.values())
            if tag_filter:
                matrices = [m for m in matrices if tag_filter in m.tags]
            matrices.sort(key=lambda m: m.created_at, reverse=True)
            return matrices

    async def list_versions(self, name: str) -> List[StoredMatrix]:
        async with self._lock:
            candidates = [v for (n, _), v in self._store.items() if n == name]
            candidates.sort(key=lambda m: m.created_at, reverse=True)
            return candidates

    async def delete(self, name: str, version: Optional[str] = None) -> int:
        async with self._lock:
            if version:
                key = (name, version)
                if key in self._store:
                    del self._store[key]
                    return 1
                return 0
            # Delete all versions
            keys = [(n, v) for (n, v) in self._store if n == name]
            for k in keys:
                del self._store[k]
            return len(keys)

    async def exists(self, name: str, version: Optional[str] = None) -> bool:
        result = await self.get(name, version)
        return result is not None


class RedisMatrixStore:
    """
    Redis-backed matrix store for production.
    Matrices are stored with a permanent key (no TTL by default).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/5",
        key_prefix: str = "afmx:matrix:",
    ):
        self._redis_url = redis_url
        self._prefix = key_prefix
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = await aioredis.from_url(
                self._redis_url, encoding="utf-8", decode_responses=True
            )
        return self._client

    def _key(self, name: str, version: str) -> str:
        return f"{self._prefix}{name}:{version}"

    async def save(self, matrix: StoredMatrix) -> None:
        client = await self._get_client()
        await client.set(self._key(matrix.name, matrix.version), json.dumps(matrix.to_dict()))

    async def get(self, name: str, version: Optional[str] = None) -> Optional[StoredMatrix]:
        client = await self._get_client()
        if version:
            raw = await client.get(self._key(name, version))
            if raw:
                return StoredMatrix.from_dict(json.loads(raw))
            return None
        # Scan for all versions of this name
        keys = []
        async for key in client.scan_iter(f"{self._prefix}{name}:*"):
            keys.append(key)
        if not keys:
            return None
        candidates = []
        for key in keys:
            raw = await client.get(key)
            if raw:
                candidates.append(StoredMatrix.from_dict(json.loads(raw)))
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.created_at)

    async def list_all(self, tag_filter: Optional[str] = None) -> List[StoredMatrix]:
        client = await self._get_client()
        keys = []
        async for key in client.scan_iter(f"{self._prefix}*"):
            keys.append(key)
        matrices = []
        for key in keys:
            raw = await client.get(key)
            if raw:
                m = StoredMatrix.from_dict(json.loads(raw))
                if tag_filter is None or tag_filter in m.tags:
                    matrices.append(m)
        matrices.sort(key=lambda m: m.created_at, reverse=True)
        return matrices

    async def delete(self, name: str, version: Optional[str] = None) -> int:
        client = await self._get_client()
        if version:
            result = await client.delete(self._key(name, version))
            return result
        keys = []
        async for key in client.scan_iter(f"{self._prefix}{name}:*"):
            keys.append(key)
        if keys:
            return await client.delete(*keys)
        return 0
