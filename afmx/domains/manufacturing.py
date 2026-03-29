"""
AFMX Domain Pack — Manufacturing & Industrial
==============================================

Roles for manufacturing plants, industrial IoT, supply chain,
predictive maintenance, and quality management systems.

Industrial AI is one of the fastest-growing segments in 2026 —
predictive maintenance, quality control, and supply chain optimisation
are actively automated at scale. The cognitive layer sequence maps
naturally to factory-floor and supply-chain decision workflows.

Usage::

    from afmx.domains.manufacturing import ManufacturingDomain, ManufacturingRole

    node = Node(
        name="fault-diagnosis",
        type=NodeType.AGENT,
        handler="predictive_maintenance_model",
        cognitive_layer="REASON",
        agent_role=ManufacturingRole.ENGINEER,
    )

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

from afmx.domains import DomainPack, domain_registry


class ManufacturingRole:
    """Manufacturing and industrial role string constants."""
    ENGINEER           = "ENGINEER"           # Process/manufacturing engineering
    QUALITY_INSPECTOR  = "QUALITY_INSPECTOR"  # Quality control and assurance
    MAINTENANCE_TECH   = "MAINTENANCE_TECH"   # Predictive and preventive maintenance
    SAFETY_OFFICER     = "SAFETY_OFFICER"     # HSE compliance and incident prevention
    PROCESS_MANAGER    = "PROCESS_MANAGER"    # Production scheduling and optimisation
    OPERATOR           = "OPERATOR"           # Machine operation and monitoring
    SUPPLY_PLANNER     = "SUPPLY_PLANNER"     # Supply chain and inventory planning

    ALL: frozenset = frozenset({
        "ENGINEER", "QUALITY_INSPECTOR", "MAINTENANCE_TECH", "SAFETY_OFFICER",
        "PROCESS_MANAGER", "OPERATOR", "SUPPLY_PLANNER",
    })


ManufacturingDomain = DomainPack(
    name="manufacturing",
    description=(
        "Manufacturing, industrial IoT, and supply chain. Covers factory-floor "
        "automation, predictive maintenance, quality management, HSE compliance, "
        "and supply chain optimisation for manufacturers and industrial platforms."
    ),
    roles={
        "ENGINEER":          "Process design, root cause analysis, specification development",
        "QUALITY_INSPECTOR": "Defect detection, SPC, quality gate evaluation, certification",
        "MAINTENANCE_TECH":  "Predictive maintenance, fault diagnosis, repair execution",
        "SAFETY_OFFICER":    "HSE compliance, risk assessment, incident investigation",
        "PROCESS_MANAGER":   "Production scheduling, OEE optimisation, shift management",
        "OPERATOR":          "Machine monitoring, process control, real-time response",
        "SUPPLY_PLANNER":    "Demand forecasting, inventory optimisation, supplier management",
    },
    tags=["manufacturing", "industrial", "iot", "supply-chain", "predictive-maintenance",
          "quality", "hse", "factory"],
)

domain_registry.register(ManufacturingDomain)
