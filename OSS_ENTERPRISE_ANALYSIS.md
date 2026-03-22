# AFMX — OSS vs Enterprise License Analysis
## Based on full codebase audit — March 21, 2026

**Method:** Read every module, every class, every function. No assumptions.
**License recommendation:** Apache 2.0 for OSS, proprietary for enterprise.
**Principle:** OSS what makes you credible and adopted. Enterprise what companies genuinely cannot build themselves and will pay for.

---

## The Honest Summary Up Front

After reading the entire codebase, the conclusion is uncomfortable but important:

**Almost everything that currently exists should be Apache 2.0 OSS.**

The existing code — engine, RBAC, audit, Redis stores, webhooks, middleware, adapters, dashboard — is all straightforwardly good infrastructure code. None of it is so uniquely differentiated that keeping it proprietary would generate revenue. What it would do is destroy adoption. The enterprise tier needs to be built on features that **do not exist yet** and that enterprises genuinely cannot build themselves.

The companies that tried to keep their execution engine proprietary while competitors were OSS (early LangChain competitors, early Airflow competitors) all lost. The companies that OSS'd the engine and monetised cloud + compliance + support won.

---

## File-by-File Verdict — What Is Currently in the Codebase

### ✅ Apache 2.0 — Core Engine (non-negotiable)

These are the reason anyone uses AFMX. Making any of them proprietary is not a business strategy — it is an adoption strategy failure.

| File | What it does | Why OSS |
|---|---|---|
| `afmx/core/engine.py` | AFMXEngine — SEQUENTIAL/PARALLEL/HYBRID orchestration | The entire value proposition. Must be OSS or the product does not exist. |
| `afmx/core/executor.py` | NodeExecutor + HandlerRegistry | Executes individual nodes. Without this, there is no AFMX. |
| `afmx/core/retry.py` | RetryManager + CircuitBreaker | Per-node retry + CB state machine. This is the main differentiator vs LangGraph. Must be OSS to demonstrate the claim. |
| `afmx/core/router.py` | ToolRouter — deterministic rule-based routing | Must be OSS — it is the determinism claim made concrete. |
| `afmx/core/dispatcher.py` | AgentDispatcher — complexity/capability routing | Must be OSS — demonstrates multi-agent coordination claim. |
| `afmx/core/hooks.py` | HookRegistry — PRE/POST hooks | Middleware extensibility. Must be OSS for integrations to work. |
| `afmx/core/concurrency.py` | ConcurrencyManager — semaphore + stats | Required for any production use. OSS. |
| `afmx/core/variable_resolver.py` | `{{template}}` param resolution | Developer DX feature. OSS. |

### ✅ Apache 2.0 — Models (non-negotiable)

| File | What it does |
|---|---|
| `afmx/models/node.py` | Node, NodeResult, RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy |
| `afmx/models/edge.py` | Edge, EdgeCondition, 5 condition types |
| `afmx/models/matrix.py` | ExecutionMatrix, topological sort, batch grouping |
| `afmx/models/execution.py` | ExecutionContext, ExecutionRecord, ExecutionStatus |

Models are never proprietary. They are the protocol. Keeping models proprietary makes integrations impossible.

### ✅ Apache 2.0 — Stores (both InMemory AND Redis backends)

This is a key decision. Some companies keep Redis backends enterprise-only. That is a mistake for AFMX.

**Why Redis stores must be OSS:**
The in-memory store is development-only. If Redis is enterprise, you are saying "you cannot run AFMX in production without paying." That kills every self-hosted enterprise evaluation. The Redis backend is standard asyncio redis client code — there is no secret sauce in it. Any developer could write it in a day. Making it proprietary just forces people to find alternatives.

| File | Both backends OSS? |
|---|---|
| `afmx/store/state_store.py` | ✅ Yes — InMemoryStateStore + RedisStateStore both OSS |
| `afmx/store/matrix_store.py` | ✅ Yes — both backends OSS |
| `afmx/store/checkpoint.py` | ✅ Yes — both backends OSS |

### ✅ Apache 2.0 — Observability

