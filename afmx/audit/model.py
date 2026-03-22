"""
AFMX Audit Event Model

Every significant operation in AFMX is recorded as an AuditEvent:
  - Execution lifecycle (created, completed, failed, cancelled, retried, resumed)
  - Matrix management (saved, deleted, executed)
  - Auth events (success, failure, permission denied)
  - API key management (created, revoked, deleted)
  - Server lifecycle (started, stopped)

Fields are deliberately flat for easy export to CSV, SIEM, and log aggregators.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class AuditAction(str, Enum):
    # Execution lifecycle
    EXECUTION_CREATED   = "execution.created"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED    = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"
    EXECUTION_RETRIED   = "execution.retried"
    EXECUTION_RESUMED   = "execution.resumed"
    EXECUTION_ASYNC     = "execution.async_created"

    # Matrix management
    MATRIX_SAVED        = "matrix.saved"
    MATRIX_DELETED      = "matrix.deleted"
    MATRIX_EXECUTED     = "matrix.executed"

    # API key management
    KEY_CREATED         = "key.created"
    KEY_REVOKED         = "key.revoked"
    KEY_DELETED         = "key.deleted"

    # Auth events
    AUTH_SUCCESS        = "auth.success"
    AUTH_FAILURE        = "auth.failure"     # bad / unknown key
    AUTH_DENIED         = "auth.denied"      # valid key but lacks permission
    AUTH_EXPIRED        = "auth.expired"     # key expired

    # Server lifecycle
    SERVER_STARTED      = "server.started"
    SERVER_STOPPED      = "server.stopped"

    # Custom / catch-all
    CUSTOM              = "custom"


@dataclass
class AuditEvent:
    """
    A single immutable audit record.

    Fields:
      action        — what happened (AuditAction enum value)
      actor         — human-readable name of the caller (key name or "system")
      actor_id      — machine-readable key ID
      actor_role    — role of the caller at the time of the action
      tenant_id     — tenant scope
      resource_type — "execution" | "matrix" | "key" | "server"
      resource_id   — ID of the affected resource
      outcome       — "success" | "failure" | "denied"
      details       — arbitrary k/v payload for context (NOT in CSV export)
      ip_address    — caller IP (from X-Forwarded-For or request.client)
      user_agent    — caller User-Agent header
      duration_ms   — request duration if applicable
      error         — error message on failure
    """
    action: AuditAction

    id: str                         = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float                = field(default_factory=time.time)

    # Caller identity
    actor: str                      = "system"
    actor_id: str                   = ""
    actor_role: str                 = "SYSTEM"
    tenant_id: str                  = "default"

    # Resource
    resource_type: str              = ""
    resource_id: str                = ""

    # Outcome
    outcome: str                    = "success"      # success | failure | denied

    # Context
    details: Dict[str, Any]         = field(default_factory=dict)
    ip_address: Optional[str]       = None
    user_agent: Optional[str]       = None
    duration_ms: Optional[float]    = None
    error: Optional[str]            = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":            self.id,
            "timestamp":     self.timestamp,
            "action":        self.action,
            "actor":         self.actor,
            "actor_id":      self.actor_id,
            "actor_role":    self.actor_role,
            "tenant_id":     self.tenant_id,
            "resource_type": self.resource_type,
            "resource_id":   self.resource_id,
            "outcome":       self.outcome,
            "details":       self.details,
            "ip_address":    self.ip_address,
            "user_agent":    self.user_agent,
            "duration_ms":   self.duration_ms,
            "error":         self.error,
        }
