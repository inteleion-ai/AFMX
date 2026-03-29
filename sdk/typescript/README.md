# @agentdyne9/afmx

> TypeScript SDK for [AFMX](https://github.com/inteleion-ai/AFMX) — Agent Flow Matrix Execution Engine

[![npm](https://img.shields.io/npm/v/@agentdyne9/afmx)](https://www.npmjs.com/package/@agentdyne9/afmx)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](../../LICENSE)

Type-safe client for the AFMX REST API. Works in Node.js 18+, browsers, and edge runtimes (Cloudflare Workers, Vercel Edge, Deno).

## Install

```bash
npm install @agentdyne9/afmx
# or
pnpm add @agentdyne9/afmx
# or
yarn add @agentdyne9/afmx
```

## Quick start

```typescript
import { AFMXClient, ExecutionMode, CognitiveLayer, NodeType, buildNode, buildEdge } from '@agentdyne9/afmx';

const client = new AFMXClient({ baseUrl: 'http://localhost:8100' });

// Build a DIAGONAL matrix — AFMX auto-routes cheap/premium models by layer
const result = await client.execute({
  matrix: {
    name: 'risk-analysis',
    mode: ExecutionMode.DIAGONAL,
    nodes: [
      buildNode({
        id: 'retrieve',
        name: 'retrieve-market-data',
        handler: 'data_retriever',
        layer: CognitiveLayer.RETRIEVE,  // → Haiku / gpt-4o-mini (cheap)
        role: 'QUANT',
      }),
      buildNode({
        id: 'analyse',
        name: 'analyse-risk',
        handler: 'risk_analyser',
        layer: CognitiveLayer.REASON,    // → Opus / gpt-4o (premium)
        role: 'RISK_MANAGER',
      }),
    ],
    edges: [buildEdge('retrieve', 'analyse')],
  },
  input: { ticker: 'AAPL', lookback_days: 30 },
});

console.log(result.status, result.duration_ms + 'ms');
console.log(result.node_results);
```

## API

### `new AFMXClient(config)`

```typescript
const client = new AFMXClient({
  baseUrl:    'http://localhost:8100',   // AFMX server URL
  apiKey:     'afmx_....',              // optional — if RBAC enabled
  timeoutMs:  30_000,                   // default: 30 s
});
```

### Execution

| Method | Description |
|--------|-------------|
| `execute(req)` | Execute synchronously, wait for result |
| `executeAsync(req)` | Fire-and-forget, returns `execution_id` |
| `pollUntilDone(id, opts?)` | Poll until terminal state |
| `getStatus(id)` | Poll once |
| `getResult(id)` | Full result with node outputs |
| `cancel(id)` | Cancel a running execution |
| `retry(id)` | Retry a failed execution |
| `resume(id)` | Resume from last checkpoint |

### Cognitive Matrix

```typescript
// Get the 2D heatmap for a completed execution:
// CognitiveLayer × AgentRole, with model tier + cost per cell
const view = await client.matrixView(executionId);

view.cells['REASON:RISK_MANAGER']
// → { status: 'SUCCESS', model_tier: 'premium', duration_ms: 847 }
```

### Domain packs

```typescript
const domains = await client.listDomains();
// → { count: 5, domains: [{ name: 'finance', roles: {...} }, ...] }

const finance = await client.getDomain('finance');
// → { name: 'finance', roles: { QUANT: '...', RISK_MANAGER: '...' } }
```

### Async with polling

```typescript
const { execution_id } = await client.executeAsync({ matrix, input });

// Poll every 500 ms, timeout after 5 minutes
const result = await client.pollUntilDone(execution_id, {
  intervalMs: 500,
  timeoutMs:  300_000,
});
```

## Types

All AFMX domain types are exported:

```typescript
import type {
  ExecutionMatrix,
  ExecutionResponse,
  Node,
  Edge,
  MatrixViewResponse,
  DomainPack,
} from '@agentdyne9/afmx';

import {
  CognitiveLayer,   // PERCEIVE | RETRIEVE | REASON | PLAN | ACT | EVALUATE | REPORT
  ExecutionMode,    // SEQUENTIAL | PARALLEL | HYBRID | DIAGONAL
  NodeType,         // TOOL | AGENT | FUNCTION | MCP
  ExecutionStatus,  // QUEUED | RUNNING | COMPLETED | FAILED | ABORTED | TIMEOUT | PARTIAL
  AFMXError,        // thrown on HTTP errors — has .status and .detail
} from '@agentdyne9/afmx';
```

## CognitiveLayer routing

AFMX automatically routes cheap models to high-frequency layers and premium models to reasoning layers:

| Layer | Typical use | Default model tier |
|-------|------------|-------------------|
| `PERCEIVE` | Ingest signals, alerts | Cheap (Haiku, gpt-4o-mini) |
| `RETRIEVE` | RAG, DB lookups | Cheap |
| `REASON` | Analysis, synthesis | **Premium** (Opus, gpt-4o) |
| `PLAN` | Strategy, runbooks | **Premium** |
| `ACT` | Execute tools, APIs | Cheap |
| `EVALUATE` | Validate, audit | **Premium** |
| `REPORT` | Summarise, alert | Cheap |

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
