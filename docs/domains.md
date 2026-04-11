# Domain Packs

AFMX v1.2 opened the COLUMN axis of the Cognitive Execution Matrix. The ROW axis
(`CognitiveLayer`) is fixed and universal. The COLUMN axis (`agent_role`) is now an
open string — any industry, any organisation, any team defines their own vocabulary.

Five built-in domain packs ship with the framework. Custom domains take 8 lines.

---

## The two axes

```
                      ROLES → COLUMN axis — open string, domain-specific
                      OPS    QUANT  CLINICIAN  PARALEGAL  ENGINEER
LAYERS  PERCEIVE       ■       □        □          □          □
(fixed) RETRIEVE       ■       ■        □          □          □
ROW     REASON         □       ■        ■          □          □
axis    PLAN           ■       □        ■          ■          □
        ACT            ■       ■        □          □          ■
        EVALUATE       □       ■        □          ■          □
        REPORT         ■       □        □          □          □
```

**ROW axis — `CognitiveLayer` (fixed, universal):**
Seven values: `PERCEIVE`, `RETRIEVE`, `REASON`, `PLAN`, `ACT`, `EVALUATE`, `REPORT`.
Never changes. Drives automatic model tier routing (cheap vs premium).

**COLUMN axis — `agent_role` (open string, domain-specific):**
Any `UPPER_SNAKE_CASE` string is valid. Built-in domain packs provide pre-defined
constants for the most common industries.

---

## Built-in domain packs

### Tech / SRE (default)

```python
from afmx.domains.tech import TechDomain, AgentRole

# Constants
AgentRole.OPS        == "OPS"
AgentRole.CODER      == "CODER"
AgentRole.ANALYST    == "ANALYST"
AgentRole.RESEARCHER == "RESEARCHER"
AgentRole.COMPLIANCE == "COMPLIANCE"
AgentRole.VERIFIER   == "VERIFIER"
AgentRole.PLANNER    == "PLANNER"
```

Use case: SRE incident response, CI/CD automation, platform engineering, code review.

```python
# v1.1 style (backward-compatible)
node = Node(agent_role=AgentRole.OPS, ...)

# v1.2+ style (preferred)
node = Node(agent_role="OPS", ...)
```

### Finance & Capital Markets

```python
from afmx.domains.finance import FinanceDomain, FinanceRole

FinanceRole.QUANT             == "QUANT"
FinanceRole.TRADER            == "TRADER"
FinanceRole.RISK_MANAGER      == "RISK_MANAGER"
FinanceRole.PORTFOLIO_MANAGER == "PORTFOLIO_MANAGER"
FinanceRole.COMPLIANCE_OFFICER == "COMPLIANCE_OFFICER"
FinanceRole.ANALYST           == "ANALYST"
FinanceRole.AUDITOR           == "AUDITOR"
```

Use case: quantitative research, risk scoring, trade compliance, portfolio management.

### Healthcare & Clinical

```python
from afmx.domains.healthcare import HealthcareDomain, HealthcareRole

HealthcareRole.CLINICIAN     == "CLINICIAN"
HealthcareRole.PHARMACIST    == "PHARMACIST"
HealthcareRole.RADIOLOGIST   == "RADIOLOGIST"
HealthcareRole.NURSE         == "NURSE"
HealthcareRole.ADMINISTRATOR == "ADMINISTRATOR"
HealthcareRole.RESEARCHER    == "RESEARCHER"
HealthcareRole.ASSESSOR      == "ASSESSOR"
```

Use case: clinical decision support, care coordination, medical image review, hospital operations.

### Legal & Compliance

```python
from afmx.domains.legal import LegalDomain, LegalRole

LegalRole.PARALEGAL      == "PARALEGAL"
LegalRole.ASSOCIATE      == "ASSOCIATE"
LegalRole.PARTNER        == "PARTNER"
LegalRole.EXPERT_WITNESS == "EXPERT_WITNESS"
LegalRole.CLERK          == "CLERK"
LegalRole.JUDGE          == "JUDGE"
LegalRole.NOTARY         == "NOTARY"
```

Use case: legal research, contract analysis, litigation support, regulatory compliance.

### Manufacturing & Industrial

```python
from afmx.domains.manufacturing import ManufacturingDomain, ManufacturingRole

ManufacturingRole.ENGINEER          == "ENGINEER"
ManufacturingRole.QUALITY_INSPECTOR == "QUALITY_INSPECTOR"
ManufacturingRole.MAINTENANCE_TECH  == "MAINTENANCE_TECH"
ManufacturingRole.SAFETY_OFFICER    == "SAFETY_OFFICER"
ManufacturingRole.PROCESS_MANAGER   == "PROCESS_MANAGER"
ManufacturingRole.OPERATOR          == "OPERATOR"
ManufacturingRole.SUPPLY_PLANNER    == "SUPPLY_PLANNER"
```

Use case: predictive maintenance, quality control, HSE compliance, supply chain optimisation.

---

## Using domain packs in a matrix

