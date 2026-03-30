"""
AFMX Domain Packs
=================

The COLUMN axis of the Cognitive Execution Matrix is *open* — any industry,
any organisation, any team can define their own agent roles.

The ROW axis (CognitiveLayer) is fixed forever — PERCEIVE → RETRIEVE → REASON
→ PLAN → ACT → EVALUATE → REPORT is universal across every domain.

The COLUMN axis is pluggable — CODER makes no sense in a hospital; CLINICIAN
makes no sense in a software company. Domain packs give each vertical its own
vocabulary without changing a single line of the execution engine.

Usage
-----
    # Tech / SRE (default)
    from afmx.domains.tech import TechDomain, AgentRole

    # Finance
    from afmx.domains.finance import FinanceDomain

    # Healthcare
    from afmx.domains.healthcare import HealthcareDomain

    # Legal
    from afmx.domains.legal import LegalDomain

    # Manufacturing / Industrial
    from afmx.domains.manufacturing import ManufacturingDomain

    # Custom domain
    from afmx.domains import DomainPack, domain_registry

    my_domain = DomainPack(
        name="logistics",
        description="Logistics and supply chain agent roles",
        roles={
            "DISPATCHER":   "Assign routes and vehicles",
            "TRACKER":      "Monitor shipment status",
            "ANALYST":      "Demand forecasting and optimisation",
            "COORDINATOR":  "Cross-carrier coordination",
            "COMPLIANCE":   "Customs and regulatory checks",
            "VERIFIER":     "Delivery confirmation",
            "REPORTER":     "KPI and SLA reporting",
        },
        tags=["logistics", "supply-chain", "transport"],
    )
    domain_registry.register(my_domain)

Apache-2.0 License. See LICENSE for details.
"""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional


# ─── DomainPack ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DomainPack:
    """
    A named set of agent role strings for a specific industry or function.

    Each domain pack defines:
      - name        — short identifier (e.g. "finance", "healthcare")
      - description — human-readable summary
      - roles       — mapping of ROLE_NAME → description
      - tags        — searchable tags

    Roles are plain strings — no enum, no restriction. Any string that is
    uppercase and contains only letters, digits, and underscores is valid.

    The DomainPack is immutable after construction (frozen dataclass).
    """
    name:        str
    description: str
    roles:       Dict[str, str]   = field(default_factory=dict)
    tags:        List[str]        = field(default_factory=list)

    @property
    def role_names(self) -> FrozenSet[str]:
        """Frozenset of all role name strings in this domain."""
        return frozenset(self.roles.keys())

    def contains(self, role: str) -> bool:
        """True if the given role name exists in this domain pack."""
        return role in self.roles

    def describe(self, role: str) -> Optional[str]:
        """Return the human-readable description for a role, or None."""
        return self.roles.get(role)

    def to_dict(self) -> dict:
        """Serialise to a plain dict for API responses."""
        return {
            "name":        self.name,
            "description": self.description,
            "roles":       self.roles,
            "tags":        self.tags,
            "role_count":  len(self.roles),
        }

    def __str__(self) -> str:
        return f"DomainPack({self.name!r}, {len(self.roles)} roles)"


# ─── Domain Registry ──────────────────────────────────────────────────────────

class DomainRegistry:
    """
    Global registry of domain packs.

    Thread-safe for reads. Writes are only expected at startup.
    """

    def __init__(self) -> None:
        self._packs: Dict[str, DomainPack] = {}

    def register(self, pack: DomainPack) -> None:
        """Register a domain pack. Overwrites if name already exists."""
        self._packs[pack.name] = pack

    def get(self, name: str) -> Optional[DomainPack]:
        """Return a domain pack by name, or None."""
        return self._packs.get(name)

    def list_all(self) -> List[Dict]:
        """Return all registered domain packs as plain dicts."""
        return [p.to_dict() for p in sorted(self._packs.values(), key=lambda p: p.name)]

    def resolve_role(self, role: str) -> Optional[str]:
        """
        Find the first domain pack that contains this role and return its description.
        Returns None if no domain pack recognises the role.
        """
        for pack in self._packs.values():
            desc = pack.describe(role)
            if desc is not None:
                return desc
        return None

    def find_domain_for_role(self, role: str) -> Optional[str]:
        """Return the name of the first domain pack that contains this role."""
        for pack in self._packs.values():
            if pack.contains(role):
                return pack.name
        return None

    def __len__(self) -> int:
        return len(self._packs)

    def __contains__(self, name: str) -> bool:
        return name in self._packs


# ─── Global registry instance ─────────────────────────────────────────────────

domain_registry = DomainRegistry()
