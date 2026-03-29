"""
AFMX Domain Pack — Finance & Capital Markets
=============================================

Roles for quantitative finance, trading desks, risk management,
investment management, and fintech teams.

Usage::

    from afmx.domains.finance import FinanceDomain, FinanceRole

    node = Node(
        name="risk-scorer",
        type=NodeType.AGENT,
        handler="risk_model",
        cognitive_layer="REASON",
        agent_role=FinanceRole.RISK_MANAGER,
    )

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

from afmx.domains import DomainPack, domain_registry


class FinanceRole:
    """Finance & capital markets role string constants."""
    QUANT             = "QUANT"             # Quantitative model development and research
    TRADER            = "TRADER"            # Order execution and market-making
    RISK_MANAGER      = "RISK_MANAGER"      # Risk assessment, VaR, exposure management
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER" # Portfolio construction and allocation
    COMPLIANCE_OFFICER= "COMPLIANCE_OFFICER"# Regulatory compliance, trade surveillance
    ANALYST           = "ANALYST"           # Market research, financial analysis
    AUDITOR           = "AUDITOR"           # Audit, reconciliation, reporting

    ALL: frozenset = frozenset({
        "QUANT", "TRADER", "RISK_MANAGER", "PORTFOLIO_MANAGER",
        "COMPLIANCE_OFFICER", "ANALYST", "AUDITOR",
    })


FinanceDomain = DomainPack(
    name="finance",
    description=(
        "Finance, capital markets, and fintech. Covers quantitative trading, "
        "risk management, portfolio management, and regulatory compliance "
        "workflows for banks, hedge funds, and fintech platforms."
    ),
    roles={
        "QUANT":              "Quantitative model research, factor development, backtesting",
        "TRADER":             "Order execution, market-making, position management",
        "RISK_MANAGER":       "Risk measurement (VaR, CVaR), exposure monitoring, limits",
        "PORTFOLIO_MANAGER":  "Asset allocation, portfolio construction, rebalancing",
        "COMPLIANCE_OFFICER": "Regulatory reporting, trade surveillance, sanctions screening",
        "ANALYST":            "Market research, earnings analysis, sector coverage",
        "AUDITOR":            "Trade reconciliation, P&L attribution, audit trails",
    },
    tags=["finance", "trading", "risk", "capital-markets", "fintech", "banking", "investment"],
)

domain_registry.register(FinanceDomain)