| File | Verdict | Reason |
|---|---|---|
| `afmx/observability/events.py` | ✅ OSS | EventBus is infrastructure. Required for everything to work. |
| `afmx/observability/metrics.py` | ✅ OSS | Prometheus is OSS. Our metrics wrapper should be too. |
| `afmx/observability/webhook.py` | ✅ OSS | Basic HTTP webhook is not a proprietary feature. Competitors include it OSS. |

### ✅ Apache 2.0 — REST API

| File | Verdict | Reason |
|---|---|---|
| `afmx/api/routes.py` | ✅ OSS | Core execution endpoints. Without this, AFMX has no HTTP surface. |
| `afmx/api/websocket.py` | ✅ OSS | WebSocket streaming. Required for dashboard and live monitoring. |
| `afmx/api/schemas.py` | ✅ OSS | Request/response models. Must be OSS for TypeScript SDK codegen. |
| `afmx/api/adapter_routes.py` | ✅ OSS | Adapter inspection. OSS. |
| `afmx/api/matrix_routes.py` | ✅ OSS | Named matrix CRUD + execute-by-name. Core usability feature. |
| `afmx/api/admin_routes.py` | ✅ OSS | Key management endpoints. Goes with RBAC. |
| `afmx/api/audit_routes.py` | ✅ OSS | Audit log query + export. Goes with audit system. |

### ✅ Apache 2.0 — Auth + RBAC

This is the most debated item. The RBAC system is production-quality:
- 5 roles: VIEWER / SERVICE / DEVELOPER / OPERATOR / ADMIN
- 16 permissions across 6 resource types
- Per-key permission overrides
- `tenant_id` field on every API key
- InMemory + Redis key stores
- Bootstrap ADMIN key generation
- `Principal` injection into `request.state`

**Verdict: OSS.**

