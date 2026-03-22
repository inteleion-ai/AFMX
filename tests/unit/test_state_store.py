"""
Unit tests for StateStore (InMemory)
"""
import asyncio
import pytest
from afmx.store.state_store import InMemoryStateStore
from afmx.models.execution import ExecutionRecord, ExecutionStatus


@pytest.fixture
def store():
    return InMemoryStateStore(max_records=100, ttl_seconds=3600)


def make_record(name: str = "test") -> ExecutionRecord:
    return ExecutionRecord(matrix_id="mat-1", matrix_name=name)


class TestInMemoryStateStore:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store):
        r = make_record()
        await store.save(r)
        fetched = await store.get(r.id)
        assert fetched is not None
        assert fetched.id == r.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status(self, store):
        r = make_record()
        await store.save(r)
        success = await store.update_status(r.id, ExecutionStatus.RUNNING)
        assert success is True
        updated = await store.get(r.id)
        assert updated.status == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_false(self, store):
        result = await store.update_status("ghost", ExecutionStatus.FAILED)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete(self, store):
        r = make_record()
        await store.save(r)
        deleted = await store.delete(r.id)
        assert deleted is True
        assert await store.get(r.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, store):
        result = await store.delete("ghost")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_recent(self, store):
        for i in range(5):
            r = make_record(f"matrix-{i}")
            await store.save(r)
        records = await store.list_recent(limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, store):
        r1 = make_record("a")
        r1.mark_completed()
        r2 = make_record("b")
        r2.mark_failed("err")
        await store.save(r1)
        await store.save(r2)

        completed = await store.list_recent(status_filter=ExecutionStatus.COMPLETED)
        assert all(r.status == ExecutionStatus.COMPLETED for r in completed)

    @pytest.mark.asyncio
    async def test_count(self, store):
        assert await store.count() == 0
        await store.save(make_record())
        await store.save(make_record())
        assert await store.count() == 2

    @pytest.mark.asyncio
    async def test_eviction_on_max_records(self):
        small_store = InMemoryStateStore(max_records=3)
        records = [make_record(f"m{i}") for i in range(5)]
        for r in records:
            await small_store.save(r)
        # After eviction, only 3 records remain
        count = await small_store.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        import time
        ttl_store = InMemoryStateStore(ttl_seconds=0.01)
        r = make_record()
        await ttl_store.save(r)
        time.sleep(0.05)  # Let TTL expire
        result = await ttl_store.get(r.id)
        assert result is None
