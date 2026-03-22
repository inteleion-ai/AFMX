"""
AFMX Observability — Prometheus Metrics

FIX: Removed unused imports (Summary, CollectorRegistry).
FIX: Guard against duplicate metric registration across test runs by
     catching ValueError from prometheus_client.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from afmx.observability.events import AFMXEvent, EventBus, EventType

logger = logging.getLogger(__name__)


def _safe_counter(name, doc, labels, registry):
    """Register a Counter, or return existing one if already registered."""
    try:
        return Counter(name, doc, labels, registry=registry)
    except ValueError:
        return registry._names_to_collectors.get(name)


def _safe_gauge(name, doc, registry):
    try:
        return Gauge(name, doc, registry=registry)
    except ValueError:
        return registry._names_to_collectors.get(name)


def _safe_histogram(name, doc, labels, buckets, registry):
    try:
        return Histogram(name, doc, labels, buckets=buckets, registry=registry)
    except ValueError:
        return registry._names_to_collectors.get(name)


class AFMXMetrics:
    """
    Prometheus metrics for AFMX.
    Safe for repeated instantiation (e.g., across test runs).
    """

    def __init__(self, registry=None):
        if not PROMETHEUS_AVAILABLE:
            return

        reg = registry or REGISTRY

        self.executions_total = _safe_counter(
            "afmx_executions_total",
            "Total number of matrix executions",
            ["matrix_name", "status"],
            reg,
        )
        self.execution_duration_seconds = _safe_histogram(
            "afmx_execution_duration_seconds",
            "Matrix execution duration in seconds",
            ["matrix_name", "mode"],
            [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            reg,
        )
        self.active_executions = _safe_gauge(
            "afmx_active_executions",
            "Number of currently running matrix executions",
            reg,
        )
        self.nodes_total = _safe_counter(
            "afmx_nodes_total",
            "Total node executions",
            ["node_type", "status"],
            reg,
        )
        self.node_duration_seconds = _safe_histogram(
            "afmx_node_duration_seconds",
            "Node execution duration in seconds",
            ["node_type"],
            [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
            reg,
        )
        self.node_retries_total = _safe_counter(
            "afmx_node_retries_total",
            "Total node retry attempts",
            ["node_name"],
            reg,
        )
        self.circuit_breaker_trips = _safe_counter(
            "afmx_circuit_breaker_trips_total",
            "Total circuit breaker open events",
            ["node_id"],
            reg,
        )

    def attach_to_event_bus(self, bus: EventBus) -> None:
        if not PROMETHEUS_AVAILABLE:
            return
        bus.subscribe(EventType.EXECUTION_STARTED,   self._on_execution_started)
        bus.subscribe(EventType.EXECUTION_COMPLETED, self._on_execution_completed)
        bus.subscribe(EventType.EXECUTION_FAILED,    self._on_execution_failed)
        bus.subscribe(EventType.EXECUTION_TIMEOUT,   self._on_execution_timeout)
        bus.subscribe(EventType.NODE_COMPLETED,      self._on_node_completed)
        bus.subscribe(EventType.NODE_FAILED,         self._on_node_failed)
        bus.subscribe(EventType.NODE_SKIPPED,        self._on_node_skipped)
        bus.subscribe(EventType.NODE_RETRYING,       self._on_node_retrying)
        bus.subscribe(EventType.CIRCUIT_BREAKER_OPEN, self._on_circuit_breaker_open)

    async def _on_execution_started(self, event: AFMXEvent) -> None:
        if self.active_executions:
            self.active_executions.inc()

    async def _on_execution_completed(self, event: AFMXEvent) -> None:
        if self.active_executions:
            self.active_executions.dec()
        if self.executions_total:
            mn = event.data.get("matrix_name", "unknown")
            self.executions_total.labels(matrix_name=mn, status="completed").inc()
        if self.execution_duration_seconds:
            duration = event.data.get("duration_ms", 0) / 1000
            mode = event.data.get("mode", "unknown")
            mn = event.data.get("matrix_name", "unknown")
            self.execution_duration_seconds.labels(matrix_name=mn, mode=mode).observe(duration)

    async def _on_execution_failed(self, event: AFMXEvent) -> None:
        if self.active_executions:
            self.active_executions.dec()
        if self.executions_total:
            mn = event.data.get("matrix_name", "unknown")
            self.executions_total.labels(matrix_name=mn, status="failed").inc()

    async def _on_execution_timeout(self, event: AFMXEvent) -> None:
        if self.active_executions:
            self.active_executions.dec()
        if self.executions_total:
            mn = event.data.get("matrix_name", "unknown")
            self.executions_total.labels(matrix_name=mn, status="timeout").inc()

    async def _on_node_completed(self, event: AFMXEvent) -> None:
        if self.nodes_total:
            nt = event.data.get("node_type", "unknown")
            self.nodes_total.labels(node_type=nt, status="success").inc()
        if self.node_duration_seconds:
            nt = event.data.get("node_type", "unknown")
            dur = event.data.get("duration_ms", 0) / 1000
            self.node_duration_seconds.labels(node_type=nt).observe(dur)

    async def _on_node_failed(self, event: AFMXEvent) -> None:
        if self.nodes_total:
            nt = event.data.get("node_type", "unknown")
            self.nodes_total.labels(node_type=nt, status="failed").inc()

    async def _on_node_skipped(self, event: AFMXEvent) -> None:
        if self.nodes_total:
            self.nodes_total.labels(node_type="any", status="skipped").inc()

    async def _on_node_retrying(self, event: AFMXEvent) -> None:
        # FIX: properly count retries via the NODE_RETRYING event
        if self.node_retries_total:
            node_name = event.data.get("node_name", "unknown")
            self.node_retries_total.labels(node_name=node_name).inc()

    async def _on_circuit_breaker_open(self, event: AFMXEvent) -> None:
        if self.circuit_breaker_trips:
            node_id = event.data.get("node_id", "unknown")
            self.circuit_breaker_trips.labels(node_id=node_id).inc()
