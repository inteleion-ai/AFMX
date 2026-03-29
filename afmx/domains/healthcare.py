"""
AFMX Domain Pack — Healthcare & Clinical
=========================================

Roles for clinical workflows, hospital operations, medical research,
and digital health platforms.

Usage::

    from afmx.domains.healthcare import HealthcareDomain, HealthcareRole

    node = Node(
        name="differential-diagnosis",
        type=NodeType.AGENT,
        handler="diagnostic_model",
        cognitive_layer="REASON",
        agent_role=HealthcareRole.CLINICIAN,
    )

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

from afmx.domains import DomainPack, domain_registry


class HealthcareRole:
    """Healthcare and clinical role string constants."""
    CLINICIAN     = "CLINICIAN"     # Physician / clinician — diagnosis and treatment
    PHARMACIST    = "PHARMACIST"    # Medication management, drug interaction checks
    RADIOLOGIST   = "RADIOLOGIST"  # Medical imaging interpretation
    NURSE         = "NURSE"         # Patient care coordination and monitoring
    ADMINISTRATOR = "ADMINISTRATOR" # Hospital operations, scheduling, billing
    RESEARCHER    = "RESEARCHER"    # Clinical research, trial management
    ASSESSOR      = "ASSESSOR"      # Quality assessment, outcome evaluation

    ALL: frozenset = frozenset({
        "CLINICIAN", "PHARMACIST", "RADIOLOGIST", "NURSE",
        "ADMINISTRATOR", "RESEARCHER", "ASSESSOR",
    })


HealthcareDomain = DomainPack(
    name="healthcare",
    description=(
        "Healthcare, clinical operations, and digital health. Covers clinical "
        "decision support, care coordination, hospital operations, and medical "
        "research workflows for health systems, clinics, and health-tech platforms."
    ),
    roles={
        "CLINICIAN":     "Clinical diagnosis, treatment planning, patient assessment",
        "PHARMACIST":    "Medication reconciliation, drug interaction checking, dispensing",
        "RADIOLOGIST":   "Medical image analysis, imaging report generation",
        "NURSE":         "Patient monitoring, care coordination, triage support",
        "ADMINISTRATOR": "Scheduling, billing, compliance, capacity management",
        "RESEARCHER":    "Clinical trial design, literature review, outcome analysis",
        "ASSESSOR":      "Quality of care evaluation, outcome measurement, accreditation",
    },
    tags=["healthcare", "clinical", "hospital", "digital-health", "medtech", "ehr"],
)

domain_registry.register(HealthcareDomain)
