"""
Unit tests for ExecutionContext and ExecutionRecord
"""
import pytest
import time
from afmx.models.execution import (
    ExecutionContext, ExecutionRecord, ExecutionStatus,
)


class TestExecutionContext:
    def test_default_context(self):
        ctx = ExecutionContext()
        assert ctx.input is None
        assert ctx.memory == {}
        assert ctx.node_outputs == {}

    def test_set_and_get_node_output(self):
        ctx = ExecutionContext()
        ctx.set_node_output("node-1", {"result": "hello"})
        out = ctx.get_node_output("node-1")
        assert out == {"result": "hello"}

    def test_get_missing_output_returns_none(self):
        ctx = ExecutionContext()
        assert ctx.get_node_output("ghost") is None

    def test_memory_operations(self):
        ctx = ExecutionContext()
        ctx.set_memory("key1", 42)
        assert ctx.get_memory("key1") == 42
        assert ctx.get_memory("missing", "default") == "default"

    def test_snapshot_is_copy(self):
        ctx = ExecutionContext(input={"query": "test"})
        ctx.set_memory("x", 1)
        snap = ctx.snapshot()
        ctx.set_memory("x", 999)
        assert snap["memory"]["x"] == 1  # Snapshot not affected


class TestExecutionRecord:
    def _make_record(self):
        return ExecutionRecord(
            matrix_id="mat-1",
            matrix_name="test-matrix",
        )

    def test_initial_state(self):
        r = self._make_record()
        assert r.status == ExecutionStatus.QUEUED
        assert r.started_at is None
        assert r.finished_at is None
        assert r.is_terminal is False

    def test_mark_started(self):
        r = self._make_record()
        r.mark_started()
        assert r.status == ExecutionStatus.RUNNING
        assert r.started_at is not None

    def test_mark_completed(self):
        r = self._make_record()
        r.mark_started()
        time.sleep(0.01)
        r.mark_completed()
        assert r.status == ExecutionStatus.COMPLETED
        assert r.is_terminal is True
        assert r.duration_ms is not None
        assert r.duration_ms > 0

    def test_mark_failed(self):
        r = self._make_record()
        r.mark_started()
        r.mark_failed("something broke", error_node_id="node-x")
        assert r.status == ExecutionStatus.FAILED
        assert r.error == "something broke"
        assert r.error_node_id == "node-x"
        assert r.is_terminal is True

    def test_mark_aborted(self):
        r = self._make_record()
        r.mark_aborted("user cancelled")
        assert r.status == ExecutionStatus.ABORTED
        assert r.is_terminal is True

    def test_mark_timeout(self):
        r = self._make_record()
        r.mark_timeout()
        assert r.status == ExecutionStatus.TIMEOUT
        assert r.is_terminal is True

    def test_mark_partial(self):
        r = self._make_record()
        r.mark_partial()
        assert r.status == ExecutionStatus.PARTIAL
        assert r.is_terminal is True

    def test_duration_ms_none_when_not_started(self):
        r = self._make_record()
        assert r.duration_ms is None
