"""
Unit tests — v1.2 Cognitive Execution Matrix (open column axis)

Covers:
  - CognitiveLayer enum (fixed, universal)
  - AgentRole backward-compat constants class (not an Enum)
  - MatrixAddress with open string role
  - CognitiveModelRouter — tier routing, hint injection
  - Node.agent_role — open string field with validation
  - Node.has_matrix_address — works with any role string
  - ExecutionMatrix helpers — get_nodes_at_role(str), build_matrix_map, coverage
  - Domain packs — DomainPack, DomainRegistry, built-in packs
  - Cross-domain matrix — tech + finance roles in same matrix
  - Backward compatibility — v1.1 code using AgentRole.OPS still works
"""
from __future__ import annotations

import pytest

from afmx.core.cognitive_router import CognitiveModelRouter
from afmx.domains import DomainPack, DomainRegistry, domain_registry
from afmx.domains.finance import FinanceDomain, FinanceRole
from afmx.domains.healthcare import HealthcareDomain, HealthcareRole
from afmx.domains.legal import LegalDomain, LegalRole
from afmx.domains.manufacturing import ManufacturingDomain, ManufacturingRole
from afmx.domains.tech import AgentRole, TechDomain
from afmx.models.execution import ExecutionContext
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, MatrixAddress
from afmx.models.node import CognitiveLayer, Node, NodeType


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_node(
    name:    str,
    layer:   CognitiveLayer | None = None,
    role:    str | None = None,
    handler: str = "echo",
) -> Node:
    return Node(
        name=name,
        type=NodeType.TOOL,
        handler=handler,
        cognitive_layer=layer,
        agent_role=role,
    )


# ─── CognitiveLayer (fixed axis — must never break) ───────────────────────────

class TestCognitiveLayer:
    def test_all_seven_layers_defined(self):
        assert len(list(CognitiveLayer)) == 7

    def test_exact_layer_values(self):
        names = {l.value for l in CognitiveLayer}
        assert names == {"PERCEIVE", "RETRIEVE", "REASON", "PLAN", "ACT", "EVALUATE", "REPORT"}

    def test_layer_from_string(self):
        assert CognitiveLayer("REASON") == CognitiveLayer.REASON

    def test_invalid_layer_raises(self):
        with pytest.raises(ValueError):
            CognitiveLayer("BOGUS")


# ─── AgentRole — backward-compat constants class ──────────────────────────────

class TestAgentRoleBackwardCompat:
    """
    AgentRole is no longer an Enum. It is a plain namespace class.
    All v1.1 code that uses AgentRole.OPS, AgentRole.ANALYST, etc.
    must continue to work — those attributes return plain strings.
    """

    def test_agentRole_ops_is_string(self):
        assert AgentRole.OPS == "OPS"
        assert isinstance(AgentRole.OPS, str)

    def test_agentRole_all_constants_are_strings(self):
        for attr in ("RESEARCHER", "CODER", "ANALYST", "OPS",
                     "COMPLIANCE", "VERIFIER", "PLANNER"):
            val = getattr(AgentRole, attr)
            assert isinstance(val, str), f"AgentRole.{attr} is not a str"
            assert val == attr

    def test_agentRole_ALL_frozenset(self):
        assert isinstance(AgentRole.ALL, frozenset)
        assert len(AgentRole.ALL) == 7
        assert "OPS" in AgentRole.ALL

    def test_agentRole_not_enum(self):
        """AgentRole is a namespace, not an Enum — do not iterate it as an enum."""
        import enum
        assert not isinstance(AgentRole, type(enum.Enum))

    def test_agentRole_used_as_node_role(self):
        """v1.1 pattern: node = Node(agent_role=AgentRole.OPS, ...)"""
        node = make_node("n", layer=CognitiveLayer.ACT, role=AgentRole.OPS)
        assert node.agent_role == "OPS"


# ─── Node.agent_role — open string field ──────────────────────────────────────

