import type {
  HealthResponse, ExecutionListResponse, ExecutionRecord,
  PluginListResponse, MatrixListResponse, AuditListResponse,
  ApiKeyListResponse, ValidateResponse, ExecuteRequest, HookEntry,
  ExecStats, ApiKey, AdminStatsResponse, ConcurrencyStats,
} from './types'

const BASE = ''  // same-origin; Vite dev proxy handles /afmx in dev

async function req<T>(
  method:  string,
  path:    string,
  body?:   unknown,
  apiKey?: string,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (apiKey) headers['X-AFMX-API-Key'] = apiKey

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      msg = j.detail ?? j.message ?? msg
    } catch { /* ignore parse error */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

const get  = <T>(path: string, key?: string)               => req<T>('GET',    path, undefined, key)
const post = <T>(path: string, body: unknown, key?: string) => req<T>('POST',   path, body,      key)
const del  = <T>(path: string, key?: string)               => req<T>('DELETE', path, undefined, key)

export const api = {
  /* ── System ── */
  health:      (key?: string) => get<HealthResponse>('/health', key),
  concurrency: (key?: string) => get<ConcurrencyStats>('/afmx/concurrency', key),
  hooks:       (key?: string) => get<{ hooks: HookEntry[] }>('/afmx/hooks', key),

  /* ── Executions ── */
  executions: (params: {
    limit?:         number
    status_filter?: string
    matrix_name?:   string
  }, key?: string) => {
    const qs = new URLSearchParams()
    if (params.limit)         qs.set('limit',         String(params.limit))
    if (params.status_filter) qs.set('status_filter', params.status_filter)
    if (params.matrix_name)   qs.set('matrix_name',   params.matrix_name)
    return get<ExecutionListResponse>(`/afmx/executions?${qs}`, key)
  },
  execution:       (id: string, key?: string) => get<ExecutionRecord>(`/afmx/result/${id}`, key),
  cancelExecution: (id: string, key?: string) =>
    post<{ message: string; status: string }>(`/afmx/cancel/${id}`, {}, key),
  retryExecution:  (id: string, key?: string) =>
    post<{ new_execution_id: string; status: string; duration_ms: number | null }>(`/afmx/retry/${id}`, {}, key),

  /* ── Execute ── */
  execute:      (body: ExecuteRequest, key?: string) => post<ExecutionRecord>('/afmx/execute', body, key),
  executeAsync: (body: ExecuteRequest, key?: string) =>
    post<{ execution_id: string; status: string; poll_url: string }>('/afmx/execute/async', body, key),
  validate:     (matrix: Record<string, unknown>, key?: string) =>
    post<ValidateResponse>('/afmx/validate', { matrix }, key),

  /* ── Plugins ── */
  plugins: (key?: string) => get<PluginListResponse>('/afmx/plugins', key),

  /* ── Matrices ── */
  matrices:      (key?: string) => get<MatrixListResponse>('/afmx/matrices', key),
  deleteMatrix:  (name: string, key?: string) => del<{ message: string }>(`/afmx/matrices/${name}`, key),
  executeMatrix: (name: string, key?: string) =>
    post<ExecutionRecord>(`/afmx/matrices/${name}/execute`, { triggered_by: 'dashboard' }, key),

  /* ── Audit ── */
  audit: (params: {
    limit?:   number
    action?:  string
    outcome?: string
    actor?:   string
  }, key?: string) => {
    const qs = new URLSearchParams()
    if (params.limit)   qs.set('limit',   String(params.limit))
    if (params.action)  qs.set('action',  params.action)
    if (params.outcome) qs.set('outcome', params.outcome)
    if (params.actor)   qs.set('actor',   params.actor)
    return get<AuditListResponse>(`/afmx/audit?${qs}`, key)
  },

  /* ── API Keys (RBAC) ── */
  keys:      (key?: string) => get<ApiKeyListResponse>('/afmx/admin/keys', key),
  createKey: (body: {
    name: string; role: string; tenant_id: string
    description: string; expires_in_days?: number
  }, key?: string) => post<ApiKey & { message: string }>('/afmx/admin/keys', body, key),
  revokeKey: (id: string, key?: string) =>
    post<{ message: string; key_id: string }>(`/afmx/admin/keys/${id}/revoke`, {}, key),
  deleteKey: (id: string, key?: string) =>
    del<{ message: string }>(`/afmx/admin/keys/${id}`, key),
  adminStats: (key?: string) => get<AdminStatsResponse>('/afmx/admin/stats', key),

  /* ── Stats — computed client-side from /executions ── */
  execStats: async (key?: string): Promise<ExecStats> => {
    const data  = await get<ExecutionListResponse>('/afmx/executions?limit=200', key)
    const execs = data.executions

    const completed = execs.filter(e => e.status === 'COMPLETED').length
    const failed    = execs.filter(e => e.status === 'FAILED').length
    const partial   = execs.filter(e => e.status === 'PARTIAL').length
    const running   = execs.filter(e => e.status === 'RUNNING').length
    const durs      = execs
      .filter(e => e.duration_ms != null)
      .map(e => e.duration_ms as number)
      .sort((a, b) => a - b)

    const avg_duration_ms = durs.length ? durs.reduce((a, b) => a + b, 0) / durs.length : 0
    const p95_duration_ms = durs.length ? durs[Math.floor(durs.length * 0.95)] : 0

    /* 12 buckets over last 24 h */
    const now      = Date.now()
    const bucketMs = (24 * 3_600_000) / 12
    const timeline = Array.from({ length: 12 }, (_, i) => ({
      bucket:    now - (11 - i) * bucketMs,
      completed: 0,
      failed:    0,
    }))
    for (const e of execs) {
      const ts  = e.queued_at * 1000
      const idx = Math.floor((ts - (now - 24 * 3_600_000)) / bucketMs)
      if (idx >= 0 && idx < 12) {
        if (e.status === 'COMPLETED') timeline[idx].completed++
        if (e.status === 'FAILED' || e.status === 'PARTIAL') timeline[idx].failed++
      }
    }

    return {
      total: execs.length,
      completed, failed, partial, running,
      success_rate:     execs.length ? completed / execs.length : 0,
      avg_duration_ms,
      p95_duration_ms,
      timeline,
    }
  },
}
