import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useExecutions, useExecution, useCancelMutation, useRetryMutation } from '../hooks/useApi'
import { Card, Skeleton, ErrorState } from '../components/ui/Card'
import { ExecBadge, NodeBadge, Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Waterfall } from '../components/charts/Charts'
import { fmtMs, fmtDate, fmtRelative, shortId, truncate, NODE_STATUS_COLOR } from '../utils/fmt'
import type { ExecutionStatus, NodeResult } from '../types'

const STATUSES: ExecutionStatus[] = [
  'COMPLETED', 'FAILED', 'RUNNING', 'PARTIAL', 'TIMEOUT', 'ABORTED', 'QUEUED',
]

const TERMINAL: ExecutionStatus[] = ['FAILED', 'PARTIAL', 'TIMEOUT', 'ABORTED']

/* ─────────────────────────────────────────────────────────────
   Executions list page
───────────────────────────────────────────────────────────── */
export default function Executions() {
  const [sp, setSp] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState(sp.get('status') ?? '')
  const [matrixFilter, setMatrixFilter] = useState(sp.get('matrix') ?? '')
  const [detailId,     setDetailId]     = useState(sp.get('id')     ?? '')

  const { data, isLoading, error } = useExecutions({
    limit:         60,
    status_filter: statusFilter || undefined,
    matrix_name:   matrixFilter || undefined,
  })

  const cancelMut = useCancelMutation()
  const retryMut  = useRetryMutation()

  /* Sync detailId when URL ?id= param changes externally */
  useEffect(() => {
    const id = sp.get('id')
    if (id) setDetailId(id)
  }, [sp])

  const openDetail = (id: string) => {
    setDetailId(id)
    setSp(prev => { const n = new URLSearchParams(prev); n.set('id', id); return n })
  }

  const closeDetail = () => {
    setDetailId('')
    setSp(prev => { const n = new URLSearchParams(prev); n.delete('id'); return n })
  }

  if (error) return <ErrorState message={error.message} />

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Filter bar ── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          className="field-input"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={{ width: 160 }}
        >
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <input
          className="field-input"
          placeholder="Filter by matrix name…"
          value={matrixFilter}
          onChange={e => setMatrixFilter(e.target.value)}
          style={{ width: 220 }}
        />

        {(statusFilter || matrixFilter) && (
          <Button variant="ghost" onClick={() => { setStatusFilter(''); setMatrixFilter('') }}>
            Clear
          </Button>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {data ? `${data.count} result${data.count !== 1 ? 's' : ''}` : ''}
        </span>
      </div>

      {/* ── Table ── */}
      <Card padding={0}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Matrix</th>
                <th>Status</th>
                <th>Completed</th>
                <th>Failed</th>
                <th>Duration</th>
                <th>Queued</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i}>
                    {[80, 120, 90, 60, 50, 70, 100, 80].map((w, j) => (
                      <td key={j}><Skeleton h={14} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : data?.executions.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-state">
                      <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                        <circle cx="18" cy="18" r="16" stroke="currentColor" strokeWidth="1.5"/>
                        <path d="M12 18h12M18 12v12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity=".4"/>
                      </svg>
                      <p>No executions match your filter</p>
                    </div>
                  </td>
                </tr>
              ) : data?.executions.map(e => (
                <tr key={e.execution_id} onClick={() => openDetail(e.execution_id)}>
                  <td>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--brand)' }}>
                      {shortId(e.execution_id)}
                    </span>
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--text-2)' }}>
                      {truncate(e.matrix_name, 22)}
                    </span>
                  </td>
                  <td><ExecBadge status={e.status} /></td>
                  <td style={{ color: 'var(--text-2)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                    {e.completed_nodes}
                  </td>
                  <td style={{
                    color: e.failed_nodes > 0 ? 'var(--red)' : 'var(--text-3)',
                    fontFamily: 'var(--mono)', fontSize: 12,
                  }}>
                    {e.failed_nodes}
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>
                    {fmtMs(e.duration_ms)}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {fmtRelative(e.queued_at)}
                  </td>
                  <td onClick={ev => ev.stopPropagation()}>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {TERMINAL.includes(e.status) && (
                        <Button
                          size="xs"
                          onClick={() => retryMut.mutate(e.execution_id)}
                          loading={retryMut.isPending}
                        >
                          Retry
                        </Button>
                      )}
                      {e.status === 'RUNNING' && (
                        <Button
                          size="xs"
                          variant="danger"
                          onClick={() => cancelMut.mutate(e.execution_id)}
                          loading={cancelMut.isPending}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── Detail modal ── */}
      {detailId && (
        <DetailModal
          id={detailId}
          onClose={closeDetail}
          onRetry={id => retryMut.mutate(id)}
          onCancel={id => cancelMut.mutate(id)}
          retryLoading={retryMut.isPending}
          cancelLoading={cancelMut.isPending}
        />
      )}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   Execution detail modal
───────────────────────────────────────────────────────────── */
interface DetailModalProps {
  id:            string
  onClose:       () => void
  onRetry:       (id: string) => void
  onCancel:      (id: string) => void
  retryLoading:  boolean
  cancelLoading: boolean
}

function DetailModal({ id, onClose, onRetry, onCancel, retryLoading, cancelLoading }: DetailModalProps) {
  const { data, isLoading, error } = useExecution(id)
  const [tab, setTab] = useState<'trace' | 'waterfall' | 'output'>('trace')

  const nodes: NodeResult[] = data ? Object.values(data.node_results) : []

  /* Build waterfall rows from node timing */
  const starts   = nodes.map(n => n.started_at  ?? Infinity).filter(v => isFinite(v))
  const ends     = nodes.map(n => n.finished_at ?? 0)
  const minStart = starts.length  ? Math.min(...starts) : 0
  const maxEnd   = ends.length    ? Math.max(...ends)   : 0
  const totalMs  = Math.max((maxEnd - minStart) * 1000, 1)

  const wfRows = nodes.map(n => ({
    name:       n.node_name,
    startPct:   n.started_at  != null ? (((n.started_at  - minStart) * 1000) / totalMs) * 100 : 0,
    widthPct:   n.duration_ms != null ? ((n.duration_ms)              / totalMs) * 100        : 0,
    color:      NODE_STATUS_COLOR[n.status] ?? 'var(--text-3)',
    durationMs: n.duration_ms,
  }))

  const TABS = ['trace', 'waterfall', 'output'] as const

  return (
    <Modal
      open
      onClose={onClose}
      title="Execution Detail"
      subtitle={id}
      maxWidth={800}
      footer={
        <>
          {data && TERMINAL.includes(data.status) && (
            <Button variant="secondary" onClick={() => onRetry(id)} loading={retryLoading}>
              Retry
            </Button>
          )}
          {data?.status === 'RUNNING' && (
            <Button variant="danger" onClick={() => onCancel(id)} loading={cancelLoading}>
              Cancel
            </Button>
          )}
          <Button variant="ghost" onClick={onClose} style={{ marginLeft: 'auto' }}>
            Close
          </Button>
        </>
      }
    >
      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={16} />)}
        </div>
      ) : error ? (
        <ErrorState message={error.message} />
      ) : data ? (
        <>
          {/* Summary strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
            {([
              ['Status',   <ExecBadge status={data.status} />],
              ['Duration', <span className="mono" style={{ fontSize: 13 }}>{fmtMs(data.duration_ms)}</span>],
              ['Nodes',    <span className="mono" style={{ fontSize: 13 }}>{data.completed_nodes}/{data.total_nodes}</span>],
              ['Failed',   <span className="mono" style={{ fontSize: 13, color: data.failed_nodes > 0 ? 'var(--red)' : 'var(--text-3)' }}>{data.failed_nodes}</span>],
            ] as const).map(([label, val], i) => (
              <div key={i} style={{ background: 'var(--bg-muted)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: '10px 12px' }}>
                <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 4 }}>
                  {label}
                </div>
                <div>{val}</div>
              </div>
            ))}
          </div>

          {/* Error banner */}
          {data.error && (
            <div style={{ padding: '10px 12px', background: 'var(--red-dim)', border: '1px solid var(--red-ring)', borderRadius: 'var(--r-md)', marginBottom: 14, fontSize: 12.5, color: 'var(--red)' }}>
              {data.error_node_id && (
                <span style={{ fontFamily: 'var(--mono)', marginRight: 8 }}>[{data.error_node_id}]</span>
              )}
              {data.error}
            </div>
          )}

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 2, background: 'var(--bg-muted)', borderRadius: 'var(--r-md)', padding: 3, width: 'fit-content', marginBottom: 14 }}>
            {TABS.map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding:        '5px 12px',
                  borderRadius:   'calc(var(--r-md) - 2px)',
                  fontSize:       12.5,
                  fontWeight:     500,
                  background:     tab === t ? 'var(--bg-elevated)' : 'transparent',
                  color:          tab === t ? 'var(--text-1)'      : 'var(--text-3)',
                  boxShadow:      tab === t ? 'var(--shadow-sm)'   : 'none',
                  border:         'none',
                  cursor:         'pointer',
                  transition:     'all var(--t-base)',
                  textTransform:  'capitalize',
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* ── Trace tab ── */}
          {tab === 'trace' && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {nodes.length === 0 ? (
                <div className="empty-state" style={{ padding: '24px 0' }}>
                  <p>No node results yet</p>
                </div>
              ) : nodes.map((n, i) => (
                <div
                  key={n.node_id}
                  style={{
                    display:      'flex',
                    alignItems:   'flex-start',
                    gap:          10,
                    padding:      '9px 0',
                    borderBottom: i < nodes.length - 1 ? '1px solid var(--border-light)' : 'none',
                  }}
                >
                  {/* Status icon */}
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `${NODE_STATUS_COLOR[n.status]}22`,
                    border:     `1.5px solid ${NODE_STATUS_COLOR[n.status]}44`,
                    fontSize:   9, fontWeight: 800,
                    color:      NODE_STATUS_COLOR[n.status],
                  }}>
                    {n.status === 'SUCCESS' ? '✓' :
                     n.status === 'FAILED'  ? '✕' :
                     n.status === 'SKIPPED' ? '—' : '↩'}
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>
                        {n.node_name}
                      </span>
                      <NodeBadge status={n.status} />
                      {n.attempt > 1 && (
                        <span style={{ fontSize: 10.5, color: 'var(--amber)', fontFamily: 'var(--mono)' }}>
                          attempt ×{n.attempt}
                        </span>
                      )}
                    </div>
                    {n.error && (
                      <div style={{ fontSize: 11.5, color: 'var(--red)', marginTop: 2 }}>
                        {n.error}
                      </div>
                    )}
                    {Boolean((n.metadata as Record<string, unknown>)?.fallback_used) && (
                      <div style={{ fontSize: 11, color: 'var(--purple)', marginTop: 2 }}>
                        ↩ Fallback handler used
                      </div>
                    )}
                  </div>

                  <div style={{ fontSize: 11.5, fontFamily: 'var(--mono)', color: 'var(--text-3)', flexShrink: 0 }}>
                    {fmtMs(n.duration_ms)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── Waterfall tab ── */}
          {tab === 'waterfall' && (
            <div style={{ padding: '8px 0' }}>
              <Waterfall rows={wfRows} />
            </div>
          )}

          {/* ── Output tab ── */}
          {tab === 'output' && (
            <div>
              {nodes.filter(n => n.output != null).length === 0 ? (
                <div className="empty-state" style={{ padding: '24px 0' }}>
                  <p>No output data for this execution</p>
                </div>
              ) : nodes.map(n => n.output != null && (
                <div key={n.node_id} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, fontFamily: 'var(--mono)' }}>
                    {n.node_name}
                  </div>
                  <pre style={{
                    fontSize:    11.5,
                    fontFamily:  'var(--mono)',
                    background:  'var(--bg-muted)',
                    borderRadius:'var(--r-md)',
                    padding:     '10px 12px',
                    color:       'var(--text-2)',
                    lineHeight:  1.6,
                    border:      '1px solid var(--border)',
                    whiteSpace:  'pre-wrap',
                    wordBreak:   'break-word',
                    maxHeight:   200,
                    overflowY:   'auto',
                  }}>
                    {JSON.stringify(n.output, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}

          {/* Queued/started/finished timestamps */}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Queued',   ts: data.queued_at  },
              { label: 'Started',  ts: data.started_at  },
              { label: 'Finished', ts: data.finished_at },
            ].map(({ label, ts }) => ts != null && (
              <div key={label}>
                <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em' }}>{label}</div>
                <div style={{ fontSize: 11.5, fontFamily: 'var(--mono)', color: 'var(--text-2)', marginTop: 2 }}>
                  {fmtDate(ts)}
                </div>
              </div>
            ))}
            {data.triggered_by && (
              <div>
                <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Triggered By</div>
                <div style={{ fontSize: 11.5, fontFamily: 'var(--mono)', color: 'var(--text-2)', marginTop: 2 }}>
                  {data.triggered_by}
                </div>
              </div>
            )}
            {data.tags.length > 0 && (
              <div>
                <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 4 }}>Tags</div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {data.tags.map(tag => (
                    <Badge key={tag} variant="muted">{tag}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      ) : null}
    </Modal>
  )
}
