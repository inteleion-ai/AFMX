import {
  useQuery, useMutation, useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import { api } from '../api'
import { useApiKeyStore, toast } from '../store'
import type { ExecuteRequest, ExecutionRecord } from '../types'

/* ── Shared ── */
const useKey = () => useApiKeyStore(s => s.apiKey) || undefined
const STALE  = 30_000   // ms — TanStack considers data fresh
const POLL   = 60_000   // ms — background refetch interval

function q<T>(
  key:  unknown[],
  fn:   () => Promise<T>,
  opts?: Partial<UseQueryOptions<T>>,
) {
  return useQuery<T>({
    queryKey:        key,
    queryFn:         fn,
    staleTime:       STALE,
    refetchInterval: POLL,
    ...opts,
  })
}

/* ── Health ── */
export const useHealth = () => {
  const k = useKey()
  return q(['health'], () => api.health(k), { refetchInterval: 15_000 })
}

/* ── Exec stats (computed client-side) ── */
export const useExecStats = () => {
  const k = useKey()
  return q(['execStats'], () => api.execStats(k), { staleTime: 15_000 })
}

/* ── Execution list ── */
export const useExecutions = (params: {
  limit?:         number
  status_filter?: string
  matrix_name?:   string
} = {}) => {
  const k = useKey()
  return q(['executions', params], () => api.executions(params, k))
}

/* ── Single execution ── */
export const useExecution = (id: string) => {
  const k = useKey()
  return q(['execution', id], () => api.execution(id, k), {
    enabled:   !!id,
    staleTime: 5_000,
  })
}

/* ── Plugins ── */
export const usePlugins = () => {
  const k = useKey()
  return q(['plugins'], () => api.plugins(k), { staleTime: 120_000 })
}

/* ── Matrices ── */
export const useMatrices = () => {
  const k = useKey()
  return q(['matrices'], () => api.matrices(k))
}

/* ── Audit ── */
export const useAudit = (params: {
  limit?:   number
  action?:  string
  outcome?: string
  actor?:   string
} = {}) => {
  const k = useKey()
  return q(['audit', params], () => api.audit(params, k))
}

/* ── API Keys ── */
export const useApiKeys = () => {
  const k = useKey()
  return q(['apikeys'], () => api.keys(k))
}

export const useAdminStats = () => {
  const k = useKey()
  return q(['adminStats'], () => api.adminStats(k))
}

/* ── v1.2: Domain packs ── */
export const useDomains = () => {
  const k = useKey()
  return q(['domains'], () => api.domains(k), { staleTime: 300_000 })
}

export const useDomain = (name: string) => {
  const k = useKey()
  return q(['domain', name], () => api.domain(name, k), {
    enabled:   !!name,
    staleTime: 300_000,
  })
}

/* ── v1.2: Matrix View ── */
export const useMatrixView = (executionId: string) => {
  const k = useKey()
  return q(['matrixView', executionId], () => api.matrixView(executionId, k), {
    enabled:   !!executionId,
    staleTime: 10_000,
  })
}

/* ── Hooks ── */
export const useHooks = () => {
  const k = useKey()
  return q(['hooks'], () => api.hooks(k), { staleTime: 120_000 })
}

/* ── Execute mutations ─────────────────────────────────────────────────────
   Sync  → returns full ExecutionRecord
   Async → returns { execution_id, status, poll_url }
   Both variants are typed as a union so TanStack Query accepts the mutationFn.
─────────────────────────────────────────────────────────────────────────── */
type AsyncResult = { execution_id: string; status: string; poll_url: string }
type ExecuteResult = ExecutionRecord | AsyncResult

export const useExecuteMutation = (isAsync: boolean) => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation<ExecuteResult, Error, ExecuteRequest>({
    mutationFn: (body: ExecuteRequest): Promise<ExecuteResult> =>
      isAsync ? api.executeAsync(body, k) : api.execute(body, k),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['executions'] })
      qc.invalidateQueries({ queryKey: ['execStats']  })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export const useCancelMutation = () => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation({
    mutationFn: (id: string) => api.cancelExecution(id, k),
    onSuccess: () => {
      toast.success('Execution cancelled')
      qc.invalidateQueries({ queryKey: ['executions'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export const useRetryMutation = () => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation({
    mutationFn: (id: string) => api.retryExecution(id, k),
    onSuccess: (r) => {
      toast.success(`Retry queued → ${r.new_execution_id.slice(0, 8)}`)
      qc.invalidateQueries({ queryKey: ['executions'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export const useCreateKeyMutation = () => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation({
    mutationFn: (body: Parameters<typeof api.createKey>[0]) => api.createKey(body, k),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['apikeys'] }),
    onError:   (e: Error) => toast.error(e.message),
  })
}

export const useRevokeKeyMutation = () => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation({
    mutationFn: (id: string) => api.revokeKey(id, k),
    onSuccess: () => {
      toast.success('Key revoked')
      qc.invalidateQueries({ queryKey: ['apikeys'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export const useDeleteMatrixMutation = () => {
  const qc = useQueryClient()
  const k  = useKey()
  return useMutation({
    mutationFn: (name: string) => api.deleteMatrix(name, k),
    onSuccess: () => {
      toast.success('Matrix deleted')
      qc.invalidateQueries({ queryKey: ['matrices'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}
