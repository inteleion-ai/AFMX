"""
AFMX Matrix Model
=================

v1.2 — Open Column Axis
------------------------
``MatrixAddress.role`` is now a plain ``str`` (was ``AgentRole`` enum).

This change is required because ``agent_role`` on ``Node`` is now an open
string field, making ``MatrixAddress`` work with any domain vocabulary.

``MatrixAddress(layer=CognitiveLayer.REASON, role="QUANT")`` is as valid as
``MatrixAddress(layer=CognitiveLayer.REASON, role="CLINICIAN")`` or
``MatrixAddress(layer=CognitiveLayer.REASON, role="PARALEGAL")``.

Backward compatibility:
  All code that passes ``AgentRole.OPS`` (which equals the string ``"OPS"``)
  continues to work — ``MatrixAddress(layer=..., role=AgentRole.OPS)`` is
  identical to ``MatrixAddress(layer=..., role="OPS")``.

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from afmx.models.edge import Edge
from afmx.models.node import CognitiveLayer, Node


# ─── Execution mode ───────────────────────────────────────────────────────────

class ExecutionMode(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"   # Topological order, one node at a time
    PARALLEL   = "PARALLEL"     # All nodes concurrently (bounded by max_parallelism)
    HYBRID     = "HYBRID"       # DAG level-sets — levels sequential, intra-level parallel
    DIAGONAL   = "DIAGONAL"     # Grouped by CognitiveLayer; each layer's nodes run in
                                # parallel; layers execute in canonical cognitive order


class AbortPolicy(str, Enum):
    FAIL_FAST     = "FAIL_FAST"      # Abort entire matrix on first node failure
    CONTINUE      = "CONTINUE"       # Run all nodes; record partial failures
    CRITICAL_ONLY = "CRITICAL_ONLY"  # Abort only when a "critical" node fails


# ─── MatrixAddress ────────────────────────────────────────────────────────────

class MatrixAddress(BaseModel):
    """
    A coordinate in the Cognitive Execution Matrix.

    ┌──────────────────────────────────────────────────────────┐
    │  layer  —  CognitiveLayer  (fixed enum, the right axis)  │
    │  role   —  str             (open string, the right fix)  │
    └──────────────────────────────────────────────────────────┘

    The role accepts any valid agent_role string from any domain pack:
      MatrixAddress(layer=CognitiveLayer.REASON, role="COMPLIANCE")   # tech
      MatrixAddress(layer=CognitiveLayer.REASON, role="QUANT")        # finance
      MatrixAddress(layer=CognitiveLayer.REASON, role="CLINICIAN")    # healthcare
      MatrixAddress(layer=CognitiveLayer.REASON, role="PARALEGAL")    # legal

    String representation: "REASON×COMPLIANCE", "PLAN×QUANT", etc.

    Backward compatibility:
      MatrixAddress(layer=CognitiveLayer.ACT, role=AgentRole.OPS)
      is identical to:
      MatrixAddress(layer=CognitiveLayer.ACT, role="OPS")
      because AgentRole.OPS == "OPS".
    """
    layer: CognitiveLayer
    role:  str             = Field(..., min_length=1, max_length=64)

    model_config = ConfigDict(frozen=True)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        import re
        v = v.strip()
        if not re.match(r'^[A-Z][A-Z0-9_]{0,63}$', v):
            raise ValueError(
                f"MatrixAddress role '{v}' must match [A-Z][A-Z0-9_]{{0,63}}. "
                f"Examples: 'OPS', 'QUANT', 'CLINICIAN'"
            )
        return v

    def __str__(self) -> str:
        # Use .value to get "REASON" not "CognitiveLayer.REASON" on Python 3.12+
        layer_str = self.layer.value if isinstance(self.layer, CognitiveLayer) else str(self.layer)
        return f"{layer_str}×{self.role}"

    def __repr__(self) -> str:
        layer_str = self.layer.value if isinstance(self.layer, CognitiveLayer) else str(self.layer)
        return f"MatrixAddress(layer={layer_str!r}, role={self.role!r})"

    def __hash__(self) -> int:
        return hash((self.layer, self.role))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MatrixAddress):
            return NotImplemented
        return self.layer == other.layer and self.role == other.role


# ─── ExecutionMatrix ──────────────────────────────────────────────────────────

class ExecutionMatrix(BaseModel):
    """
    The core orchestration primitive in AFMX — a DAG of Nodes and Edges.

    Execution modes:
      SEQUENTIAL  → one node at a time in topological order
      PARALLEL    → all nodes concurrently (bounded by max_parallelism)
      HYBRID      → DAG level-sets (parallel within a level, sequential across)
      DIAGONAL    → grouped by CognitiveLayer; each layer's nodes run in parallel;
                    layers execute: PERCEIVE→RETRIEVE→REASON→PLAN→ACT→EVALUATE→REPORT

    Nodes without ``cognitive_layer`` run in an unclassified batch at the end
    when DIAGONAL mode is used.
    """
    model_config = ConfigDict()

    id:      str = Field(default_factory=lambda: str(uuid.uuid4()))
    name:    str = Field(default="unnamed-matrix", min_length=1, max_length=128)
    version: str = Field(default="1.0.0")

    mode:   ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL)
    nodes:  List[Node]    = Field(default_factory=list, min_length=1)
    edges:  List[Edge]    = Field(default_factory=list)

    entry_node_id:         Optional[str] = Field(default=None)
    abort_policy:          AbortPolicy   = Field(default=AbortPolicy.FAIL_FAST)
    max_parallelism:       int           = Field(default=10, ge=1, le=100)
    global_timeout_seconds:float         = Field(default=300.0, ge=1.0)

    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags:     List[str]      = Field(default_factory=list)

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

    # ─── Node lookups ─────────────────────────────────────────────────────────

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

    # ─── Matrix coordinate helpers ────────────────────────────────────────────

    def get_matrix_address(self, node_id: str) -> Optional[MatrixAddress]:
        """Return the MatrixAddress for a node, or None if it has no coordinates."""
        node = self.get_node_by_id(node_id)
        if node and node.cognitive_layer and node.agent_role:
            return MatrixAddress(
                layer=CognitiveLayer(node.cognitive_layer),
                role=node.agent_role,   # already validated str
            )
        return None

    def get_nodes_at_layer(self, layer: CognitiveLayer) -> List[Node]:
        """Return all nodes at a given CognitiveLayer (matrix row)."""
        layer_val = layer.value if isinstance(layer, CognitiveLayer) else layer
        return [n for n in self.nodes if n.cognitive_layer == layer_val]

    def get_nodes_at_role(self, role: str) -> List[Node]:
        """
        Return all nodes for a given agent_role string (matrix column).

        Accepts any string — domain-specific roles like "QUANT" or "CLINICIAN"
        are as valid as the default tech roles like "OPS" or "ANALYST".

        Args:
            role: Role string, e.g. "OPS", "QUANT", "CLINICIAN". Case-sensitive.
        """
        return [n for n in self.nodes if n.agent_role == role]

    def roles_in_matrix(self) -> List[str]:
        """
        Return a sorted list of all unique agent_role values present in this matrix.
        Excludes nodes without a role (agent_role is None).
        """
        return sorted({
            n.agent_role
            for n in self.nodes
            if n.agent_role is not None
        })

    def build_matrix_map(self) -> Dict[MatrixAddress, Node]:
        """
        Build a coordinate → Node mapping for all nodes that have both
        cognitive_layer and agent_role set.

        The returned dict is keyed by MatrixAddress objects. The role string
        in each address is the raw agent_role value from the node — no
        normalisation or enum coercion is applied.
        """
        result: Dict[MatrixAddress, Node] = {}
        for node in self.nodes:
            if node.cognitive_layer and node.agent_role:
                addr = MatrixAddress(
                    layer=CognitiveLayer(node.cognitive_layer),
                    role=node.agent_role,
                )
                result[addr] = node
        return result

    def matrix_coverage_summary(self) -> Dict[str, Any]:
        """
        Return a summary of matrix coverage.

        ``cells_possible`` is now dynamic — it is computed as
        ``len(CognitiveLayer) × len(unique_roles_in_matrix)`` rather than
        a fixed constant. This correctly reflects whatever domain vocabulary
        is in use, not a hardcoded tech-only role count.
        """
        coordinated   = [n for n in self.nodes if n.cognitive_layer and n.agent_role]
        layers_used   = sorted({n.cognitive_layer for n in coordinated})
        roles_used    = sorted({n.agent_role      for n in coordinated})
        n_roles       = len(roles_used)
        n_layers      = len(CognitiveLayer)
        total_possible = n_layers * n_roles if n_roles else 0
        cells = [
            {
                "layer":     n.cognitive_layer,
                "role":      n.agent_role,
                "node_id":   n.id,
                "node_name": n.name,
            }
            for n in coordinated
        ]
        return {
            "total_nodes":          len(self.nodes),
            "coordinated_nodes":    len(coordinated),
            "uncoordinated_nodes":  len(self.nodes) - len(coordinated),
            "layers_used":          layers_used,
            "roles_used":           roles_used,
            "cells_populated":      len(coordinated),
            # cells_possible = 7 layers × N unique roles observed in this matrix
            "cells_possible":       total_possible,
            "coverage_pct": (
                round(len(coordinated) / total_possible * 100, 1)
                if total_possible else 0.0
            ),
            "cells": cells,
        }

    # ─── Topological sort (Kahn's algorithm — O(V + E)) ───────────────────────

    def topological_order(self) -> List[str]:
        """
        Returns nodes in a valid topological execution order.

        Sort key uses a pre-built priority dict (O(1) per node) rather than
        calling get_node_by_id() inside the sort comparator (was O(n²log n)).
        """
        in_degree: Dict[str, int]       = {n.id: 0 for n in self.nodes}
        adjacency: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        priority:  Dict[str, int]       = {n.id: n.priority for n in self.nodes}

        for edge in self.edges:
            adjacency[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        queue  = [nid for nid, deg in in_degree.items() if deg == 0]
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
        """Group nodes into parallel execution batches (DAG level sets)."""
        in_degree: Dict[str, int]       = {n.id: 0 for n in self.nodes}
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
