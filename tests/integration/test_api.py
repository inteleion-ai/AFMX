"""
Integration tests for AFMX REST API (FastAPI TestClient)
"""
import pytest
from fastapi.testclient import TestClient

from afmx.main import app, afmx_app
from afmx.core.executor import HandlerRegistry


@pytest.fixture(scope="module")
def client():
    """
    Create a synchronous TestClient wrapping the AFMX FastAPI app.
    Uses module scope to avoid re-creating the app per test.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def register_test_handlers():
    async def echo(inp, ctx, node):
        return {"result": inp.get("input")}

    async def fail(inp, ctx, node):
        raise RuntimeError("handler failure")

    HandlerRegistry.register("echo", echo)
    HandlerRegistry.register("fail_handler", fail)


# ─── Helpers ──────────────────────────────────────────────────────────────────

ECHO_MATRIX = {
    "name": "echo-flow",
    "mode": "SEQUENTIAL",
    "nodes": [
        {"id": "n1", "name": "n1", "type": "FUNCTION", "handler": "echo"}
    ],
    "edges": [],
}

FAIL_MATRIX = {
    "name": "fail-flow",
    "mode": "SEQUENTIAL",
    "abort_policy": "FAIL_FAST",
    "nodes": [
        {"id": "n1", "name": "n1", "type": "FUNCTION", "handler": "fail_handler"}
    ],
    "edges": [],
}

TWO_NODE_MATRIX = {
    "name": "two-node",
    "mode": "SEQUENTIAL",
    "nodes": [
        {"id": "n1", "name": "n1", "type": "FUNCTION", "handler": "echo"},
        {"id": "n2", "name": "n2", "type": "FUNCTION", "handler": "echo"},
    ],
    "edges": [{"from": "n1", "to": "n2"}],
}


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_ok(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "AFMX" in resp.json()["name"]


class TestExecuteEndpoint:
    def test_execute_success(self, client):
        resp = client.post("/afmx/execute", json={
            "matrix": ECHO_MATRIX,
            "input": "hello world",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert data["completed_nodes"] == 1
        assert data["failed_nodes"] == 0

    def test_execute_with_failure(self, client):
        resp = client.post("/afmx/execute", json={
            "matrix": FAIL_MATRIX,
            "input": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "FAILED"
        assert data["failed_nodes"] >= 1

    def test_execute_invalid_matrix_422(self, client):
        resp = client.post("/afmx/execute", json={
            "matrix": {"nodes": []},  # Empty nodes — invalid
            "input": {},
        })
        assert resp.status_code == 422

    def test_execute_two_node_chain(self, client):
        resp = client.post("/afmx/execute", json={
            "matrix": TWO_NODE_MATRIX,
            "input": "chained",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_nodes"] == 2


class TestStatusEndpoint:
    def test_status_found(self, client):
        # First execute to get an ID
        resp = client.post("/afmx/execute", json={
            "matrix": ECHO_MATRIX,
            "input": "x",
        })
        exec_id = resp.json()["execution_id"]

        status_resp = client.get(f"/afmx/status/{exec_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["execution_id"] == exec_id

    def test_status_not_found_404(self, client):
        resp = client.get("/afmx/status/nonexistent-id-xyz")
        assert resp.status_code == 404


class TestValidateEndpoint:
    def test_validate_valid_matrix(self, client):
        resp = client.post("/afmx/validate", json={"matrix": ECHO_MATRIX})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["node_count"] == 1
        assert data["errors"] == []

    def test_validate_invalid_matrix(self, client):
        resp = client.post("/afmx/validate", json={
            "matrix": {
                "nodes": [
                    {"id": "a", "name": "a", "type": "FUNCTION", "handler": "h"}
                ],
                "edges": [{"from": "a", "to": "nonexistent"}],
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


class TestListExecutions:
    def test_list_executions(self, client):
        # Run a few executions first
        for _ in range(3):
            client.post("/afmx/execute", json={"matrix": ECHO_MATRIX, "input": "x"})
        resp = client.get("/afmx/executions?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "executions" in data
        assert data["count"] >= 3

    def test_list_with_invalid_status_400(self, client):
        resp = client.get("/afmx/executions?status_filter=INVALID")
        assert resp.status_code == 400


class TestPluginsEndpoint:
    def test_list_plugins(self, client):
        resp = client.get("/afmx/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "agents" in data
        assert "functions" in data
