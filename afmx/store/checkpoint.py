"""
AFMX Execution Checkpointing

Fix: asyncio.Lock() is now created lazily on first use in InMemoryCheckpointStore.
     Creating asyncio primitives outside a running event loop raises on Python 3.12+.

Checkpoint format per execution:
    {
        "execution_id": "...",
        "matrix_id": "...",
        "completed_node_ids": ["n1", "n2"],
        "node_outputs": {"n1": {...}, "n2": {...}},
        "memory": {...},
        "last_checkpoint_at": 1234567890.0
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from afmx.models.execution import ExecutionContext

logger = logging.getLogger(__name__)

CHECKPOINT_KEY_PREFIX = "afmx:ckpt:"


class CheckpointData:
    """Represents a saved execution checkpoint."""

    def __init__(
        self,
        execution_id: str,
        matrix_id: str,
        completed_node_ids: List[str],
        node_outputs: Dict[str, Any],
        memory: Dict[str, Any],
        last_checkpoint_at: float,
    ):
        self.execution_id = execution_id
        self.matrix_id = matrix_id
        self.completed_node_ids: Set[str] = set(completed_node_ids)
        self.node_outputs = node_outputs
        self.memory = memory
        self.last_checkpoint_at = last_checkpoint_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "matrix_id": self.matrix_id,
            "completed_node_ids": list(self.completed_node_ids),
            "node_outputs": self.node_outputs,
            "memory": self.memory,
            "last_checkpoint_at": self.last_checkpoint_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        return cls(
            execution_id=data["execution_id"],
            matrix_id=data["matrix_id"],
            completed_node_ids=data.get("completed_node_ids", []),
            node_outputs=data.get("node_outputs", {}),
            memory=data.get("memory", {}),
            last_checkpoint_at=data.get("last_checkpoint_at", time.time()),
        )

    def apply_to_context(self, context: ExecutionContext) -> None:
        """Restore checkpoint state into a fresh ExecutionContext."""
        context.node_outputs.update(self.node_outputs)
        context.memory.update(self.memory)


class InMemoryCheckpointStore:
    """
    In-memory checkpoint store for development/testing.

    Fix: asyncio.Lock() is now created lazily on first coroutine call
         instead of in __init__ to avoid Python 3.12 event loop errors.
    """

    def __init__(self):
        self._checkpoints: Dict[str, CheckpointData] = {}
        self._lock: Optional[asyncio.Lock] = None  # lazy

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def save(self, checkpoint: CheckpointData) -> None:
        async with self._get_lock():
            self._checkpoints[checkpoint.execution_id] = checkpoint
            logger.debug(
                f"[Checkpoint] Saved '{checkpoint.execution_id}' "
                f"({len(checkpoint.completed_node_ids)} nodes complete)"
            )

    async def load(self, execution_id: str) -> Optional[CheckpointData]:
        async with self._get_lock():
            return self._checkpoints.get(execution_id)

    async def delete(self, execution_id: str) -> None:
        async with self._get_lock():
            self._checkpoints.pop(execution_id, None)

    async def update_node_complete(
        self,
        execution_id: str,
        node_id: str,
        node_output: Any,
        context: ExecutionContext,
    ) -> None:
        """Called after each node completes — incrementally updates checkpoint."""
        async with self._get_lock():
            ckpt = self._checkpoints.get(execution_id)
            if ckpt is None:
                ckpt = CheckpointData(
                    execution_id=execution_id,
                    matrix_id=context.metadata.get("__matrix_id__", ""),
                    completed_node_ids=[],
                    node_outputs={},
                    memory={},
                    last_checkpoint_at=time.time(),
                )
                self._checkpoints[execution_id] = ckpt

            ckpt.completed_node_ids.add(node_id)
            if node_output is not None:
                ckpt.node_outputs[node_id] = node_output
            ckpt.memory = dict(context.memory)
            ckpt.last_checkpoint_at = time.time()


class RedisCheckpointStore:
    """
    Redis-backed checkpoint store for production.
    Supports cross-process resume after crash or restart.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/4",
        ttl_seconds: int = 86400 * 7,  # 7 days
    ):
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = await aioredis.from_url(
                    self._redis_url, encoding="utf-8", decode_responses=True
                )
            except ImportError:
                raise ImportError(
                    "redis package required for RedisCheckpointStore. "
                    "Install: pip install redis[asyncio]"
                )
        return self._client

    def _key(self, execution_id: str) -> str:
        return f"{CHECKPOINT_KEY_PREFIX}{execution_id}"

    async def save(self, checkpoint: CheckpointData) -> None:
        client = await self._get_client()
        await client.setex(
            self._key(checkpoint.execution_id),
            self._ttl,
            json.dumps(checkpoint.to_dict()),
        )

    async def load(self, execution_id: str) -> Optional[CheckpointData]:
        client = await self._get_client()
        raw = await client.get(self._key(execution_id))
        if raw is None:
            return None
        return CheckpointData.from_dict(json.loads(raw))

    async def delete(self, execution_id: str) -> None:
        client = await self._get_client()
        await client.delete(self._key(execution_id))

    async def update_node_complete(
        self,
        execution_id: str,
        node_id: str,
        node_output: Any,
        context: ExecutionContext,
    ) -> None:
        existing = await self.load(execution_id)
        if existing is None:
            existing = CheckpointData(
                execution_id=execution_id,
                matrix_id=context.metadata.get("__matrix_id__", ""),
                completed_node_ids=[],
                node_outputs={},
                memory={},
                last_checkpoint_at=time.time(),
            )
        existing.completed_node_ids.add(node_id)
        if node_output is not None:
            existing.node_outputs[node_id] = node_output
        existing.memory = dict(context.memory)
        existing.last_checkpoint_at = time.time()
        await self.save(existing)