**Reasoning:** The alternative — making RBAC enterprise — means OSS users cannot secure their AFMX deployment without paying. That is not a sustainable position in 2026. Every competitor (LangGraph, Prefect, even Temporal's OSS version) includes basic auth and RBAC. The enterprise RBAC features are the ones that don't exist yet: SSO/OIDC, SCIM provisioning, LDAP integration, and **multi-tenancy data isolation** (tenant_id exists on keys but queries are not yet tenant-scoped).

| File | Verdict | Notes |
|---|---|---|
| `afmx/auth/rbac.py` | ✅ OSS | Role definitions, permission map, APIKey model |
| `afmx/auth/store.py` | ✅ OSS | InMemory + Redis key stores |
| `afmx/middleware/rbac.py` | ✅ OSS | Enforcement middleware |
| `afmx/middleware/auth.py` | ✅ OSS | Simple legacy key middleware |
| `afmx/middleware/rate_limit.py` | ✅ OSS | Token-bucket rate limiter |
| `afmx/middleware/logging.py` | ✅ OSS | Request logging |

### ✅ Apache 2.0 — Audit System

| File | Verdict | Notes |
|---|---|---|
| `afmx/audit/model.py` | ✅ OSS | AuditEvent + AuditAction enum. 25+ action types. |
| `afmx/audit/store.py` | ✅ OSS | InMemory + Redis audit stores, JSON/CSV/NDJSON export. |

**Reasoning:** The audit system in its current form is a good audit log. It is not a compliance system. The enterprise features are what come next: cryptographic signing of each AuditEvent, tamper-evident hash chain, SOC2 report generation, 1-year guaranteed retention with S3 archival, SIEM integration (Splunk, DataDog, Elastic). Those features don't exist yet. The current AuditStore is OSS; the compliance system is enterprise.

### ✅ Apache 2.0 — Adapters

| File | Verdict |
|---|---|
| `afmx/adapters/base.py` | ✅ OSS |
| `afmx/adapters/langchain.py` | ✅ OSS |
| `afmx/adapters/langgraph.py` | ✅ OSS |
| `afmx/adapters/crewai.py` | ✅ OSS |
| `afmx/adapters/openai.py` | ✅ OSS |
| `afmx/adapters/registry.py` | ✅ OSS |

Adapters must be OSS. They are the connective tissue to the rest of the ecosystem. Making them proprietary would make AFMX irrelevant in two quarters as every framework builds native fault tolerance.

### ✅ Apache 2.0 — Everything Else

| File/Dir | Verdict |
|---|---|
| `afmx/__init__.py` | ✅ OSS — public SDK surface |
| `afmx/config.py` | ✅ OSS — environment settings |
| `afmx/main.py` | ✅ OSS — FastAPI app factory |
| `afmx/cli.py` | ✅ OSS — CLI |
| `afmx/plugins/` | ✅ OSS — plugin registry + decorators |
| `afmx/utils/` | ✅ OSS — exceptions, helpers |
| `afmx/startup_handlers.py` | ✅ OSS — built-in handlers |
| `afmx/integrations/agentability_hook.py` | ✅ OSS — drives Agentability adoption |
| `afmx/dashboard/` | ✅ OSS — drives product adoption (see Grafana model) |
| `realistic_handlers.py` | ✅ OSS — example/demo code |
| `demo_multiagent.py` | ✅ OSS — demo code |
| `demo_agentability.py` | ✅ OSS — demo code |
| `tests/` | ✅ OSS — test suite |
| `examples/` | ✅ OSS — runnable examples |
| `docs/` | ✅ OSS — documentation |

---

## What the Enterprise Tier Actually Is

The enterprise tier is not about withholding existing code. It is about building features that enterprises pay for and that individual developers genuinely do not need.

### Enterprise Feature 1 — Multi-Tenancy Data Isolation (v1.3)

**Does not exist yet.** The `tenant_id` field is on `APIKey` and in `AuditEvent`, but `StateStore`, `MatrixStore`, and `AuditStore` queries are not tenant-scoped. Tenant A can call `GET /afmx/executions` and see Tenant B's data.

Real multi-tenancy means:
- Every store query is prefixed by `tenant_id` from the authenticated key
- ADMIN can cross-tenant query with explicit `?tenant_id=` param
- Data cannot leak between tenants even on shared infrastructure
- Tenant-level billing and usage reporting

This is an enterprise feature. Single teams do not need it.

### Enterprise Feature 2 — SSO / OIDC / SAML (v2.0)

Not built. Enterprises with 50+ engineers cannot manage individual API keys. They need:
- OIDC integration (Google Workspace, Okta, Azure AD)
- SAML 2.0 for legacy enterprise identity providers
- SCIM provisioning to sync users and groups automatically
- Session-based auth in addition to key-based auth

Individual developers and small teams are fine with API keys.

### Enterprise Feature 3 — Cryptographic Execution Integrity (v1.5)

Not built. The website claims "execution integrity verification" — what exists is a good audit log. The enterprise feature is:
- SHA-256 hash chain over every `ExecutionRecord`
- HMAC-SHA256 signature on every `AuditEvent` using a server-side signing key
- `POST /afmx/verify/{execution_id}` — cryptographic proof of record integrity
- SOC2 Type II attestation support
- Legal-grade tamper evidence

Developers using AFMX for internal tooling do not need this. Fintech, healthcare, and legal companies do.

### Enterprise Feature 4 — Distributed Worker Pool (v1.4)

Not built. Single-server AFMX handles 500 concurrent executions well. At enterprise scale (10,000+ executions/day, multi-region, high-availability), you need:
- Worker process architecture with Redis task queue
- Worker auto-scaling (Kubernetes HPA integration)
- Cross-region execution routing
- Worker health monitoring + automatic failover

Developers and startups are fine with a single server. Large enterprises need distributed execution.

### Enterprise Feature 5 — Scheduled Execution with Leader Election (v1.3)

Not built at the level enterprises need. The scheduled execution feature itself will be OSS (basic cron). The enterprise features on top are:
- Multi-timezone schedule management UI
- Webhook trigger ingestion at scale
- Leader election for distributed deployments (Redis lock)
- Schedule history with SLA tracking
- Pause/resume across deployments

### Enterprise Feature 6 — Cost Governance (v1.4)

Not built. The `_llm_meta` pattern exists in `realistic_handlers.py` but there is no enforcement layer. Enterprise cost governance means:
- Per-matrix and per-tenant token + dollar budgets
- Budget breach alerts with configurable actions (WARN/ABORT)
- Cost attribution reports by team, matrix, model, and time period
- Integration with cloud provider billing (AWS Cost Explorer, GCP Billing)
- Chargeback reporting for internal billing

### Enterprise Feature 7 — SIEM Integration

Not built. Enterprise compliance teams require audit events in:
- Splunk HEC (HTTP Event Collector)
- Elastic SIEM
- DataDog Logs
- AWS Security Hub
- Microsoft Sentinel

### Enterprise Feature 8 — AFMX Cloud (v2.0)

No self-hosted user can access this. Managed AFMX with:
- Zero infrastructure to run
- Multi-region (US, EU, AP)
- Automatic scaling
- Built-in Agentability observability
- Usage-based billing
- 99.9% SLA with financial credit

### Enterprise Feature 9 — Enterprise Support

Not a software feature. Enterprises pay for:
- Dedicated Slack channel with < 4hr response SLA
- Security advisory notifications before public disclosure
- Architecture review sessions (quarterly)
- Custom training for engineering teams
- Signed BAA (Business Associate Agreement) for HIPAA

---

## What to NOT Make Enterprise

Two things that might seem like enterprise features but should stay OSS:

**1. Redis backends.** If Redis is enterprise-only, self-hosted production deployments are impossible without paying. This will destroy adoption from developers who evaluate and then advocate to their companies. Redis backends are OSS.

**2. The dashboard.** It might seem like a premium UI deserves a price tag. It does not. The dashboard drives adoption the same way Grafana's OSS UI drives Grafana's enterprise business. OSS dashboard → more users → more enterprise sales. Proprietary dashboard → fewer evaluations → fewer enterprise leads.

---

## The Licensing Architecture

```
┌─────────────────────────────────────────────────────────┐
│            AFMX Cloud (Proprietary SaaS)                │
│     Managed hosting · SLA · Multi-region · Billing      │
├─────────────────────────────────────────────────────────┤
│           AFMX Enterprise (Proprietary)                 │
│  Multi-tenancy · SSO/OIDC · Cryptographic integrity     │
│  Distributed workers · Cost governance · SIEM           │
│  SOC2 tooling · Priority support · Custom SLA           │
├─────────────────────────────────────────────────────────┤
│              AFMX Open Source (Apache 2.0)              │
│                                                         │
│  Core engine · Models · Adapters · Plugins              │
│  RBAC · Audit · Redis stores · Webhooks                 │
│  REST API · WebSocket · Dashboard · CLI                 │
│  Agentability integration · Prometheus metrics          │
│  All 4 framework adapters · All built-in handlers       │
└─────────────────────────────────────────────────────────┘
```

---

## OSS vs Enterprise — Decision Table

| Component | Exists Today | License | Enterprise Equivalent |
|---|---|---|---|
| Core engine (SEQUENTIAL/PARALLEL/HYBRID) | ✅ | Apache 2.0 | — |
| RetryManager + CircuitBreaker | ✅ | Apache 2.0 | — |
| ToolRouter + AgentDispatcher | ✅ | Apache 2.0 | — |
| HookRegistry | ✅ | Apache 2.0 | — |
| ConcurrencyManager | ✅ | Apache 2.0 | — |
| All models (Node, Edge, Matrix, Context, Record) | ✅ | Apache 2.0 | — |
| InMemory + Redis stores (all 3 stores) | ✅ | Apache 2.0 | — |
| LangChain / LangGraph / CrewAI / OpenAI adapters | ✅ | Apache 2.0 | MCP, OpenAI Agents SDK (future) |
| Basic RBAC (5 roles, 16 permissions, API keys) | ✅ | Apache 2.0 | SSO/OIDC, SCIM, multi-tenancy |
| Audit log (InMemory + Redis, export) | ✅ | Apache 2.0 | Signed audit, SOC2 tooling, SIEM |
| Webhook notifier (HMAC-signed) | ✅ | Apache 2.0 | — |
| Rate limiting | ✅ | Apache 2.0 | — |
| REST API (all current endpoints) | ✅ | Apache 2.0 | — |
| WebSocket streaming | ✅ | Apache 2.0 | — |
| React SPA dashboard | ✅ | Apache 2.0 | — |
| Prometheus metrics | ✅ | Apache 2.0 | — |
| Agentability integration hook | ✅ | Apache 2.0 | — |
| CLI | ✅ | Apache 2.0 | — |
| **Multi-tenancy data isolation** | ❌ Not built | **Enterprise** | v1.3 |
| **SSO / OIDC / SAML** | ❌ Not built | **Enterprise** | v2.0 |
| **SCIM provisioning** | ❌ Not built | **Enterprise** | v2.0 |
| **Cryptographic execution integrity** | ❌ Not built | **Enterprise** | v1.5 |
| **Signed tamper-evident audit chain** | ❌ Not built | **Enterprise** | v1.5 |
| **SOC2 audit report generation** | ❌ Not built | **Enterprise** | v1.5 |
| **SIEM connectors** | ❌ Not built | **Enterprise** | v2.0 |
| **Distributed worker pool** | ❌ Not built | **Enterprise** | v1.4 |
| **Scheduled execution (cron/webhook/event)** | ❌ Not built | **Hybrid** (cron=OSS, advanced=Enterprise) | v1.3 |
| **Cost governance + budgets** | ❌ Not built | **Enterprise** | v1.4 |
| **Per-tenant billing + usage reports** | ❌ Not built | **Enterprise** | v2.0 |
| **AFMX Cloud (managed hosting)** | ❌ Not built | **Enterprise SaaS** | v2.0 |
| **Enterprise SLA + dedicated support** | ❌ Not available | **Enterprise** | Now |

---

## What to Put in the Apache 2.0 LICENSE File

```
Apache License
Version 2.0, January 2004

Copyright 2026 Agentdyne9

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

NOTICE: Enterprise features (multi-tenancy isolation, SSO/OIDC, 
cryptographic execution integrity, distributed workers, cost governance,
and AFMX Cloud) are available under a separate commercial license.
Contact: enterprise@agentdyne9.com
```

The current MIT LICENSE file should be replaced with Apache 2.0. Apache 2.0 is more appropriate than MIT for infrastructure software because it includes an explicit patent grant — which matters when you start dealing with enterprise procurement teams who ask about IP indemnification.

---

## Why Apache 2.0 and Not MIT or BSL

**MIT:** Too permissive. A competitor could take the entire AFMX codebase, brand it, and sell it as a managed service without contributing back or acknowledging the origin. AWS did this to Elasticsearch (hence the BSL pivot).

**Business Source License (BSL / BUSL):** Popular post-Elasticsearch. Allows free use for most purposes but restricts commercial hosting. The problem is it creates friction: lawyers at large companies have to review it, some companies refuse BSL on policy. It also signals distrust of the community. Temporal, Prefect, and HashiCorp have all gone BSL and faced community backlash.

**Apache 2.0:** The gold standard for infrastructure software. Used by Kubernetes, Kafka, Airflow, Spark, Ray, and essentially every major infrastructure project that won. Includes explicit patent grant (critical for enterprise procurement). Requires attribution. Does not restrict commercial use. Enterprise sales are not threatened by OSS users when the enterprise features are genuinely differentiated.

The business model is: OSS drives adoption → adoption creates enterprise leads → enterprise features (not withheld OSS) close deals.

---

## The Three Actions to Take This Week

**1. Replace LICENSE with Apache 2.0.** The current MIT license is fine but Apache 2.0 is strategically better for enterprise sales. Do it before the public repo launch.

**2. Publish to PyPI under Apache 2.0.** Tag v1.0.1. Run `python -m build && twine upload`. This is the single most impactful action — it makes `pip install afmx` work globally.

**3. Create `ENTERPRISE.md` in the repo root.** Describe the enterprise features that are coming (multi-tenancy, SSO, integrity verification, cloud hosting). Give a contact email. This converts OSS evaluators into enterprise leads without any sales call needed.

Every day the repo stays private and unpublished on PyPI is a day of lost adoption that cannot be recovered.
