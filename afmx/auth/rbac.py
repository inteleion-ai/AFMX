"""
AFMX RBAC — Role-Based Access Control

Roles (ascending privilege):
    VIEWER    — read-only across executions, matrices, plugins, audit
    SERVICE   — execute + read  (CI / service-to-service accounts)
    DEVELOPER — execute, cancel, retry, resume; read everything; no matrix write
    OPERATOR  — full execution + matrix management; audit export; no key admin
    ADMIN     — every permission including key management

Permission model: "<resource>:<action>" strings.
Role → permission set is statically defined here; individual keys may carry
an optional `permission_overrides` set that REPLACES the role default.

Design rules:
  - No inheritance between roles (explicit permission sets only)
  - Permission check is a single frozenset lookup — O(1)
  - API keys store the plain-text key; the store also indexes by key_id
  - All AFMX API keys begin with the prefix "afmx_" for easy scanning
"""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set

# ─── Role ─────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    VIEWER    = "VIEWER"
    SERVICE   = "SERVICE"
    DEVELOPER = "DEVELOPER"
    OPERATOR  = "OPERATOR"
    ADMIN     = "ADMIN"


# ─── Permissions ──────────────────────────────────────────────────────────────

ALL_PERMISSIONS: FrozenSet[str] = frozenset({
    # Execution lifecycle
    "execution:execute",
    "execution:read",
    "execution:cancel",
    "execution:retry",
    "execution:resume",
    # Matrix management
    "matrix:write",
    "matrix:read",
    "matrix:delete",
    "matrix:execute",
    # Discovery
    "plugin:read",
    "adapter:read",
    "hook:read",
    # Audit
    "audit:read",
    "audit:export",
    # Admin — API key management
    "admin:read",
    "admin:write",
    # Observability
    "metrics:read",
})

ROLE_PERMISSIONS: Dict[Role, FrozenSet[str]] = {
    Role.VIEWER: frozenset({
        "execution:read",
        "matrix:read",
        "plugin:read", "adapter:read", "hook:read",
        "audit:read",
        "metrics:read",
    }),
    Role.SERVICE: frozenset({
        "execution:execute", "execution:read",
        "matrix:read", "matrix:execute",
    }),
    Role.DEVELOPER: frozenset({
        "execution:execute", "execution:read",
        "execution:cancel", "execution:retry", "execution:resume",
        "matrix:read", "matrix:execute",
        "plugin:read", "adapter:read", "hook:read",
        "metrics:read",
    }),
    Role.OPERATOR: frozenset({
        "execution:execute", "execution:read",
        "execution:cancel", "execution:retry", "execution:resume",
        "matrix:write", "matrix:read", "matrix:delete", "matrix:execute",
        "plugin:read", "adapter:read", "hook:read",
        "audit:read", "audit:export",
        "metrics:read",
    }),
    Role.ADMIN: ALL_PERMISSIONS,
}


# ─── Endpoint → Permission mapping ────────────────────────────────────────────
# Tuples of (HTTP_METHOD, PATH_PREFIX, REQUIRED_PERMISSION).
# Evaluated in order — first match wins.
# More specific prefixes must come before shorter ones.

PERMISSION_MAP: List[tuple] = [
    # Admin — key management
    ("POST",   "/afmx/admin",              "admin:write"),
    ("DELETE", "/afmx/admin",              "admin:write"),
    ("GET",    "/afmx/admin",              "admin:read"),
    # Audit
    ("GET",    "/afmx/audit/export",       "audit:export"),
    ("GET",    "/afmx/audit",              "audit:read"),
    # Execution — specific actions before generic prefixes
    ("POST",   "/afmx/cancel",             "execution:cancel"),
    ("POST",   "/afmx/retry",              "execution:retry"),
    ("POST",   "/afmx/resume",             "execution:resume"),
    ("POST",   "/afmx/execute",            "execution:execute"),
    ("GET",    "/afmx/status",             "execution:read"),
    ("GET",    "/afmx/result",             "execution:read"),
    ("GET",    "/afmx/executions",         "execution:read"),
    ("POST",   "/afmx/validate",           "execution:execute"),
    # Matrices
    ("DELETE", "/afmx/matrices",           "matrix:delete"),
    ("POST",   "/afmx/matrices",           "matrix:write"),
    ("GET",    "/afmx/matrices",           "matrix:read"),
    # Discovery
    ("GET",    "/afmx/plugins",            "plugin:read"),
    ("GET",    "/afmx/adapters",           "adapter:read"),
    ("GET",    "/afmx/hooks",              "hook:read"),
    # Observability
    ("GET",    "/metrics",                 "metrics:read"),
    ("GET",    "/afmx/concurrency",        "metrics:read"),
]

