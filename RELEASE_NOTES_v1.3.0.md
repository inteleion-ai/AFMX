# AFMX v1.3.0 — Enterprise Adapters + Platform Integrations

> Released: March 31, 2026

AFMX v1.3.0 is the largest adapter release to date — connecting AFMX's
execution fabric to every major enterprise AI platform and the Agentdyne9
product ecosystem.

All changes are **fully backward-compatible** with v1.2.x.

---

## What's new

### Enterprise framework adapters

Three new adapters bring AFMX to the dominant enterprise AI SDKs in March 2026.
All use lazy imports — AFMX starts without any of these installed.

**Microsoft Semantic Kernel** (`pip install afmx[semantic-kernel]`)

```python
from afmx.adapters.semantic_kernel import SemanticKernelAdapter

adapter = SemanticKernelAdapter(kernel=kernel)
node    = adapter.function_node(fn, node_name="summarise", cognitive_layer="REASON")
nodes   = adapter.plugin_nodes("WebSearch", agent_role="OPS")
```

`CognitiveLayer` is inferred automatically from function name and description.
Every SK plugin function becomes an AFMX node with retry, circuit breaker, and audit.

**Google Agent Development Kit** (`pip install afmx[google-adk]`)

```python
from afmx.adapters.google_adk import GoogleADKAdapter

adapter    = GoogleADKAdapter()
tool_node  = adapter.tool_node(google_search)       # → RETRIEVE (auto)
agent_node = adapter.agent_node(researcher)         # → REASON (auto)
plan_node  = adapter.agent_node(SequentialAgent())  # → PLAN (auto)
```

Google ADK launched in March 2026. AFMX is among the first frameworks to
provide a production wrapper — full `Runner` session execution included.

**Amazon Bedrock** (`pip install afmx[bedrock]`)

```python
from afmx.adapters.bedrock import BedrockAdapter

adapter     = BedrockAdapter(region_name="us-east-1")
haiku_node  = adapter.model_node("anthropic.claude-3-haiku-20240307-v1:0")  # → RETRIEVE
sonnet_node = adapter.model_node("anthropic.claude-3-5-sonnet-20241022-v2:0")  # → REASON
agent_node  = adapter.agent_node("AGENT_ID_HERE", "TSTALIASID")
```

Supports all Bedrock providers with provider-specific request/response handling:
Claude (Messages API), Meta Llama, Amazon Titan, Mistral, Cohere.

---

### Platform integrations

Three first-party integrations connect AFMX to the Agentdyne9 product ecosystem.

**HyperState — Cognitive Memory** (`pip install afmx[hyperstate]`)

RETRIEVE-layer nodes automatically query HyperState for relevant memories.
REASON/PLAN/EVALUATE outputs are persisted back for future runs.

```python
from afmx.integrations.hyperstate import attach_hyperstate

attach_hyperstate(
    api_url="http://localhost:8000",
    api_key="hs_...",
    hook_registry=afmx_app.hook_registry,
    inject_into_memory=True,
    persist_agent_outputs=True,
)
```

**MAP — Verified Context** (`pip install afmx[map]`)

Every RETRIEVE node receives SHA-256 verified, provenanced context from MAP
before execution. Conflicts are caught before the LLM call.

```python
from afmx.integrations.map_plugin import attach_map
await attach_map(service=map_svc, hook_registry=afmx_app.hook_registry)
# handler="map:retrieve" and handler="map:verify" available everywhere
```

**RHFL — Human Governance Gate** (no extra install needed)

Every ACT-layer node requires human approval before execution.
AUTO → proceed · REVIEW → poll · BLOCK → `RHFLBlockedError` · ESCALATE → escalate

```python
from afmx.integrations.rhfl import attach_rhfl

attach_rhfl(
    api_url="http://rhfl.internal:4000/api/v1",
    token=os.getenv("RHFL_TOKEN"),
    hook_registry=afmx_app.hook_registry,
    gate_act_nodes=True,
    max_wait=300.0,
)
```

---

### TypeScript SDK — `@agentdyne9/afmx`

First npm release. Zero dependencies. Works in Node.js 18+, browser, and edge runtimes.

```bash
npm install @agentdyne9/afmx
```

```typescript
import { AFMXClient, ExecutionMode, CognitiveLayer, buildNode, buildEdge } from "@agentdyne9/afmx";

const client = new AFMXClient({ baseUrl: "http://localhost:8100" });

const result = await client.execute({
  matrix: {
    name: "risk-analysis",
    mode: ExecutionMode.DIAGONAL,
    nodes: [
      buildNode({ id: "retrieve", name: "fetch-data",   handler: "retriever",   layer: CognitiveLayer.RETRIEVE, role: "QUANT" }),
      buildNode({ id: "analyse",  name: "analyse-risk", handler: "risk_model",  layer: CognitiveLayer.REASON,   role: "RISK_MANAGER" }),
    ],
    edges: [buildEdge("retrieve", "analyse")],
  },
  input: { ticker: "AAPL" },
});

// Async + poll
const { execution_id } = await client.executeAsync({ matrix, input });
const final = await client.pollUntilDone(execution_id);

// Cognitive Matrix heatmap
const view = await client.matrixView(execution_id);
view.cells["REASON:RISK_MANAGER"]  // → { status, model_tier, duration_ms }
```

Full API: `execute` · `executeAsync` · `pollUntilDone` · `getStatus` · `getResult`
· `cancel` · `retry` · `resume` · `matrixView` · `listDomains` · `getDomain` · `validate`

---

## Full changelog

See [CHANGELOG.md](https://github.com/inteleion-ai/AFMX/blob/main/CHANGELOG.md) for the complete diff-level changelog including all file changes.

## Install

```bash
# Python
pip install afmx==1.3.0

# With adapters
pip install "afmx[mcp,semantic-kernel,google-adk,bedrock]==1.3.0"

# TypeScript
npm install @agentdyne9/afmx@1.3.0
```

## Upgrading from v1.2.x

No breaking changes. Drop-in upgrade:

```bash
pip install --upgrade afmx
```

All existing matrices, handlers, and API calls are unaffected.
`AgentRole.OPS` still works. Domain packs are additive.

---

**Full diff:** https://github.com/inteleion-ai/AFMX/compare/v1.2.1...v1.3.0
