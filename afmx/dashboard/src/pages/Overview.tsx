import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useHealth, useExecStats, useExecutions } from '../hooks/useApi'
import { Card, StatCard, CardHeader, Skeleton, ErrorState } from '../components/ui/Card'
import { ExecBadge } from '../components/ui/Badge'
import { ExecutionTimeline } from '../components/charts/Charts'
import {
  fmtSec, fmtMs, fmtNum, fmtPct, fmtTs, shortId, truncate
} from '../utils/fmt'

export default function Overview() {
  const nav = useNavigate()
  const { data: health, isLoading: hLoading, error: hErr } = useHealth()
  const { data: stats,  isLoading: sLoading } = useExecStats()
  const { data: execs  } = useExecutions({ limit: 10 })

  if (hErr) return <ErrorState message="Cannot reach AFMX at /health — is the server running on :8100?" />

  const c = health?.concurrency

  // Build 12-bucket timeline from stats
  const chartData = useMemo(
    () => stats?.timeline ?? [],
    [stats]
  )

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── KPI stat cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <StatCard
          label="Uptime"
          value={hLoading ? <Skeleton h={28} /> : fmtSec(health?.uptime_seconds ?? 0)}
          sub={health?.environment ?? '—'}
          accent="var(--brand)"
          icon={<ClockIcon />}
        />
        <StatCard
          label="Executions (store)"
          value={hLoading ? <Skeleton h={28} /> : fmtNum(health?.active_executions ?? 0)}
          sub={`${health?.store_backend ?? '—'} backend`}
          accent="var(--green)"
          icon={<PlayIcon />}
        />
        <StatCard
          label="Concurrency"
          value={hLoading ? <Skeleton h={28} /> : `${c?.active ?? 0} / ${c?.max_concurrent ?? 0}`}
          sub={c ? `peak ${c.peak_active} · ${c.utilization_pct}% util` : '—'}
          accent="var(--amber)"
          icon={<BoltIcon />}
        />
        <StatCard
          label="Success Rate (24h)"
          value={sLoading ? <Skeleton h={28} /> : fmtPct(stats?.success_rate ?? 0)}
          sub={stats ? `${fmtNum(stats.total)} total runs` : '—'}
          accent={stats && stats.success_rate < .9 ? 'var(--red)' : 'var(--green)'}
          icon={<CheckIcon />}
        />
      </div>

      {/* ── Secondary stats row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <StatCard label="Completed (24h)" value={sLoading ? '—' : fmtNum(stats?.completed ?? 0)} accent="var(--green)" />
        <StatCard label="Failed (24h)"    value={sLoading ? '—' : fmtNum(stats?.failed    ?? 0)} accent="var(--red)" />
        <StatCard label="Avg Duration"    value={sLoading ? '—' : fmtMs(stats?.avg_duration_ms)} accent="var(--brand)" />
        <StatCard label="p95 Duration"    value={sLoading ? '—' : fmtMs(stats?.p95_duration_ms)} accent="var(--amber)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>

        {/* ── Timeline chart ── */}
        <Card padding={0}>
          <CardHeader title="Execution Activity (24h)" sub="Completed vs Failed per 2h bucket" />
          <div style={{ padding: '16px 16px 12px' }}>
            {chartData.length ? (
              <ExecutionTimeline data={chartData} height={160} />
            ) : (
              <div className="empty-state" style={{ height: 160 }}>
                <p>No execution data yet</p>
              </div>
            )}
          </div>
        </Card>

        {/* ── Engine status panel ── */}
        <Card padding={0}>
          <CardHeader title="Engine Status" />
          <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {hLoading ? (
              Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} h={14} w="80%" />)
            ) : health ? (
              <>
                <Row label="Version"     value={health.version} mono />
                <Row label="Environment" value={health.environment} />
                <Row label="Store"       value={health.store_backend} />
                <Row label="RBAC"        value={health.rbac_enabled   ? 'Enabled'  : 'Disabled'} color={health.rbac_enabled   ? 'var(--green)' : 'var(--text-3)'} />
                <Row label="Audit"       value={health.audit_enabled  ? 'Enabled'  : 'Disabled'} color={health.audit_enabled  ? 'var(--green)' : 'var(--text-3)'} />
                <Row label="Webhooks"    value={health.webhooks_enabled? 'Configured':'Not set'}  color={health.webhooks_enabled?'var(--brand)' : 'var(--text-3)'} />
                <Row label="Agentability"value={health.agentability?.connected ? '● Connected' : '● Offline'} color={health.agentability?.connected ? 'var(--green)' : 'var(--text-3)'} />
                {health.adapters.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 6 }}>Adapters</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {health.adapters.map(a => (
                        <span key={a} style={{ padding: '1px 7px', background: 'var(--brand-dim)', color: 'var(--brand)', borderRadius: 'var(--r-full)', fontSize: 11, fontWeight: 600 }}>
                          {a}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : null}
          </div>
        </Card>
      </div>

      {/* ── Recent executions ── */}
      <Card padding={0}>
        <CardHeader
          title="Recent Executions"
          right={
            <button
              onClick={() => nav('/executions')}
              style={{ fontSize: 12, color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              View all →
            </button>
          }
        />
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Execution ID</th>
                <th>Matrix</th>
                <th>Status</th>
                <th>Nodes</th>
                <th>Duration</th>
                <th>Queued</th>
              </tr>
            </thead>
            <tbody>
              {!execs ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {[70, 120, 80, 60, 70, 80].map((w, j) => (
                      <td key={j}><Skeleton h={14} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : execs.executions.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-state" style={{ padding: '32px 0' }}>
                      <p>No executions yet — run your first matrix</p>
                    </div>
                  </td>
                </tr>
              ) : (
                execs.executions.map(e => (
                  <tr key={e.execution_id} onClick={() => nav(`/executions?id=${e.execution_id}`)}>
                    <td>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--brand)' }}>
                        {shortId(e.execution_id)}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>
                        {truncate(e.matrix_name, 24)}
                      </span>
                    </td>
                    <td><ExecBadge status={e.status} /></td>
                    <td style={{ color: 'var(--text-2)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                      {e.completed_nodes}/{e.total_nodes}
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>
                      {fmtMs(e.duration_ms)}
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-3)' }}>
                      {fmtTs(e.queued_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

/* ── Local helpers ── */
function Row({
  label, value, mono = false, color,
}: { label: string; value: string; mono?: boolean; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
      <span style={{ color: 'var(--text-3)' }}>{label}</span>
      <span style={{ fontFamily: mono ? 'var(--mono)' : undefined, color: color ?? 'var(--text-1)', fontWeight: 500 }}>
        {value}
      </span>
    </div>
  )
}

function ClockIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3"/><path d="M8 5v3.5L10.5 10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
}
function PlayIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><polygon points="4 2.5 13 8 4 13.5" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
}
function BoltIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M9 2L4 9h5l-2 5 7-7H9L11 2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
}
function CheckIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3"/><path d="M5 8l2.5 2.5L11 6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
}