class TestNodeAgentRoleOpenString:
    def test_tech_role_accepted(self):
        node = make_node("n", role="OPS")
        assert node.agent_role == "OPS"

    def test_finance_role_accepted(self):
        node = make_node("n", role="QUANT")
        assert node.agent_role == "QUANT"

    def test_healthcare_role_accepted(self):
        node = make_node("n", role="CLINICIAN")
        assert node.agent_role == "CLINICIAN"

    def test_legal_role_accepted(self):
        node = make_node("n", role="PARALEGAL")
        assert node.agent_role == "PARALEGAL"

    def test_manufacturing_role_accepted(self):
        node = make_node("n", role="QUALITY_INSPECTOR")
        assert node.agent_role == "QUALITY_INSPECTOR"

    def test_custom_role_accepted(self):
        node = make_node("n", role="DISPATCHERS_COORDINATOR")
        assert node.agent_role == "DISPATCHERS_COORDINATOR"

    def test_none_accepted(self):
        node = make_node("n", role=None)
        assert node.agent_role is None

    def test_lowercase_role_rejected(self):
        with pytest.raises(Exception):
            make_node("n", role="ops")

    def test_hyphenated_role_rejected(self):
        with pytest.raises(Exception):
            make_node("n", role="RISK-MANAGER")

    def test_space_in_role_rejected(self):
        with pytest.raises(Exception):
            make_node("n", role="RISK MANAGER")

    def test_empty_string_rejected(self):
        with pytest.raises(Exception):
            make_node("n", role="")

    def test_role_too_long_rejected(self):
        with pytest.raises(Exception):
            make_node("n", role="A" * 65)

    def test_has_matrix_address_with_any_role(self):
        for role in ["OPS", "QUANT", "CLINICIAN", "PARALEGAL", "ENGINEER"]:
            node = make_node("n", layer=CognitiveLayer.REASON, role=role)
            assert node.has_matrix_address is True

    def test_no_matrix_address_without_role(self):
        node = make_node("n", layer=CognitiveLayer.REASON)
        assert node.has_matrix_address is False

    def test_no_matrix_address_without_layer(self):
        node = make_node("n", role="OPS")
        assert node.has_matrix_address is False


# ─── MatrixAddress — open string role ─────────────────────────────────────────

class TestMatrixAddress:
    def test_tech_role(self):
        addr = MatrixAddress(layer=CognitiveLayer.REASON, role="COMPLIANCE")
        assert str(addr) == "REASON×COMPLIANCE"

    def test_finance_role(self):
        addr = MatrixAddress(layer=CognitiveLayer.PLAN, role="QUANT")
        assert str(addr) == "PLAN×QUANT"

    def test_healthcare_role(self):
        addr = MatrixAddress(layer=CognitiveLayer.ACT, role="CLINICIAN")
        assert str(addr) == "ACT×CLINICIAN"

    def test_equality_same_domain(self):
        a = MatrixAddress(layer=CognitiveLayer.EVALUATE, role="VERIFIER")
        b = MatrixAddress(layer=CognitiveLayer.EVALUATE, role="VERIFIER")
        assert a == b

    def test_equality_cross_domain(self):
        """Same string = same address regardless of which domain it came from."""
        addr_from_tech    = MatrixAddress(layer=CognitiveLayer.REASON, role=AgentRole.ANALYST)
        addr_from_string  = MatrixAddress(layer=CognitiveLayer.REASON, role="ANALYST")
        assert addr_from_tech == addr_from_string

    def test_inequality_different_role_same_layer(self):
        a = MatrixAddress(layer=CognitiveLayer.REASON, role="ANALYST")
        b = MatrixAddress(layer=CognitiveLayer.REASON, role="QUANT")
        assert a != b

    def test_hashable_in_dict(self):
        a = MatrixAddress(layer=CognitiveLayer.PLAN, role="RISK_MANAGER")
        b = MatrixAddress(layer=CognitiveLayer.PLAN, role="RISK_MANAGER")
        d = {a: "result"}
        assert d[b] == "result"

    def test_hashable_in_set(self):
        addrs = {
            MatrixAddress(layer=CognitiveLayer.PERCEIVE, role="OPS"),
            MatrixAddress(layer=CognitiveLayer.PERCEIVE, role="OPS"),   # dup
            MatrixAddress(layer=CognitiveLayer.PERCEIVE, role="NURSE"),
        }
        assert len(addrs) == 2

    def test_invalid_role_lowercase(self):
        with pytest.raises(Exception):
            MatrixAddress(layer=CognitiveLayer.ACT, role="ops")

    def test_invalid_role_hyphen(self):
        with pytest.raises(Exception):
            MatrixAddress(layer=CognitiveLayer.ACT, role="RISK-MANAGER")


# ─── ExecutionMatrix helpers — open roles ─────────────────────────────────────

def _make_cross_domain_matrix() -> ExecutionMatrix:
    """Matrix that mixes tech and finance domain roles."""
    nodes = [
        make_node("alert-detect",   CognitiveLayer.PERCEIVE,  "OPS"),         # tech
        make_node("market-signal",  CognitiveLayer.PERCEIVE,  "ANALYST"),     # tech/finance
        make_node("quant-analysis", CognitiveLayer.REASON,    "QUANT"),       # finance
        make_node("risk-scoring",   CognitiveLayer.REASON,    "RISK_MANAGER"),# finance
        make_node("exec-trade",     CognitiveLayer.ACT,       "TRADER"),      # finance
        make_node("verify-result",  CognitiveLayer.EVALUATE,  "VERIFIER"),    # tech
        make_node("plain-node"),    # no coordinates
    ]
    return ExecutionMatrix(
        name="cross-domain",
        mode=ExecutionMode.DIAGONAL,
        nodes=nodes,
        edges=[],
    )


