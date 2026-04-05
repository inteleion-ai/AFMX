// Copyright 2026 Agentdyne9
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @agentdyne9/afmx — TypeScript SDK for AFMX
 *
 * Type-safe client for the AFMX REST API.
 * Works in Node.js 18+, browser (with fetch), and edge runtimes.
 *
 * @example
 * ```typescript
 * import { AFMXClient, ExecutionMode, CognitiveLayer } from '@agentdyne9/afmx';
 *
 * const client = new AFMXClient({ baseUrl: 'http://localhost:8100' });
 *
 * const result = await client.execute({
 *   matrix: {
 *     name: 'risk-analysis',
 *     mode: ExecutionMode.DIAGONAL,
 *     nodes: [
 *       {
 *         id: 'retrieve',
 *         name: 'retrieve-data',
 *         type: 'AGENT',
 *         handler: 'data_retriever',
 *         cognitive_layer: CognitiveLayer.RETRIEVE,
 *         agent_role: 'QUANT',
 *       },
 *       {
 *         id: 'analyse',
 *         name: 'analyse-risk',
 *         type: 'AGENT',
 *         handler: 'risk_analyser',
 *         cognitive_layer: CognitiveLayer.REASON,
 *         agent_role: 'RISK_MANAGER',
 *       },
 *     ],
 *     edges: [{ from: 'retrieve', to: 'analyse' }],
 *   },
 *   input: { ticker: 'AAPL', lookback_days: 30 },
 * });
 *
 * console.log(result.status, result.duration_ms);
 * ```
 */

// ─── Enums ────────────────────────────────────────────────────────────────────

/** Cognitive layer for automatic LLM tier routing. */
export enum CognitiveLayer {
  /** Ingest signals, alerts, documents, telemetry — cheap model. */
  PERCEIVE  = 'PERCEIVE',
  /** Fetch knowledge, RAG, DB lookups — cheap model. */
  RETRIEVE  = 'RETRIEVE',
  /** Analysis, correlation, synthesis — premium model. */
  REASON    = 'REASON',
  /** Strategy, fix plans, runbooks — premium model. */
  PLAN      = 'PLAN',
  /** Execute tools, APIs, deployments — cheap model. */
  ACT       = 'ACT',
  /** Validate, test, audit, verify — premium model. */
  EVALUATE  = 'EVALUATE',
  /** Summarise, escalate, alert — cheap model. */
  REPORT    = 'REPORT',
}

/** Execution mode for the matrix. */
export enum ExecutionMode {
  /** One node at a time in topological order. */
  SEQUENTIAL = 'SEQUENTIAL',
  /** All nodes concurrently. */
  PARALLEL   = 'PARALLEL',
  /** DAG level-sets: parallel within each level, sequential across levels. */
  HYBRID     = 'HYBRID',
  /** Grouped by CognitiveLayer; each layer's nodes run in parallel. */
  DIAGONAL   = 'DIAGONAL',
}

/** Node type. */
export enum NodeType {
  TOOL     = 'TOOL',
  AGENT    = 'AGENT',
  FUNCTION = 'FUNCTION',
  MCP      = 'MCP',
}

/** Execution status. */
export enum ExecutionStatus {
  QUEUED    = 'QUEUED',
  RUNNING   = 'RUNNING',
  COMPLETED = 'COMPLETED',
  FAILED    = 'FAILED',
  ABORTED   = 'ABORTED',
  TIMEOUT   = 'TIMEOUT',
  PARTIAL   = 'PARTIAL',
}

// ─── Core types ───────────────────────────────────────────────────────────────

/** Retry policy for a node. */
export interface RetryPolicy {
  retries?: number;
  backoff_seconds?: number;
  backoff_multiplier?: number;
  max_backoff_seconds?: number;
  jitter?: boolean;
}

/** Timeout policy for a node. */
export interface TimeoutPolicy {
  timeout_seconds: number;
  hard_kill?: boolean;
}

/** Edge connecting two nodes. */
export interface Edge {
  /** Source node ID. */
  from: string;
  /** Target node ID. */
  to: string;
  /** Optional condition expression. */
  condition?: string;
  /** Optional label for the dashboard. */
  label?: string;
}

/** A single execution node. */
export interface Node {
  id: string;
  name: string;
  type: NodeType | string;
  handler: string;
  cognitive_layer?: CognitiveLayer | string;
  agent_role?: string;
  priority?: number;
  retry_policy?: RetryPolicy;
  timeout_policy?: TimeoutPolicy;
  fallback_node_id?: string;
  metadata?: Record<string, unknown>;
  config?: {
    params?: Record<string, unknown>;
    env?: Record<string, string>;
    tags?: string[];
  };
}

