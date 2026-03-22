"""
Unit tests for InMemoryMatrixStore
"""
import asyncio
import pytest
from afmx.store.matrix_store import InMemoryMatrixStore, StoredMatrix


@pytest.fixture
def store():
    return InMemoryMatrixStore()


def make_matrix(name: str = "my-flow", version: str = "1.0.0") -> StoredMatrix:
    return StoredMatrix(
        name=name,
        version=version,
        definition={
            "name": name,
            "mode": "SEQUENTIAL",
            "nodes": [
                {"id": "n1", "name": "n1", "type": "FUNCTION", "handler": "h"}
            ],
            "edges": [],
        },
        description=f"Test matrix {name}",
        tags=["test"],
    )


class TestInMemoryMatrixStore:

    @pytest.mark.asyncio
    async def test_save_and_get_latest(self, store):
        m = make_matrix()
        await store.save(m)
        loaded = await store.get(m.name)
        assert loaded is not None
        assert loaded.name == m.name
        assert loaded.version == m.version

    @pytest.mark.asyncio
    async def test_get_specific_version(self, store):
        v1 = make_matrix("flow", "1.0.0")
        v2 = make_matrix("flow", "2.0.0")
        await store.save(v1)
        await store.save(v2)
        result = await store.get("flow", version="1.0.0")
        assert result is not None
        assert result.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_returns_latest_when_no_version(self, store):
        import time
        v1 = make_matrix("flow", "1.0.0")
        v1.created_at = time.time() - 100
        v2 = make_matrix("flow", "2.0.0")
        v2.created_at = time.time()
        await store.save(v1)
        await store.save(v2)
        result = await store.get("flow")
        assert result.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("ghost")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, store):
        await store.save(make_matrix("flow-a"))
        await store.save(make_matrix("flow-b"))
        await store.save(make_matrix("flow-c"))
        all_matrices = await store.list_all()
        assert len(all_matrices) == 3

    @pytest.mark.asyncio
    async def test_list_all_tag_filter(self, store):
        m1 = make_matrix("tagged")
        m1.tags = ["production"]
        m2 = make_matrix("untagged")
        m2.tags = []
        await store.save(m1)
        await store.save(m2)
        production = await store.list_all(tag_filter="production")
        assert len(production) == 1
        assert production[0].name == "tagged"

    @pytest.mark.asyncio
    async def test_list_versions(self, store):
        await store.save(make_matrix("flow", "1.0.0"))
        await store.save(make_matrix("flow", "2.0.0"))
        await store.save(make_matrix("flow", "3.0.0"))
        versions = await store.list_versions("flow")
        assert len(versions) == 3

    @pytest.mark.asyncio
    async def test_delete_specific_version(self, store):
        await store.save(make_matrix("flow", "1.0.0"))
        await store.save(make_matrix("flow", "2.0.0"))
        deleted = await store.delete("flow", version="1.0.0")
        assert deleted == 1
        assert await store.get("flow", version="1.0.0") is None
        assert await store.get("flow", version="2.0.0") is not None

    @pytest.mark.asyncio
    async def test_delete_all_versions(self, store):
        await store.save(make_matrix("flow", "1.0.0"))
        await store.save(make_matrix("flow", "2.0.0"))
        deleted = await store.delete("flow")
        assert deleted == 2
        assert await store.get("flow") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_zero(self, store):
        deleted = await store.delete("ghost")
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_exists(self, store):
        assert not await store.exists("flow")
        await store.save(make_matrix("flow"))
        assert await store.exists("flow")

    @pytest.mark.asyncio
    async def test_stored_matrix_to_dict_roundtrip(self):
        m = make_matrix("roundtrip", "1.2.3")
        d = m.to_dict()
        restored = StoredMatrix.from_dict(d)
        assert restored.name == "roundtrip"
        assert restored.version == "1.2.3"
        assert restored.definition["mode"] == "SEQUENTIAL"
