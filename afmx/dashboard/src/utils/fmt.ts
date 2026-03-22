import type { CSSProperties } from 'react'
import type { ExecutionStatus, NodeStatus } from '../types'
import { format, formatDistanceToNow } from 'date-fns'

/* ── Duration / numbers ── */
export const fmtMs = (ms: number | null | undefined): string => {
  if (ms == null) return '—'
  if (ms < 1000)  return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export const fmtSec = (s: number): string => {
  if (s < 60)    return `${Math.round(s)}s`
  if (s < 3_600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${Math.floor(s / 3_600)}h ${Math.floor((s % 3_600) / 60)}m`
}

export const fmtNum = (n: number): string => n.toLocaleString()

export const fmtPct = (n: number): string => `${(n * 100).toFixed(1)}%`

/* ── Timestamps ── */
export const fmtTs = (ts: number): string =>
  format(new Date(ts * 1000), 'HH:mm:ss')

export const fmtDate = (ts: number): string =>
  format(new Date(ts * 1000), 'MMM d, HH:mm')

export const fmtRelative = (ts: number): string =>
  formatDistanceToNow(new Date(ts * 1000), { addSuffix: true })

export const fmtIso = (iso: string): string =>
  format(new Date(iso), 'HH:mm:ss.SSS')

/* ── String helpers ── */
export const shortId = (id: string): string => id.slice(0, 8) + '…'

export const truncate = (s: string, n = 32): string =>
  s.length > n ? s.slice(0, n) + '…' : s

/* ── Execution status → CSS var colour ── */
export const EXEC_STATUS_COLOR: Record<ExecutionStatus, string> = {
  COMPLETED: 'var(--green)',
  FAILED:    'var(--red)',
  PARTIAL:   'var(--amber)',
  TIMEOUT:   'var(--amber)',
  RUNNING:   'var(--brand)',
  QUEUED:    'var(--text-3)',
  ABORTED:   'var(--text-3)',
}

export const EXEC_STATUS_BG: Record<ExecutionStatus, string> = {
  COMPLETED: 'var(--green-dim)',
  FAILED:    'var(--red-dim)',
  PARTIAL:   'var(--amber-dim)',
  TIMEOUT:   'var(--amber-dim)',
  RUNNING:   'var(--brand-dim)',
  QUEUED:    'rgba(82,82,91,.15)',
  ABORTED:   'rgba(82,82,91,.15)',
}

/* ── Node status → CSS var colour ── */
export const NODE_STATUS_COLOR: Record<NodeStatus, string> = {
  SUCCESS:  'var(--green)',
  FAILED:   'var(--red)',
  SKIPPED:  'var(--text-3)',
  RUNNING:  'var(--brand)',
  ABORTED:  'var(--text-3)',
  TIMEOUT:  'var(--amber)',
  FALLBACK: 'var(--purple)',
}

/* ── Recharts shared config ── */
export const TOOLTIP_STYLE: CSSProperties = {
  background:   'var(--bg-elevated)',
  border:       '1px solid var(--border-med)',
  borderRadius: 8,
  fontSize:     12,
  color:        'var(--text-1)',
  boxShadow:    'var(--shadow-md)',
}

export const AXIS_TICK = {
  fill:       'var(--text-3)',
  fontSize:   11,
  fontFamily: 'var(--mono)',
} as const

export const GRID = {
  stroke:          'var(--border)',
  strokeDasharray: '3 3',
} as const
