# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
AFMX Domain Packs
=================

The COLUMN axis of the Cognitive Execution Matrix is *open* — any industry,
any organisation, any team can define their own agent roles.

The ROW axis (CognitiveLayer) is fixed forever — PERCEIVE -> RETRIEVE -> REASON
-> PLAN -> ACT -> EVALUATE -> REPORT is universal across every domain.

Domain packs give each vertical its own vocabulary without changing a single
line of the execution engine.

Usage::

    from afmx.domains.tech import TechDomain, AgentRole
    from afmx.domains.finance import FinanceDomain
    from afmx.domains.healthcare import HealthcareDomain
    from afmx.domains.legal import LegalDomain
    from afmx.domains.manufacturing import ManufacturingDomain

    # Custom domain
    from afmx.domains import DomainPack, domain_registry

    my_domain = DomainPack(
        name="logistics",
        description="Logistics and supply chain agent roles",
        roles={
            "DISPATCHER": "Assign routes and vehicles",
            "TRACKER":    "Monitor shipment status",
            "ANALYST":    "Demand forecasting and optimisation",
        },
        tags=["logistics", "supply-chain"],
    )
    domain_registry.register(my_domain)

Apache-2.0 License. See LICENSE for details.
"""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional


@dataclass(frozen=True)
class DomainPack:
    """A named set of agent role strings for a specific industry or function."""

    name: str
    description: str
    roles: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

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
            "name": self.name,
            "description": self.description,
            "roles": self.roles,
            "tags": self.tags,
            "role_count": len(self.roles),
        }

    def __str__(self) -> str:
        return f"DomainPack({self.name!r}, {len(self.roles)} roles)"


class DomainRegistry:
    """Global registry of domain packs. Thread-safe for reads."""

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
        """Find the first domain pack that contains this role and return its description."""
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


#: Global singleton domain registry.
domain_registry = DomainRegistry()
