import type { ReactNode, CSSProperties } from 'react'
import type { ExecutionStatus, NodeStatus } from '../../types'

/* ── Badge variants ── */
export type BadgeVariant =
  | 'green' | 'red' | 'amber' | 'brand' | 'purple' | 'cyan' | 'muted'

const BADGE_STYLES: Record<BadgeVariant, { bg: string; color: string; border: string }> = {
  green:  { bg: 'var(--green-dim)',  color: 'var(--green)',  border: 'var(--green-ring)'  },
  red:    { bg: 'var(--red-dim)',    color: 'var(--red)',    border: 'var(--red-ring)'    },
  amber:  { bg: 'var(--amber-dim)', color: 'var(--amber)',  border: 'var(--amber-ring)'  },
  brand:  { bg: 'var(--brand-dim)', color: 'var(--brand)',  border: 'var(--brand-ring)'  },
  purple: { bg: 'var(--purple-dim)',color: 'var(--purple)', border: 'var(--purple-ring)' },
  cyan:   { bg: 'var(--cyan-dim)',  color: 'var(--cyan)',   border: 'var(--cyan-ring)'   },
  muted:  { bg: 'var(--bg-muted)',  color: 'var(--text-3)', border: 'var(--border-med)'  },
}

/* ── Generic Badge ── */
interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  dot?:     boolean
  style?:   CSSProperties
}

export function Badge({ children, variant = 'muted', dot = false, style }: BadgeProps) {
  const s = BADGE_STYLES[variant]
  return (
    <span
      style={{
        display:      'inline-flex',
        alignItems:   'center',
        gap:          5,
        padding:      '2px 8px',
        borderRadius: 'var(--r-full)',
        fontSize:     11,
        fontWeight:   600,
        fontFamily:   'var(--mono)',
        background:   s.bg,
        color:        s.color,
        border:       `1px solid ${s.border}`,
        whiteSpace:   'nowrap',
        lineHeight:   1.6,
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width:      5,
            height:     5,
            borderRadius: '50%',
            background: s.color,
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  )
}

/* ── Execution status badge ── */
const EXEC_VARIANT: Record<ExecutionStatus, BadgeVariant> = {
  COMPLETED: 'green',
  FAILED:    'red',
  RUNNING:   'brand',
  PARTIAL:   'amber',
  TIMEOUT:   'amber',
  QUEUED:    'muted',
  ABORTED:   'muted',
}

export function ExecBadge({ status }: { status: ExecutionStatus }) {
  return <Badge variant={EXEC_VARIANT[status]} dot>{status}</Badge>
}

/* ── Node status badge ── */
const NODE_VARIANT: Record<NodeStatus, BadgeVariant> = {
  SUCCESS:  'green',
  FAILED:   'red',
  RUNNING:  'brand',
  FALLBACK: 'purple',
  TIMEOUT:  'amber',
  SKIPPED:  'muted',
  ABORTED:  'muted',
}

export function NodeBadge({ status }: { status: NodeStatus }) {
  return <Badge variant={NODE_VARIANT[status]} dot>{status}</Badge>
}
