"""
Unit tests for InMemoryCheckpointStore
"""
import asyncio
import pytest
from afmx.store.checkpoint import InMemoryCheckpointStore, CheckpointData
from afmx.models.execution import ExecutionContext


@pytest.fixture
def store():
    return InMemoryCheckpointStore()


@pytest.fixture
def context():
    ctx = ExecutionContext(input="test")
    ctx.set_memory("key", "value")
    return ctx


def make_checkpoint(exec_id: str = "exec-1") -> CheckpointData:
    return CheckpointData(
        execution_id=exec_id,
        matrix_id="mat-1",
        completed_node_ids=["n1", "n2"],
        node_outputs={"n1": {"result": "a"}, "n2": {"result": "b"}},
        memory={"shared": True},
        last_checkpoint_at=1000.0,
    )


class TestInMemoryCheckpointStore:

    @pytest.mark.asyncio
    async def test_save_and_load(self, store):
        ckpt = make_checkpoint()
        await store.save(ckpt)
        loaded = await store.load(ckpt.execution_id)
        assert loaded is not None
        assert loaded.execution_id == ckpt.execution_id
        assert "n1" in loaded.completed_node_ids

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, store):
        result = await store.load("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, store):
        ckpt = make_checkpoint()
        await store.save(ckpt)
        await store.delete(ckpt.execution_id)
        assert await store.load(ckpt.execution_id) is None

    @pytest.mark.asyncio
    async def test_update_node_complete_creates_if_absent(self, store, context):
        await store.update_node_complete("exec-new", "n1", {"out": 1}, context)
        ckpt = await store.load("exec-new")
        assert ckpt is not None
        assert "n1" in ckpt.completed_node_ids
        assert ckpt.node_outputs["n1"] == {"out": 1}

    @pytest.mark.asyncio
    async def test_update_node_complete_incremental(self, store, context):
        await store.update_node_complete("exec-1", "n1", {"a": 1}, context)
        await store.update_node_complete("exec-1", "n2", {"b": 2}, context)
        ckpt = await store.load("exec-1")
        assert "n1" in ckpt.completed_node_ids
        assert "n2" in ckpt.completed_node_ids
        assert len(ckpt.completed_node_ids) == 2

    @pytest.mark.asyncio
    async def test_update_syncs_memory(self, store, context):
        context.set_memory("step", "done")
        await store.update_node_complete("exec-1", "n1", None, context)
        ckpt = await store.load("exec-1")
        assert ckpt.memory.get("step") == "done"

    @pytest.mark.asyncio
    async def test_apply_to_context_restores_state(self, store):
        ckpt = CheckpointData(
            execution_id="exec-1",
            matrix_id="mat-1",
            completed_node_ids=["n1"],
            node_outputs={"n1": {"restored": True}},
            memory={"token": "abc"},
            last_checkpoint_at=0,
        )
        ctx = ExecutionContext(input="fresh")
        ckpt.apply_to_context(ctx)
        assert ctx.get_node_output("n1") == {"restored": True}
        assert ctx.get_memory("token") == "abc"

    @pytest.mark.asyncio
    async def test_checkpoint_to_dict_and_from_dict(self):
        ckpt = make_checkpoint("exec-roundtrip")
        d = ckpt.to_dict()
        restored = CheckpointData.from_dict(d)
        assert restored.execution_id == "exec-roundtrip"
        assert "n1" in restored.completed_node_ids
        assert restored.node_outputs["n1"] == {"result": "a"}
