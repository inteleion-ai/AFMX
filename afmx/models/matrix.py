"""
AFMX Matrix Model

FIX: topological_order() sort key used get_node_by_id() which is O(n) per call,
     making the overall sort O(n² log n). Replaced with a pre-built priority dict.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afmx.models.edge import Edge
from afmx.models.node import Node


class ExecutionMode(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    PARALLEL = "PARALLEL"
    HYBRID = "HYBRID"


class AbortPolicy(str, Enum):
    FAIL_FAST = "FAIL_FAST"
    CONTINUE = "CONTINUE"
    CRITICAL_ONLY = "CRITICAL_ONLY"   # Abort only on critical-flagged node failures


class ExecutionMatrix(BaseModel):
    """
    The core orchestration primitive in AFMX — a DAG of Nodes and Edges.
    The mode determines HOW nodes are scheduled relative to each other.
    """
    model_config = ConfigDict()

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(default="unnamed-matrix", min_length=1, max_length=128)
    version: str = Field(default="1.0.0")
    mode: ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL)
    nodes: List[Node] = Field(default_factory=list, min_length=1)
    edges: List[Edge] = Field(default_factory=list)
    entry_node_id: Optional[str] = Field(default=None)
    abort_policy: AbortPolicy = Field(default=AbortPolicy.FAIL_FAST)
    max_parallelism: int = Field(default=10, ge=1, le=100)
    global_timeout_seconds: float = Field(default=300.0, ge=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_matrix(self) -> "ExecutionMatrix":
        node_ids = {n.id for n in self.nodes}

        for edge in self.edges:
            if edge.from_node not in node_ids:
                raise ValueError(
                    f"Edge '{edge.id}' references unknown from_node '{edge.from_node}'"
                )
            if edge.to_node not in node_ids:
                raise ValueError(
                    f"Edge '{edge.id}' references unknown to_node '{edge.to_node}'"
                )

        if self.entry_node_id and self.entry_node_id not in node_ids:
            raise ValueError(
                f"entry_node_id '{self.entry_node_id}' not found in nodes"
            )

        for node in self.nodes:
            if node.fallback_node_id and node.fallback_node_id not in node_ids:
                raise ValueError(
                    f"Node '{node.id}' fallback_node_id '{node.fallback_node_id}' not found"
                )

        return self

    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edges_from(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.from_node == node_id]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.to_node == node_id]

    def get_entry_nodes(self) -> List[Node]:
        if self.entry_node_id:
            node = self.get_node_by_id(self.entry_node_id)
            return [node] if node else []
        nodes_with_incoming: Set[str] = {e.to_node for e in self.edges}
        return [n for n in self.nodes if n.id not in nodes_with_incoming]

    def topological_order(self) -> List[str]:
        """
        Kahn's algorithm — O(V + E).

        FIX: sort key uses a pre-built priority dict (O(1) lookup per node)
             instead of calling get_node_by_id() (O(n)) inside the sort key,
             which was O(n² log n) overall.
        """
        in_degree: Dict[str, int] = {n.id: 0 for n in self.nodes}
        adjacency: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        # FIX: O(1) priority lookup
        priority: Dict[str, int] = {n.id: n.priority for n in self.nodes}

        for edge in self.edges:
            adjacency[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            queue.sort(key=lambda nid: priority.get(nid, 99))
            current = queue.pop(0)
            result.append(current)
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise ValueError("Cycle detected in execution matrix — DAG required")

        return result

    def get_parallel_batches(self) -> List[List[str]]:
        """Group nodes into parallel execution batches (level sets of the DAG)."""
        in_degree: Dict[str, int] = {n.id: 0 for n in self.nodes}
        adjacency: Dict[str, List[str]] = {n.id: [] for n in self.nodes}

        for edge in self.edges:
            adjacency[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        batches: List[List[str]] = []
        current_batch = [nid for nid, deg in in_degree.items() if deg == 0]

        while current_batch:
            batches.append(current_batch)
            next_batch: List[str] = []
            for nid in current_batch:
                for neighbor in adjacency[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_batch.append(neighbor)
            current_batch = next_batch

        return batches