```python
from afmx import ExecutionMatrix, ExecutionMode, Node, NodeType, CognitiveLayer
from afmx.domains.finance import FinanceRole

risk_pipeline = ExecutionMatrix(
    name="risk-pipeline",
    mode=ExecutionMode.DIAGONAL,
    nodes=[
        Node(
            id="retrieve",
            name="fetch-market-data",
            type=NodeType.AGENT,
            handler="data_retriever",
            cognitive_layer=CognitiveLayer.RETRIEVE,  # → cheap model
            agent_role=FinanceRole.QUANT,
        ),
        Node(
            id="analyse",
            name="risk-scoring",
            type=NodeType.AGENT,
            handler="risk_model",
            cognitive_layer=CognitiveLayer.REASON,    # → premium model
            agent_role=FinanceRole.RISK_MANAGER,
        ),
        Node(
            id="report",
            name="risk-report",
            type=NodeType.AGENT,
            handler="reporter",
            cognitive_layer=CognitiveLayer.REPORT,    # → cheap model
            agent_role=FinanceRole.ANALYST,
        ),
    ],
    edges=[
        {"from": "retrieve", "to": "analyse"},
        {"from": "analyse",  "to": "report"},
    ],
)
```

---

## Cross-domain matrices

Different roles from different domains can coexist in one matrix:

```python
# A compliance workflow mixing tech OPS with legal PARALEGAL
matrix = ExecutionMatrix(
    name="compliance-review",
    nodes=[
        Node(cognitive_layer="PERCEIVE",  agent_role="OPS",       ...),  # tech
        Node(cognitive_layer="RETRIEVE",  agent_role="PARALEGAL",  ...),  # legal
        Node(cognitive_layer="REASON",    agent_role="ASSOCIATE",  ...),  # legal
        Node(cognitive_layer="EVALUATE",  agent_role="COMPLIANCE", ...),  # tech
        Node(cognitive_layer="REPORT",    agent_role="PARTNER",    ...),  # legal
    ],
    ...
)
```

`MatrixAddress` strings are unique regardless of origin domain:
`"REASON×PARALEGAL"`, `"EVALUATE×COMPLIANCE"`, etc.

---

## Custom domains

Define a custom domain pack in 8 lines:

```python
from afmx.domains import DomainPack, domain_registry

logistics = DomainPack(
    name="logistics",
    description="Logistics and supply chain agent roles",
    roles={
        "DISPATCHER":  "Route assignment and vehicle allocation",
        "TRACKER":     "Shipment monitoring and status updates",
        "ANALYST":     "Demand forecasting and optimisation",
        "COORDINATOR": "Cross-carrier and customs coordination",
    },
    tags=["logistics", "supply-chain", "transport"],
)
domain_registry.register(logistics)

# Now use it anywhere:
node = Node(agent_role="DISPATCHER", ...)
```

---

## Domain Registry

The global `domain_registry` is the single source of truth for all registered packs.

```python
from afmx.domains import domain_registry

# List all packs
for pack in domain_registry.list_all():
    print(pack["name"], pack["role_count"])

# Look up a role across all packs
desc = domain_registry.resolve_role("QUANT")
# → "Quantitative model research, factor development, backtesting"

# Find which domain owns a role
domain = domain_registry.find_domain_for_role("CLINICIAN")
# → "healthcare"

# Get a specific pack
finance = domain_registry.get("finance")
finance.contains("QUANT")   # True
finance.contains("OPS")     # False
```

---

## REST API

Domain packs are exposed via the REST API (v1.2+):

```bash
# List all registered domain packs
GET /afmx/domains
→ {"count": 5, "domains": [{"name": "finance", "role_count": 7, ...}, ...]}

# Get a specific domain pack
GET /afmx/domains/finance
→ {"name": "finance", "description": "...", "roles": {"QUANT": "...", ...}, "tags": [...]}
```

---

## Role string validation

All `agent_role` strings must match: `[A-Z][A-Z0-9_]{0,63}`

Valid: `"OPS"`, `"RISK_MANAGER"`, `"EXPERT_WITNESS"`, `"QUALITY_INSPECTOR2"`

Invalid: `"ops"` (lowercase), `"risk-manager"` (hyphen), `"RISK MANAGER"` (space)

```python
# These raise ValidationError:
Node(agent_role="ops", ...)         # lowercase
Node(agent_role="risk-manager", ...) # hyphen
Node(agent_role="", ...)             # empty

# These are fine:
Node(agent_role=None, ...)           # no role (backward compat)
Node(agent_role="OPS", ...)
Node(agent_role="QUALITY_INSPECTOR_2", ...)
```

---

## Backward compatibility

All v1.1 code using `AgentRole` as an enum continues to work unchanged:

```python
# v1.1 — still works in v1.2+
from afmx.models.node import AgentRole   # re-exported from afmx.domains.tech
node = Node(agent_role=AgentRole.OPS, ...)   # AgentRole.OPS == "OPS"
addr = MatrixAddress(layer=CognitiveLayer.ACT, role=AgentRole.OPS)
assert str(addr) == "ACT×OPS"
```

`AgentRole` is no longer an enum — it is a plain namespace class where each constant
equals its string value. This makes it fully compatible with the open string field
without requiring any code changes.