class TestExecutionMatrixOpenRoles:
    def setup_method(self):
        self.matrix = _make_cross_domain_matrix()

    def test_get_nodes_at_role_string(self):
        quant_nodes = self.matrix.get_nodes_at_role("QUANT")
        assert len(quant_nodes) == 1
        assert quant_nodes[0].name == "quant-analysis"

    def test_get_nodes_at_role_finance(self):
        trader_nodes = self.matrix.get_nodes_at_role("TRADER")
        assert len(trader_nodes) == 1

    def test_get_nodes_at_role_empty(self):
        assert self.matrix.get_nodes_at_role("CLINICIAN") == []

    def test_roles_in_matrix(self):
        roles = self.matrix.roles_in_matrix()
        assert isinstance(roles, list)
        assert "QUANT" in roles
        assert "TRADER" in roles
        assert "OPS" in roles
        assert "RISK_MANAGER" in roles
        assert None not in roles

    def test_build_matrix_map(self):
        cell_map = self.matrix.build_matrix_map()
        assert len(cell_map) == 6   # 7 nodes - 1 uncoordinated
        addr = MatrixAddress(layer=CognitiveLayer.REASON, role="QUANT")
        assert addr in cell_map
        assert cell_map[addr].name == "quant-analysis"

    def test_matrix_coverage_summary_dynamic_possible(self):
        """cells_possible is now 7_layers × N_unique_roles, not 7×7."""
        summary = self.matrix.matrix_coverage_summary()
        n_roles = len(set(
            n.agent_role for n in self.matrix.nodes
            if n.agent_role
        ))
        expected_possible = len(CognitiveLayer) * n_roles
        assert summary["cells_possible"]  == expected_possible
        assert summary["coordinated_nodes"]  == 6
        assert summary["uncoordinated_nodes"] == 1

    def test_get_matrix_address_finance_role(self):
        node = next(n for n in self.matrix.nodes if n.name == "quant-analysis")
        addr = self.matrix.get_matrix_address(node.id)
        assert addr is not None
        assert addr.role == "QUANT"
        assert addr.layer == CognitiveLayer.REASON


# ─── Domain packs ─────────────────────────────────────────────────────────────

class TestDomainPacks:
    def test_tech_domain_registered(self):
        assert domain_registry.get("tech") is not None
        assert domain_registry.get("tech") is TechDomain

    def test_finance_domain_registered(self):
        assert domain_registry.get("finance") is not None

    def test_healthcare_domain_registered(self):
        assert domain_registry.get("healthcare") is not None

    def test_legal_domain_registered(self):
        assert domain_registry.get("legal") is not None

    def test_manufacturing_domain_registered(self):
        assert domain_registry.get("manufacturing") is not None

    def test_tech_domain_contains_ops(self):
        assert TechDomain.contains("OPS")
        assert TechDomain.contains("CODER")
        assert not TechDomain.contains("QUANT")

    def test_finance_domain_contains_quant(self):
        assert FinanceDomain.contains("QUANT")
        assert FinanceDomain.contains("RISK_MANAGER")
        assert not FinanceDomain.contains("CLINICIAN")

    def test_healthcare_domain_contains_clinician(self):
        assert HealthcareDomain.contains("CLINICIAN")
        assert not HealthcareDomain.contains("CODER")

    def test_legal_domain_contains_paralegal(self):
        assert LegalDomain.contains("PARALEGAL")
        assert LegalDomain.contains("PARTNER")

    def test_manufacturing_domain_contains_engineer(self):
        assert ManufacturingDomain.contains("ENGINEER")
        assert ManufacturingDomain.contains("QUALITY_INSPECTOR")

    def test_domain_pack_role_names(self):
        assert "QUANT" in FinanceDomain.role_names
        assert isinstance(FinanceDomain.role_names, frozenset)

    def test_domain_pack_to_dict(self):
        d = TechDomain.to_dict()
        assert d["name"] == "tech"
        assert "roles" in d
        assert isinstance(d["roles"], dict)
        assert "OPS" in d["roles"]

    def test_registry_resolve_role(self):
        desc = domain_registry.resolve_role("QUANT")
        assert desc is not None
        assert isinstance(desc, str)

    def test_registry_unknown_role_returns_none(self):
        assert domain_registry.resolve_role("XYZZY_NONEXISTENT") is None

    def test_registry_find_domain_for_role(self):
        assert domain_registry.find_domain_for_role("CLINICIAN") == "healthcare"
        assert domain_registry.find_domain_for_role("QUANT")     == "finance"
        assert domain_registry.find_domain_for_role("OPS")       == "tech"

    def test_custom_domain_registration(self):
        custom = DomainPack(
            name="logistics-test",
            description="Test logistics domain",
            roles={
                "DISPATCHER": "Route assignment and vehicle allocation",
                "TRACKER":    "Shipment monitoring and status updates",
            },
            tags=["logistics"],
        )
        reg = DomainRegistry()
        reg.register(custom)
        assert reg.get("logistics-test") is custom
        assert reg.get("logistics-test").contains("DISPATCHER")

    def test_finance_role_constants(self):
        assert FinanceRole.QUANT        == "QUANT"
        assert FinanceRole.RISK_MANAGER == "RISK_MANAGER"
        assert FinanceRole.TRADER       == "TRADER"
        assert isinstance(FinanceRole.ALL, frozenset)

    def test_healthcare_role_constants(self):
        assert HealthcareRole.CLINICIAN  == "CLINICIAN"
        assert HealthcareRole.PHARMACIST == "PHARMACIST"

    def test_legal_role_constants(self):
        assert LegalRole.PARALEGAL == "PARALEGAL"
        assert LegalRole.PARTNER   == "PARTNER"

    def test_manufacturing_role_constants(self):
        assert ManufacturingRole.ENGINEER          == "ENGINEER"
        assert ManufacturingRole.QUALITY_INSPECTOR == "QUALITY_INSPECTOR"


