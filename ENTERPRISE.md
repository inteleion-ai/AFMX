# AFMX Enterprise

The AFMX OSS core (Apache 2.0) includes the full execution engine, RBAC,
audit trail, Redis stores, all adapters, dashboard, and observability.
Everything you need to run AFMX in production is open-source.

Enterprise adds features that large organisations require for compliance,
governance, and scale.

---

## Enterprise Features

| Feature | Status | Description |
|---|---|---|
| **Multi-tenancy data isolation** | Roadmap v1.4 | One deployment, many teams — zero data leakage between tenants |
| **SSO / OIDC / SAML** | Roadmap v2.0 | Okta, Azure AD, Google Workspace, SAML 2.0, SCIM provisioning |
| **Cryptographic execution integrity** | Roadmap v1.5 | SHA-256 hash chain + HMAC-signed audit entries — tamper-evident |
| **SOC2 audit tooling** | Roadmap v1.5 | Pre-formatted SOC2 reports, 1-year retention, S3 archival |
| **SIEM integration** | Roadmap v2.0 | Splunk, Elastic, DataDog, AWS Security Hub connectors |
| **Distributed worker pool** | Roadmap v1.4 | Redis task queue + worker processes for horizontal scaling |
| **Cost governance** | Roadmap v1.4 | Per-matrix and per-tenant token + dollar budgets with enforcement |
| **AFMX Cloud** | Roadmap v2.0 | Managed hosting, multi-region, automatic scaling, zero infrastructure |
| **Enterprise SLA + support** | Available now | Dedicated support channel, architecture reviews, security advisories |

---

## What ships in the OSS core (v1.3.0)

- Full execution engine: SEQUENTIAL · PARALLEL · HYBRID · DIAGONAL modes
- CognitiveModelRouter: automatic cheap/premium model routing
- All 8 adapters: MCP, LangChain, LangGraph, CrewAI, OpenAI, Semantic Kernel, Google ADK, Bedrock
- All 4 platform integrations: HyperState, MAP, RHFL, Agentability
- 5 domain packs: tech, finance, healthcare, legal, manufacturing
- RBAC: 5 roles × 16 permissions, API key management
- Audit log: append-only, JSON/CSV/NDJSON export
- Redis-backed stores: state, matrix, checkpoint
- React dashboard, Prometheus metrics, WebSocket streaming
- TypeScript SDK: `@agentdyne9/afmx`
- Full REST API + CLI

---

## Contact

**Enterprise enquiries:** enterprise@agentdyne9.com
**General:** hello@agentdyne9.com

We respond to all enterprise enquiries within 24 hours.