/** An execution matrix — the primary AFMX orchestration primitive. */
export interface ExecutionMatrix {
  id?: string;
  name: string;
  version?: string;
  mode?: ExecutionMode | string;
  nodes: Node[];
  edges?: Edge[];
  abort_policy?: 'FAIL_FAST' | 'CONTINUE' | 'CRITICAL_ONLY';
  max_parallelism?: number;
  global_timeout_seconds?: number;
  metadata?: Record<string, unknown>;
  tags?: string[];
}

/** Result of a single node execution. */
export interface NodeResult {
  node_id: string;
  node_name: string;
  status: string;
  output?: unknown;
  error?: string | null;
  error_type?: string | null;
  attempt?: number;
  duration_ms?: number | null;
  started_at?: number | null;
  finished_at?: number | null;
  metadata?: Record<string, unknown>;
}

/** Full execution response. */
export interface ExecutionResponse {
  execution_id: string;
  matrix_id: string;
  matrix_name: string;
  status: ExecutionStatus | string;
  total_nodes: number;
  completed_nodes: number;
  failed_nodes: number;
  skipped_nodes: number;
  duration_ms?: number | null;
  error?: string | null;
  error_node_id?: string | null;
  node_results: Record<string, NodeResult>;
  queued_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  tags?: string[];
}

/** Status-only response for polling. */
export interface ExecutionStatusResponse {
  execution_id: string;
  status: ExecutionStatus | string;
  matrix_id: string;
  matrix_name: string;
  total_nodes: number;
  completed_nodes: number;
  failed_nodes: number;
  skipped_nodes: number;
  duration_ms?: number | null;
  error?: string | null;
  queued_at: number;
  started_at?: number | null;
  finished_at?: number | null;
}

/** Cognitive Matrix view for an execution. */
export interface MatrixViewCell {
  node_id: string;
  node_name: string;
  status: string;
  duration_ms?: number | null;
  model_tier?: string | null;
  model?: string | null;
  error?: string | null;
  attempt?: number;
}

export interface MatrixViewSummary {
  total_possible: number;
  active_cells: number;
  success_cells: number;
  failed_cells: number;
  coverage_pct: number;
  success_rate: number;
}

export interface MatrixViewResponse {
  execution_id: string;
  matrix_name: string;
  status: string;
  layers: string[];
  roles: string[];
  role_meta: Record<string, { description?: string; domain?: string }>;
  cells: Record<string, MatrixViewCell>;
  summary: MatrixViewSummary;
}

/** Execute request body. */
export interface ExecuteRequest {
  matrix: ExecutionMatrix;
  input?: unknown;
  memory?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  triggered_by?: string;
  tags?: string[];
}

/** Async execute response. */
export interface AsyncExecuteResponse {
  execution_id: string;
  status: string;
  message: string;
  poll_url: string;
  stream_url: string;
}

/** Domain pack. */
export interface DomainPack {
  name: string;
  description: string;
  roles: Record<string, string>;
  tags: string[];
}

/** Validation response. */
export interface ValidateResponse {
  valid: boolean;
  errors: string[];
  node_count: number;
  edge_count: number;
  execution_order: string[];
}

// ─── Error types ──────────────────────────────────────────────────────────────

/** HTTP error from the AFMX API. */
export class AFMXError extends Error {
  public readonly status: number;
  public readonly detail: string;

  constructor(status: number, detail: string) {
    super(`AFMX API error ${status}: ${detail}`);
    this.name    = 'AFMXError';
    this.status  = status;
    this.detail  = detail;
  }
}

// ─── Client configuration ─────────────────────────────────────────────────────

export interface AFMXClientConfig {
  /**
   * Base URL of the AFMX server (e.g. ``"http://localhost:8100"``).
   * Do NOT include the ``/afmx`` path prefix — the client adds it.
   */
  baseUrl: string;

  /**
   * Optional API key for RBAC authentication.
   * Set the ``AFMX_RBAC_ENABLED=true`` env var on the server to require this.
   */
  apiKey?: string;

  /**
   * Request timeout in milliseconds (default: 30 000).
   */
  timeoutMs?: number;

  /**
   * Custom fetch implementation (default: globalThis.fetch).
   * Useful for Node.js 16 environments where fetch is not global.
   *
   * @example
   * ```typescript
   * import fetch from 'node-fetch';
   * const client = new AFMXClient({ baseUrl: '...', fetch });
   * ```
   */
  fetch?: typeof globalThis.fetch;
}

// ─── Main client ──────────────────────────────────────────────────────────────

