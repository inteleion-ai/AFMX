"""
AFMX Domain Pack — Technology / SRE / DevOps
=============================================

The DEFAULT domain pack. These are the roles used in software engineering,
site reliability engineering, platform engineering, and DevOps teams.

This module also provides the ``AgentRole`` constants class for backward
compatibility with AFMX v1.1 code that used the old enum syntax:

    node = Node(
        agent_role=AgentRole.OPS,   # still works — returns the string "OPS"
        ...
    )

For new code, prefer passing role strings directly:

    node = Node(agent_role="OPS", ...)

Apache-2.0 License. See LICENSE for details.
"""
from afmx.domains import DomainPack, domain_registry

# ─── Role constants (backward-compatible namespace) ───────────────────────────

class AgentRole:
    """
    Tech/SRE domain role string constants.

    Provided for backward compatibility with v1.1 code. These are plain
    strings — not an Enum — so any string is accepted as agent_role on a Node.

    For non-tech domains, import the appropriate domain pack instead:

        from afmx.domains.finance      import FinanceDomain
        from afmx.domains.healthcare   import HealthcareDomain
        from afmx.domains.legal        import LegalDomain
        from afmx.domains.manufacturing import ManufacturingDomain
    """
    # Core engineering
    RESEARCHER = "RESEARCHER"   # Research, investigation, information gathering
    CODER      = "CODER"        # Code generation, implementation, debugging
    ANALYST    = "ANALYST"      # Data analysis, metrics, correlation
    OPS        = "OPS"          # Operations, incident response, deployment
    COMPLIANCE = "COMPLIANCE"   # Policy enforcement, regulatory checks
    VERIFIER   = "VERIFIER"     # Testing, QA, validation, review
    PLANNER    = "PLANNER"      # Architecture, strategy, roadmap

    # All tech domain roles as a frozenset
    ALL: frozenset = frozenset({
        "RESEARCHER", "CODER", "ANALYST", "OPS",
        "COMPLIANCE", "VERIFIER", "PLANNER",
    })

    def __class_getitem__(cls, item: str) -> str:
        """Support AgentRole["OPS"] as an alternative access pattern."""
        return getattr(cls, item)


# ─── Domain pack definition ───────────────────────────────────────────────────

TechDomain = DomainPack(
    name="tech",
    description=(
        "Technology, software engineering, and site reliability engineering. "
        "Default domain for AFMX — SRE incident response, CI/CD automation, "
        "platform engineering, DevOps workflows."
    ),
    roles={
        "RESEARCHER": "Research, investigation, document retrieval and synthesis",
        "CODER":      "Code generation, implementation, debugging, refactoring",
        "ANALYST":    "Data analysis, metrics interpretation, root-cause correlation",
        "OPS":        "Operations, incident response, deployment, infrastructure",
        "COMPLIANCE": "Policy enforcement, security checks, regulatory alignment",
        "VERIFIER":   "Testing, QA, validation, code review, acceptance criteria",
        "PLANNER":    "Architecture decisions, sprint planning, roadmap strategy",
    },
    tags=["tech", "sre", "devops", "software", "platform", "incident-response"],
)

# Auto-register on import
domain_registry.register(TechDomain)
