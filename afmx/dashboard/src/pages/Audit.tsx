import { useState } from 'react'
import { useAudit } from '../hooks/useApi'
import { Card, Skeleton, ErrorState } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { fmtDate, fmtMs } from '../utils/fmt'
import type { BadgeVariant } from '../components/ui/Badge'

const ACTIONS = [
  'execution.created', 'execution.completed', 'execution.failed',
  'execution.cancelled', 'execution.retried', 'execution.resumed',
  'execution.async_created',
  'matrix.saved', 'matrix.deleted', 'matrix.executed',
  'key.created', 'key.revoked', 'key.deleted',
  'auth.success', 'auth.failure', 'auth.denied', 'auth.expired',
  'server.started', 'server.stopped',
]

const OUTCOMES = ['success', 'failure', 'denied'] as const

/* ── Colour helpers ── */
function outcomeBadge(o: string) {
  const variant: BadgeVariant =
    o === 'success' ? 'green' :
    o === 'failure' ? 'red'   : 'amber'
  return <Badge variant={variant}>{o}</Badge>
}

function roleBadgeVariant(role: string): BadgeVariant {
  return role === 'ADMIN'     ? 'red'   :
         role === 'OPERATOR'  ? 'amber' :
         role === 'DEVELOPER' ? 'brand' :
         role === 'SERVICE'   ? 'green' : 'muted'
}

function actionColor(a: string): string {
  if (a.includes('failed') || a.includes('failure') || a.includes('denied'))  return 'var(--red)'
  if (a.includes('retried') || a.includes('resumed') || a.includes('expired')) return 'var(--amber)'
  if (a.startsWith('auth'))    return 'var(--cyan)'
  if (a.startsWith('key'))     return 'var(--purple)'
  if (a.includes('completed') || a.includes('success') || a.includes('started') || a.includes('created')) return 'var(--green)'
  return 'var(--text-2)'
}

/* ─────────────────────────────────────────────────────────────
   Audit log page
───────────────────────────────────────────────────────────── */
export default function Audit() {
  const [actionFilter,  setActionFilter]  = useState('')
  const [outcomeFilter, setOutcomeFilter] = useState('')
  const [actorFilter,   setActorFilter]   = useState('')

  const { data, isLoading, error } = useAudit({
    limit:   200,
    action:  actionFilter  || undefined,
    outcome: outcomeFilter || undefined,
    actor:   actorFilter   || undefined,
  })

  if (error) return <ErrorState message={error.message} />

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Filter bar ── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          className="field-input"
          value={actionFilter}
          onChange={e => setActionFilter(e.target.value)}
          style={{ width: 230 }}
        >
          <option value="">All actions</option>
          {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
        </select>

        <select
          className="field-input"
          value={outcomeFilter}
          onChange={e => setOutcomeFilter(e.target.value)}
          style={{ width: 150 }}
        >
          <option value="">All outcomes</option>
          {OUTCOMES.map(o => <option key={o} value={o}>{o}</option>)}
        </select>

        <input
          className="field-input"
          placeholder="Filter by actor…"
          value={actorFilter}
          onChange={e => setActorFilter(e.target.value)}
          style={{ width: 180 }}
        />

        {(actionFilter || outcomeFilter || actorFilter) && (
          <button
            onClick={() => { setActionFilter(''); setOutcomeFilter(''); setActorFilter('') }}
            style={{
              padding:      '7px 12px',
              borderRadius: 'var(--r-md)',
              background:   'none',
              border:       '1px solid var(--border-med)',
              color:        'var(--text-3)',
              fontSize:     12,
              cursor:       'pointer',
            }}
          >
            Clear
          </button>
        )}

        <div style={{ flex: 1 }} />

        {/* Export links — uses backend audit export endpoints */}
        {(['json', 'csv', 'ndjson'] as const).map(fmt => (
          <a
            key={fmt}
            href={`/afmx/audit/export/${fmt}`}
            download={`afmx-audit.${fmt}`}
            style={{
              padding:        '5px 10px',
              borderRadius:   'var(--r-md)',
              background:     'var(--bg-elevated)',
              border:         '1px solid var(--border-med)',
              fontSize:       12,
              color:          'var(--text-2)',
              textDecoration: 'none',
              fontWeight:     500,
              transition:     'all var(--t-fast)',
            }}
          >
            ↓ {fmt.toUpperCase()}
          </a>
        ))}

        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {data ? `${data.count} event${data.count !== 1 ? 's' : ''}` : ''}
        </span>
      </div>

      {/* ── Table ── */}
      <Card padding={0}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Role</th>
                <th>Resource</th>
                <th>Outcome</th>
                <th>Duration</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 12 }).map((_, i) => (
                  <tr key={i}>
                    {[110, 160, 100, 80, 120, 70, 70, 90].map((w, j) => (
                      <td key={j}><Skeleton h={13} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : (data?.events ?? []).length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-state">
                      <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                        <rect x="4" y="4" width="28" height="28" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                        <path d="M11 12h14M11 18h14M11 24h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity=".4"/>
                      </svg>
                      <p>No audit events match your filter</p>
                    </div>
                  </td>
                </tr>
              ) : data!.events.map(ev => (
                <tr key={ev.id} style={{ cursor: 'default' }}>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
                    {fmtDate(ev.timestamp)}
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: actionColor(ev.action), fontWeight: 600 }}>
                      {ev.action}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                      {ev.actor || '—'}
                    </span>
                  </td>
                  <td>
                    {ev.actor_role ? (
                      <Badge variant={roleBadgeVariant(ev.actor_role)}>
                        {ev.actor_role}
                      </Badge>
                    ) : (
                      <span style={{ color: 'var(--text-3)', fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td>
                    {ev.resource_type ? (
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>
                        {ev.resource_type}
                        {ev.resource_id ? `:${ev.resource_id.slice(0, 8)}` : ''}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-3)', fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td>{outcomeBadge(ev.outcome)}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--text-3)' }}>
                    {fmtMs(ev.duration_ms)}
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>
                    {ev.ip_address || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