# Paths that are always public regardless of RBAC settings
PUBLIC_PATHS: frozenset = frozenset({
    "/health",
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/afmx/ui",
    "/afmx/static",
})


def get_required_permission(method: str, path: str) -> Optional[str]:
    """
    Return the permission string required for the given HTTP method + path.
    Returns None if the endpoint is public or not in the permission map.
    """
    # Public paths pass through unconditionally
    for pub in PUBLIC_PATHS:
        if path == pub or path.startswith(pub + "/"):
            return None

    method = method.upper()
    for pm, pp, perm in PERMISSION_MAP:
        if method == pm and path.startswith(pp):
            return perm

    return None  # Unknown endpoints are public by default


def has_permission(role: Role, permission: str) -> bool:
    """Check whether a role grants a given permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


# ─── API Key ──────────────────────────────────────────────────────────────────

@dataclass
class APIKey:
    """
    An AFMX API key.

    Keys are stored in plain text in the key store (protected by the store's
    access controls). The key_hash() method provides a SHA-256 digest for
    situations where you must not store the raw key.
    """
    id: str                          = field(default_factory=lambda: str(uuid.uuid4()))
    key: str                         = field(
        default_factory=lambda: f"afmx_{secrets.token_urlsafe(32)}"
    )
    name: str                        = ""
    role: Role                       = Role.DEVELOPER
    tenant_id: str                   = "default"
    created_at: float                = field(default_factory=time.time)
    expires_at: Optional[float]      = None
    active: bool                     = True
    permission_overrides: Set[str]   = field(default_factory=set)
    created_by: Optional[str]        = None
    last_used_at: Optional[float]    = None
    description: str                 = ""

    @property
    def permissions(self) -> FrozenSet[str]:
        """Effective permissions — overrides replace role defaults if set."""
        if self.permission_overrides:
            return frozenset(self.permission_overrides)
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    def is_valid(self) -> bool:
        """True if the key is active and not expired."""
        if not self.active:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def key_hash(self) -> str:
        """SHA-256 of the raw key — safe for external storage."""
        return hashlib.sha256(self.key.encode()).hexdigest()

    def to_dict(self, *, redact: bool = True) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": (self.key[:12] + "..." + self.key[-4:]) if redact else self.key,
            "name": self.name,
            "role": self.role.value,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "active": self.active,
            "permissions": sorted(self.permissions),
            "description": self.description,
            "last_used_at": self.last_used_at,
            "created_by": self.created_by,
        }


# ─── Principal ────────────────────────────────────────────────────────────────

@dataclass
class Principal:
    """
    Resolved caller identity — injected into request.state.principal
    by RBACMiddleware.  Handlers can read this without touching headers.
    """
    key_id: str
    key_name: str
    role: Role
    tenant_id: str
    permissions: FrozenSet[str]
    key_preview: str          # first 16 chars — safe to log

    @classmethod
    def from_api_key(cls, key: APIKey) -> "Principal":
        return cls(
            key_id=key.id,
            key_name=key.name,
            role=key.role,
            tenant_id=key.tenant_id,
            permissions=key.permissions,
            key_preview=key.key[:16],
        )

    @classmethod
    def system(cls) -> "Principal":
        """Anonymous / system principal used when RBAC is disabled."""
        return cls(
            key_id="system",
            key_name="system",
            role=Role.ADMIN,
            tenant_id="default",
            permissions=ALL_PERMISSIONS,
            key_preview="system",
        )

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_name": self.key_name,
            "role": self.role.value,
            "tenant_id": self.tenant_id,
        }