/**
 * Type-safe AFMX REST API client.
 *
 * Works in any environment with a global ``fetch`` (Node 18+, browser,
 * Deno, Cloudflare Workers, Vercel Edge).
 *
 * @example
 * ```typescript
 * const client = new AFMXClient({ baseUrl: 'http://localhost:8100' });
 *
 * // Execute synchronously
 * const result = await client.execute({ matrix, input });
 *
 * // Execute asynchronously and poll
 * const { execution_id } = await client.executeAsync({ matrix, input });
 * const final = await client.pollUntilDone(execution_id);
 * ```
 */
export class AFMXClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;
  private readonly _fetch: typeof globalThis.fetch;

  constructor(config: AFMXClientConfig) {
    this.baseUrl   = config.baseUrl.replace(/\/+$/, '') + '/afmx';
    this.timeoutMs = config.timeoutMs ?? 30_000;
    this._fetch    = config.fetch ?? globalThis.fetch;

    this.headers = {
      'Content-Type': 'application/json',
      'User-Agent':   '@agentdyne9/afmx/1.3.0',
    };
    if (config.apiKey) {
      this.headers['X-API-Key'] = config.apiKey;
    }
  }

  // ── Execution ─────────────────────────────────────────────────────────────

  /**
   * Execute a matrix synchronously.
   *
   * Waits for the execution to complete before returning.
   * For long-running matrices, use {@link executeAsync} + {@link pollUntilDone}.
   */
  async execute(request: ExecuteRequest): Promise<ExecutionResponse> {
    return this._post<ExecutionResponse>('/execute', request);
  }

  /**
   * Execute a matrix asynchronously (fire-and-forget).
   *
   * Returns immediately with an ``execution_id``. Poll via {@link getStatus}
   * or use {@link pollUntilDone} for a blocking wait.
   */
  async executeAsync(request: ExecuteRequest): Promise<AsyncExecuteResponse> {
    return this._post<AsyncExecuteResponse>('/execute/async', request);
  }

  /**
   * Get the current status of an execution.
   */
  async getStatus(executionId: string): Promise<ExecutionStatusResponse> {
    return this._get<ExecutionStatusResponse>(`/status/${executionId}`);
  }

  /**
   * Get the full result of a completed execution.
   */
  async getResult(executionId: string): Promise<ExecutionResponse> {
    return this._get<ExecutionResponse>(`/result/${executionId}`);
  }

  /**
   * Cancel a running execution.
   */
  async cancel(executionId: string): Promise<{ message: string; status: string }> {
    return this._post(`/cancel/${executionId}`, {});
  }

  /**
   * Retry a failed execution.
   */
  async retry(executionId: string): Promise<{
    original_execution_id: string;
    new_execution_id: string;
    status: string;
    duration_ms?: number | null;
  }> {
    return this._post(`/retry/${executionId}`, {});
  }

  /**
   * Resume a failed/partial execution from its last checkpoint.
   */
  async resume(executionId: string): Promise<{
    original_execution_id: string;
    new_execution_id: string;
    status: string;
    resumed_from_node_count: number;
    duration_ms?: number | null;
  }> {
    return this._post(`/resume/${executionId}`, {});
  }

  /**
   * Poll an execution until it reaches a terminal state.
   *
   * @param executionId  The execution ID from {@link executeAsync}.
   * @param options.intervalMs  Poll interval (default: 500 ms).
   * @param options.timeoutMs   Max wait time (default: 300 000 ms / 5 min).
   *
   * @throws {AFMXError} if the timeout is exceeded.
   */
  async pollUntilDone(
    executionId: string,
    options: { intervalMs?: number; timeoutMs?: number } = {},
  ): Promise<ExecutionResponse> {
    const interval  = options.intervalMs ?? 500;
    const timeoutMs = options.timeoutMs  ?? 300_000;
    const deadline  = Date.now() + timeoutMs;

    const terminal = new Set<string>([
      'COMPLETED', 'FAILED', 'ABORTED', 'TIMEOUT', 'PARTIAL',
    ]);

    while (Date.now() < deadline) {
      const status = await this.getStatus(executionId);
      if (terminal.has(status.status)) {
        return this.getResult(executionId);
      }
      await _sleep(interval);
    }

    throw new AFMXError(
      408,
      `Execution '${executionId}' did not complete within ${timeoutMs}ms`,
    );
  }

  // ── Matrix management ─────────────────────────────────────────────────────

  /**
   * Validate a matrix definition without executing it.
   */
  async validate(matrix: ExecutionMatrix): Promise<ValidateResponse> {
    return this._post<ValidateResponse>('/validate', { matrix });
  }

  /**
   * List recent executions.
   */
  async listExecutions(options: {
    limit?: number;
    status?: string;
    matrix_name?: string;
  } = {}): Promise<{ count: number; executions: ExecutionStatusResponse[] }> {
    const params = new URLSearchParams();
    if (options.limit     !== undefined) params.set('limit',       String(options.limit));
    if (options.status    !== undefined) params.set('status_filter', options.status);
    if (options.matrix_name !== undefined) params.set('matrix_name', options.matrix_name);
    const qs = params.toString();
    return this._get(`/executions${qs ? '?' + qs : ''}`);
  }

  // ── Cognitive Matrix view ─────────────────────────────────────────────────

  /**
   * Get the Cognitive Matrix view for a completed execution.
   *
   * Returns a 2D cell map: ``CognitiveLayer × AgentRole``.
   * Includes per-cell model tier, cost, duration, and status.
   */
  async matrixView(executionId: string): Promise<MatrixViewResponse> {
    return this._get<MatrixViewResponse>(`/matrix-view/${executionId}`);
  }

  // ── Domain packs ──────────────────────────────────────────────────────────

  /**
   * List all registered domain packs (tech, finance, healthcare, legal, manufacturing).
   */
  async listDomains(): Promise<{ count: number; domains: DomainPack[] }> {
    return this._get('/domains');
  }

  /**
   * Get a specific domain pack by name.
   */
  async getDomain(name: string): Promise<DomainPack> {
    return this._get<DomainPack>(`/domains/${encodeURIComponent(name)}`);
  }

  // ── Health ────────────────────────────────────────────────────────────────

  /**
   * Check AFMX server health.
   */
  async health(): Promise<{ status: string; version: string }> {
    return this._get<{ status: string; version: string }>('/../health');
  }

  // ── Internal ──────────────────────────────────────────────────────────────

  private async _get<T>(path: string): Promise<T> {
    const url  = this.baseUrl + path;
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), this.timeoutMs);

    try {
      const resp = await this._fetch(url, {
        method:  'GET',
        headers: this.headers,
        signal:  ctrl.signal,
      });
      return _handleResponse<T>(resp);
    } finally {
      clearTimeout(tid);
    }
  }

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const url  = this.baseUrl + path;
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), this.timeoutMs);

    try {
      const resp = await this._fetch(url, {
        method:  'POST',
        headers: this.headers,
        body:    JSON.stringify(body),
        signal:  ctrl.signal,
      });
      return _handleResponse<T>(resp);
    } finally {
      clearTimeout(tid);
    }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function _handleResponse<T>(resp: Response): Promise<T> {
  if (resp.ok) {
    return (await resp.json()) as T;
  }
  let detail = `HTTP ${resp.status}`;
  try {
    const body = await resp.json() as { detail?: string };
    detail = body.detail ?? detail;
  } catch {
    // ignore parse failures
  }
  throw new AFMXError(resp.status, detail);
}

