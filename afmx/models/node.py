"""
AFMX Node Model
===============

v1.2 — Open Column Axis (breaking fix)
---------------------------------------
``agent_role`` is now an *open string field* — any domain vocabulary is valid.

The previous v1.1 ``AgentRole`` enum hardcoded seven tech/SRE roles, making the
framework unusable for healthcare, finance, legal, and other industries without
modifying core framework code.

The fix:
  - ``agent_role: Optional[str]``         — accepts any role from any domain
  - ``AgentRole``                         — re-exported from ``afmx.domains.tech``
                                             for full backward compatibility
  - ``afmx.domains.*``                    — five built-in domain packs (tech,
                                             finance, healthcare, legal, manufacturing)
  - Custom domains                         — ``DomainPack`` + ``domain_registry``

Backward compatibility
----------------------
All v1.1 code continues to work unchanged::

    # v1.1 — still works
    from afmx.models.node import AgentRole
    node = Node(agent_role=AgentRole.OPS, ...)   # AgentRole.OPS == "OPS"

    # v1.2 — preferred for non-tech domains
    from afmx.domains.finance import FinanceRole
    node = Node(agent_role=FinanceRole.QUANT, ...)   # FinanceRole.QUANT == "QUANT"

    # v1.2 — any string is accepted
    node = Node(agent_role="CLINICIAN", ...)

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Backward-compatible AgentRole re-export ─────────────────────────────────
# Import the tech domain first to trigger auto-registration.
# AgentRole is a plain namespace class (not an Enum) — AgentRole.OPS == "OPS".
from afmx.domains.tech import AgentRole  # noqa: F401 — public re-export

# ─── Agent role validation regex ─────────────────────────────────────────────
# Roles must be: 1–64 chars, uppercase letters/digits/underscores.
# Examples: "QUANT", "RISK_MANAGER", "NURSE", "EXPERT_WITNESS"
_ROLE_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')


# ─── Node type & status ───────────────────────────────────────────────────────

class NodeType(str, Enum):
    TOOL     = "TOOL"
    AGENT    = "AGENT"
    FUNCTION = "FUNCTION"
    MCP      = "MCP"     # v1.1: native MCP server node


class NodeStatus(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    SKIPPED  = "SKIPPED"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"
    ABORTED  = "ABORTED"


# ─── Cognitive layer — the FIXED ROW axis ────────────────────────────────────

class CognitiveLayer(str, Enum):
    """
    What TYPE of thinking this node performs.

    This is the FIXED axis of the Cognitive Execution Matrix.
    It is universal across every industry and domain.
    It never changes.

    ROW order (canonical for DIAGONAL execution mode):
      PERCEIVE  → ingest signals, alerts, documents, telemetry
      RETRIEVE  → fetch knowledge, RAG, DB lookups, log retrieval
      REASON    → analysis, correlation, synthesis          ← premium LLM
      PLAN      → strategy, fix plans, runbooks             ← premium LLM
      ACT       → execute tools, APIs, deployments
      EVALUATE  → validate, test, audit, verify             ← premium LLM
      REPORT    → summarise, escalate, alert

    CognitiveModelRouter tier assignments:
      Cheap  → PERCEIVE, RETRIEVE, ACT, REPORT
      Premium → REASON, PLAN, EVALUATE
    """
    PERCEIVE = "PERCEIVE"
    RETRIEVE = "RETRIEVE"
    REASON   = "REASON"
    PLAN     = "PLAN"
    ACT      = "ACT"
    EVALUATE = "EVALUATE"
    REPORT   = "REPORT"


# ─── Fault-tolerance policies ─────────────────────────────────────────────────

class RetryPolicy(BaseModel):
    retries:             int   = Field(default=3,    ge=0, le=10)
    backoff_seconds:     float = Field(default=1.0,  ge=0.0)
    backoff_multiplier:  float = Field(default=2.0,  ge=1.0)
    max_backoff_seconds: float = Field(default=60.0)
    jitter:              bool  = Field(default=True)


class TimeoutPolicy(BaseModel):
    timeout_seconds: float = Field(default=30.0, ge=0.01)
    hard_kill:       bool  = Field(default=True)


class CircuitBreakerPolicy(BaseModel):
    enabled:                  bool  = Field(default=False)
    failure_threshold:        int   = Field(default=5, ge=1)
    recovery_timeout_seconds: float = Field(default=60.0)
    half_open_max_calls:      int   = Field(default=2)


class NodeConfig(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)
    env:    Dict[str, str] = Field(default_factory=dict)
    tags:   List[str]      = Field(default_factory=list)


# ─── Node ─────────────────────────────────────────────────────────────────────

class Node(BaseModel):
    """
    Core execution unit in AFMX.

    Matrix coordinate fields (v1.1 / v1.2):
    ┌───────────────────────────────────────────────────────────────┐
    │  cognitive_layer  — FIXED axis (CognitiveLayer enum)          │
    │                     Universal across all industries            │
    │                     PERCEIVE → RETRIEVE → REASON → PLAN →     │
    │                     ACT → EVALUATE → REPORT                   │
    ├───────────────────────────────────────────────────────────────┤
    │  agent_role       — OPEN axis (plain string)          v1.2    │
    │                     Domain-specific vocabulary                 │
    │                     "OPS", "QUANT", "CLINICIAN", "PARALEGAL", │
    │                     "ENGINEER" — any valid role string         │
    └───────────────────────────────────────────────────────────────┘

    Both fields are Optional. Nodes without coordinates work exactly
    as before. Existing v1.1 matrices are 100% backward-compatible.

    Role strings must match: [A-Z][A-Z0-9_]{0,63}
    Examples: "OPS", "QUANT", "RISK_MANAGER", "EXPERT_WITNESS"

    Domain packs provide pre-defined constants:
        from afmx.domains.tech         import AgentRole      # OPS, CODER, ...
        from afmx.domains.finance      import FinanceRole     # QUANT, TRADER, ...
        from afmx.domains.healthcare   import HealthcareRole  # CLINICIAN, NURSE, ...
        from afmx.domains.legal        import LegalRole       # PARALEGAL, PARTNER, ...
        from afmx.domains.manufacturing import ManufacturingRole  # ENGINEER, ...
    """
    model_config = ConfigDict(use_enum_values=True)

    id:      str      = Field(default_factory=lambda: str(uuid.uuid4()))
    name:    str      = Field(..., min_length=1, max_length=128)
    type:    NodeType
    handler: str      = Field(..., description="Registry key or dotted module path")

    # ── Matrix coordinate — ROW (fixed enum) ─────────────────────────────────
    cognitive_layer: Optional[CognitiveLayer] = Field(
        default=None,
        description=(
            "Matrix ROW — what type of cognition this node performs. "
            "Fixed universal axis. One of: PERCEIVE, RETRIEVE, REASON, "
            "PLAN, ACT, EVALUATE, REPORT."
        ),
    )

    # ── Matrix coordinate — COLUMN (open string) v1.2 ────────────────────────
    agent_role: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "Matrix COLUMN — which functional domain role this node belongs to. "
            "Open string — any industry vocabulary is valid. "
            "Examples: 'OPS' (tech), 'QUANT' (finance), 'CLINICIAN' (healthcare), "
            "'PARALEGAL' (legal), 'ENGINEER' (manufacturing), or any custom role. "
            "Must match: [A-Z][A-Z0-9_]{0,63}"
        ),
    )

    # ── Fault tolerance ──────────────────────────────────────────────────────
    config:           NodeConfig           = Field(default_factory=NodeConfig)
    retry_policy:     RetryPolicy          = Field(default_factory=RetryPolicy)
    timeout_policy:   TimeoutPolicy        = Field(default_factory=TimeoutPolicy)
    circuit_breaker:  CircuitBreakerPolicy = Field(default_factory=CircuitBreakerPolicy)
    fallback_node_id: Optional[str]        = Field(default=None)

    # ── Scheduling ───────────────────────────────────────────────────────────
    priority: int = Field(default=5, ge=1, le=10)

    # ── Open metadata ────────────────────────────────────────────────────────
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("handler")
    @classmethod
    def validate_handler(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("handler must be a non-empty string")
        return v.strip()

    @field_validator("agent_role")
    @classmethod
    def validate_agent_role(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate the agent_role string format.

        Rules:
          - None is always accepted (node has no role coordinate)
          - Must be 1–64 characters
          - Must match: [A-Z][A-Z0-9_]{0,63}
          - Must start with an uppercase letter
          - Only uppercase letters, digits, and underscores allowed

        Valid examples:   "OPS", "QUANT", "RISK_MANAGER", "EXPERT_WITNESS"
        Invalid examples: "ops", "123ROLE", "risk-manager", "role name"
        """
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("agent_role must not be an empty string")
        if not _ROLE_PATTERN.match(v):
            raise ValueError(
                f"agent_role '{v}' is invalid. Must match [A-Z][A-Z0-9_]{{0,63}}. "
                f"Examples: 'OPS', 'QUANT', 'RISK_MANAGER', 'CLINICIAN'"
            )
        return v

    @property
    def has_matrix_address(self) -> bool:
        """True when both cognitive_layer and agent_role are set."""
        return self.cognitive_layer is not None and self.agent_role is not None


# ─── NodeResult ───────────────────────────────────────────────────────────────

class NodeResult(BaseModel):
    """Captures the outcome of a single node execution."""
    node_id:     str
    node_name:   str
    status:      NodeStatus
    output:      Optional[Any]   = None
    error:       Optional[str]   = None
    error_type:  Optional[str]   = None
    attempt:     int             = Field(default=1)
    started_at:  Optional[float] = None
    finished_at: Optional[float] = None
    duration_ms: Optional[float] = None
    metadata:    Dict[str, Any]  = Field(default_factory=dict)

    # Matrix coordinates captured at execution time for observability
    cognitive_layer: Optional[str] = None   # e.g. "REASON"
    agent_role:      Optional[str] = None   # e.g. "QUANT" (any domain)

    @property
    def is_success(self) -> bool:
        return self.status == NodeStatus.SUCCESS

    @property
    def is_terminal_failure(self) -> bool:
        return self.status in (NodeStatus.FAILED, NodeStatus.ABORTED)
