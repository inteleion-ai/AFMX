"""
Unit tests for ConcurrencyManager
"""
import asyncio
import pytest
from afmx.core.concurrency import ConcurrencyManager


class TestConcurrencyManager:

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        mgr = ConcurrencyManager(max_concurrent=5)
        ok = await mgr.acquire("exec-1", "matrix-a")
        assert ok is True
        stats = mgr.get_stats()
        assert stats["active"] == 1
        await mgr.release("exec-1", "matrix-a")
        assert mgr.get_stats()["active"] == 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_acquires(self):
        mgr = ConcurrencyManager(max_concurrent=3)
        for i in range(3):
            ok = await mgr.acquire(f"exec-{i}", "matrix-a")
            assert ok is True
        assert mgr.get_stats()["active"] == 3

    @pytest.mark.asyncio
    async def test_is_at_capacity(self):
        mgr = ConcurrencyManager(max_concurrent=2)
        await mgr.acquire("e1", "m")
        assert not mgr.is_at_capacity()
        await mgr.acquire("e2", "m")
        assert mgr.is_at_capacity()

    @pytest.mark.asyncio
    async def test_release_decrements_active(self):
        mgr = ConcurrencyManager(max_concurrent=5)
        await mgr.acquire("e1", "m")
        await mgr.acquire("e2", "m")
        await mgr.release("e1", "m")
        assert mgr.get_stats()["active"] == 1

    @pytest.mark.asyncio
    async def test_stats_track_totals(self):
        mgr = ConcurrencyManager(max_concurrent=5)
        await mgr.acquire("e1", "m")
        await mgr.release("e1", "m")
        await mgr.acquire("e2", "m")
        await mgr.release("e2", "m")
        stats = mgr.get_stats()
        assert stats["total_accepted"] == 2
        assert stats["total_completed"] == 2
        assert stats["active"] == 0

    @pytest.mark.asyncio
    async def test_timeout_rejects_when_full(self):
        """When all slots are taken, new acquires should timeout and return False."""
        mgr = ConcurrencyManager(max_concurrent=1, queue_timeout_seconds=0.05)
        ok1 = await mgr.acquire("e1", "m")
        assert ok1 is True
        # e2 should fail — slot taken and timeout is tiny
        ok2 = await mgr.acquire("e2", "m")
        assert ok2 is False
        stats = mgr.get_stats()
        assert stats["total_rejected"] == 1

    @pytest.mark.asyncio
    async def test_peak_active_tracking(self):
        mgr = ConcurrencyManager(max_concurrent=10)
        for i in range(5):
            await mgr.acquire(f"e{i}", "m")
        peak = mgr.get_stats()["peak_active"]
        assert peak == 5

    @pytest.mark.asyncio
    async def test_utilization_pct(self):
        mgr = ConcurrencyManager(max_concurrent=10)
        await mgr.acquire("e1", "m")
        await mgr.acquire("e2", "m")
        stats = mgr.get_stats()
        assert stats["utilization_pct"] == 20.0