function _sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─── Convenience builder ──────────────────────────────────────────────────────

/**
 * Build a simple AFMX node with sensible defaults.
 *
 * @example
 * ```typescript
 * const node = buildNode({
 *   id: 'analyst',
 *   name: 'analyse-risk',
 *   handler: 'risk_analyser',
 *   layer: CognitiveLayer.REASON,
 *   role: 'RISK_MANAGER',
 * });
 * ```
 */
export function buildNode(opts: {
  id: string;
  name: string;
  handler: string;
  layer?: CognitiveLayer | string;
  role?: string;
  type?: NodeType | string;
  retries?: number;
  timeoutSeconds?: number;
  fallbackNodeId?: string;
  metadata?: Record<string, unknown>;
}): Node {
  return {
    id:               opts.id,
    name:             opts.name,
    type:             opts.type ?? NodeType.AGENT,
    handler:          opts.handler,
    cognitive_layer:  opts.layer,
    agent_role:       opts.role,
    fallback_node_id: opts.fallbackNodeId,
    metadata:         opts.metadata,
    ...(opts.retries !== undefined && {
      retry_policy: { retries: opts.retries },
    }),
    ...(opts.timeoutSeconds !== undefined && {
      timeout_policy: { timeout_seconds: opts.timeoutSeconds },
    }),
  };
}

/**
 * Build an edge between two nodes.
 */
export function buildEdge(from: string, to: string, condition?: string): Edge {
  return { from, to, ...(condition !== undefined && { condition }) };
}

// All types are already exported directly above via 'export interface' / 'export class'.
// No re-export block needed — adding one causes TS2484 (conflicting declarations).
