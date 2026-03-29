"""
AFMX Domain Pack — Legal & Compliance
=======================================

Roles for law firms, in-house legal teams, compliance departments,
regulatory bodies, and legaltech platforms.

The cognitive layer sequence maps almost exactly to legal reasoning doctrine:
  PERCEIVE  → fact gathering
  RETRIEVE  → precedent and statute retrieval
  REASON    → legal analysis (the core of legal work)
  PLAN      → litigation or transaction strategy
  ACT       → filing, negotiation, execution
  EVALUATE  → outcome assessment, appeal evaluation
  REPORT    → brief, memo, client communication

Usage::

    from afmx.domains.legal import LegalDomain, LegalRole

    node = Node(
        name="precedent-analysis",
        type=NodeType.AGENT,
        handler="legal_research_model",
        cognitive_layer="REASON",
        agent_role=LegalRole.ASSOCIATE,
    )

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

from afmx.domains import DomainPack, domain_registry


class LegalRole:
    """Legal and compliance role string constants."""
    PARALEGAL      = "PARALEGAL"      # Legal research, document review, case preparation
    ASSOCIATE      = "ASSOCIATE"      # Legal analysis, drafting, client advice
    PARTNER        = "PARTNER"        # Strategic decisions, client management, oversight
    EXPERT_WITNESS = "EXPERT_WITNESS" # Technical domain expertise for proceedings
    CLERK          = "CLERK"          # Court filings, docket management, admin
    JUDGE          = "JUDGE"          # Decision-making, ruling, adjudication
    NOTARY         = "NOTARY"         # Document authentication, certification

    ALL: frozenset = frozenset({
        "PARALEGAL", "ASSOCIATE", "PARTNER", "EXPERT_WITNESS",
        "CLERK", "JUDGE", "NOTARY",
    })


LegalDomain = DomainPack(
    name="legal",
    description=(
        "Legal, compliance, and regulatory. Covers law firm workflows, "
        "in-house legal operations, contract analysis, litigation support, "
        "and regulatory compliance for legal teams and legaltech platforms."
    ),
    roles={
        "PARALEGAL":      "Legal research, document review, case file preparation, citation check",
        "ASSOCIATE":      "Legal analysis, contract drafting, client advisory memos",
        "PARTNER":        "Strategic oversight, client relationship, settlement authority",
        "EXPERT_WITNESS": "Technical domain expertise, report preparation for proceedings",
        "CLERK":          "Court filings, docket tracking, administrative coordination",
        "JUDGE":          "Ruling, decision-making, legal reasoning adjudication",
        "NOTARY":         "Document authentication, certification, notarisation",
    },
    tags=["legal", "law", "compliance", "legaltech", "litigation", "contracts", "regulatory"],
)

domain_registry.register(LegalDomain)