# ─── CognitiveModelRouter — still role-agnostic ───────────────────────────────

class TestCognitiveModelRouterOpenRoles:
    """
    The CognitiveModelRouter routes on CognitiveLayer only.
    It is completely domain-agnostic — the agent_role string is passed
    through to metadata for observability but never affects model selection.
    """
    CHEAP   = "claude-haiku-4-5-20251001"
    PREMIUM = "claude-opus-4-6"

    def router(self) -> CognitiveModelRouter:
        return CognitiveModelRouter(cheap_model=self.CHEAP, premium_model=self.PREMIUM)

    @pytest.mark.parametrize("role", ["OPS", "QUANT", "CLINICIAN", "PARALEGAL", "ENGINEER"])
    def test_inject_hint_works_with_any_role(self, role):
        """inject_hint works for all domain roles — model selection is layer-based."""
        router  = self.router()
        node    = Node(
            name="n", type=NodeType.TOOL, handler="echo",
            cognitive_layer=CognitiveLayer.REASON,
            agent_role=role,
        )
        context = ExecutionContext()
        router.inject_hint(node, context)

        # Model is determined by layer (REASON → premium), not role
        assert context.metadata["__model_hint__"] == self.PREMIUM
        assert context.metadata["__model_tier__"] == "premium"
        # Role is passed through for observability
        assert context.metadata["__agent_role__"] == role

    @pytest.mark.parametrize("role", ["OPS", "TRADER", "NURSE", "CLERK", "OPERATOR"])
    def test_cheap_layer_any_role(self, role):
        router  = self.router()
        node    = Node(
            name="n", type=NodeType.TOOL, handler="echo",
            cognitive_layer=CognitiveLayer.ACT,
            agent_role=role,
        )
        context = ExecutionContext()
        router.inject_hint(node, context)
        assert context.metadata["__model_hint__"] == self.CHEAP
        assert context.metadata["__model_tier__"] == "cheap"


# ─── Backward compatibility ───────────────────────────────────────────────────

class TestBackwardCompatibility:
    def test_v11_matrix_works_unchanged(self):
        """v1.1 matrices with AgentRole.X values still validate and run."""
        matrix = ExecutionMatrix(
            name="legacy-v11",
            mode=ExecutionMode.SEQUENTIAL,
            nodes=[
                Node(name="n1", type=NodeType.TOOL,  handler="echo",
                     cognitive_layer=CognitiveLayer.PERCEIVE, agent_role=AgentRole.OPS),
                Node(name="n2", type=NodeType.AGENT, handler="analyst_agent",
                     cognitive_layer=CognitiveLayer.REASON,  agent_role=AgentRole.ANALYST),
            ],
            edges=[{"from": "n1", "to": "n2"}],
        )
        assert len(matrix.nodes) == 2
        cell_map = matrix.build_matrix_map()
        assert len(cell_map) == 2
        addr = MatrixAddress(layer=CognitiveLayer.REASON, role="ANALYST")
        assert addr in cell_map

    def test_node_without_coords_works(self):
        node = Node(name="legacy", type=NodeType.TOOL, handler="echo")
        assert node.cognitive_layer is None
        assert node.agent_role      is None
        assert node.has_matrix_address is False

    def test_matrix_without_coords_works(self):
        matrix = ExecutionMatrix(
            name="no-coords",
            nodes=[Node(name="n", type=NodeType.TOOL, handler="echo")],
            edges=[],
        )
        assert matrix.build_matrix_map() == {}
        assert matrix.matrix_coverage_summary()["coordinated_nodes"] == 0
