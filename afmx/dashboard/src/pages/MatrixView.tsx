/**
 * MatrixView — Cognitive Execution Matrix visualizer
 *
 * v1.2 — Open Column Axis
 * -----------------------
 * The COLUMN axis (agent roles) is now FULLY DYNAMIC.
 * Column headers are discovered from the execution's node results, not from
 * a hardcoded list. Any domain vocabulary works:
 *   - Tech:          OPS, CODER, ANALYST …
 *   - Finance:       QUANT, TRADER, RISK_MANAGER …
 *   - Healthcare:    CLINICIAN, PHARMACIST, NURSE …
 *   - Legal:         PARALEGAL, PARTNER, ASSOCIATE …
 *   - Manufacturing: ENGINEER, QUALITY_INSPECTOR …
 *   - Custom:        anything UPPER_SNAKE_CASE
 *
 * The ROW axis (CognitiveLayer) remains FIXED:
 *   PERCEIVE → RETRIEVE → REASON → PLAN → ACT → EVALUATE → REPORT
 *
 * Apache-2.0 License. See LICENSE for details.
 */
import { useState, useMemo } from 'react'
import { useExecutions, useMatrixView } from '../hooks/useApi'
import { Card, CardHeader, Skeleton, ErrorState } from '../components/ui/Card'
import { ExecBadge } from '../components/ui/Badge'
import { fmtMs, shortId } from '../utils/fmt'
import type { CognitiveLayer, MatrixCell, RoleMeta } from '../types'

// ─── Fixed ROW axis — universal, never changes ────────────────────────────────

const LAYERS: CognitiveLayer[] = [
  'PERCEIVE', 'RETRIEVE', 'REASON', 'PLAN', 'ACT', 'EVALUATE', 'REPORT',
]

const LAYER_COLOR: Record<CognitiveLayer, string> = {
  PERCEIVE: '#185FA5', RETRIEVE: '#0F6E56', REASON: '#534AB7',
  PLAN:     '#854F0B', ACT:      '#993C1D', EVALUATE:'#3B6D11', REPORT: '#5F5E5A',
}
const LAYER_BG: Record<CognitiveLayer, string> = {
  PERCEIVE: '#E6F1FB', RETRIEVE: '#E1F5EE', REASON:  '#EEEDFE',
  PLAN:     '#FAEEDA', ACT:      '#FAECE7', EVALUATE:'#EAF3DE', REPORT: '#F1EFE8',
}
const LAYER_DESC: Record<CognitiveLayer, string> = {
  PERCEIVE: 'Ingest signals & data',   RETRIEVE: 'Fetch knowledge & context',
  REASON:   'Analyse & synthesise',    PLAN:     'Strategy & remediation',
  ACT:      'Execute & deploy',        EVALUATE: 'Validate & verify',
  REPORT:   'Summarise & escalate',
}

// ─── Domain badge colors ──────────────────────────────────────────────────────

const DOMAIN_COLORS: Record<string, { bg: string; color: string }> = {
  tech:          { bg: '#EEEDFE', color: '#534AB7' },
  finance:       { bg: '#FAEEDA', color: '#854F0B' },
  healthcare:    { bg: '#E1F5EE', color: '#0F6E56' },
  legal:         { bg: '#F1EFE8', color: '#444441' },
  manufacturing: { bg: '#FAECE7', color: '#993C1D' },
}

function domainBadge(domain: string | null | undefined) {
  if (!domain) return null
  const style = DOMAIN_COLORS[domain] ?? { bg: 'var(--bg-muted)', color: 'var(--text-3)' }
  return (
    <span style={{
      fontSize: 8.5, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase',
      padding: '1px 5px', borderRadius: 3,
      background: style.bg, color: style.color,
      flexShrink: 0,
    }}>
      {domain}
    </span>
  )
}

// ─── Status styles ────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, { bg: string; border: string; dot: string }> = {
  SUCCESS:  { bg: 'rgba(34,197,94,.12)',  border: 'rgba(34,197,94,.3)',  dot: '#16a34a' },
  FAILED:   { bg: 'rgba(239,68,68,.12)',  border: 'rgba(239,68,68,.3)',  dot: '#dc2626' },
  RUNNING:  { bg: 'rgba(59,130,246,.12)', border: 'rgba(59,130,246,.3)', dot: '#2563eb' },
  FALLBACK: { bg: 'rgba(127,119,221,.12)',border: 'rgba(127,119,221,.3)',dot: '#7F77DD' },
  SKIPPED:  { bg: 'var(--bg-muted)',      border: 'var(--border)',       dot: 'var(--text-4)' },
  ABORTED:  { bg: 'var(--bg-muted)',      border: 'var(--border)',       dot: 'var(--text-3)' },
}
const DEFAULT_STYLE = { bg: 'var(--bg-muted)', border: 'var(--border-light, rgba(0,0,0,.06))', dot: 'var(--text-4)' }
const st = (s: string | null) => STATUS_STYLE[s ?? ''] ?? DEFAULT_STYLE

// ─── Model tier badge ─────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null
  const isPremium = tier === 'premium'
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase',
      padding: '1px 5px', borderRadius: 3, flexShrink: 0,
      background: isPremium ? 'rgba(127,119,221,.15)' : 'rgba(34,197,94,.12)',
      color:      isPremium ? '#534AB7' : '#15803d',
      border:     `1px solid ${isPremium ? 'rgba(127,119,221,.3)' : 'rgba(34,197,94,.25)'}`,
    }}>
      {isPremium ? '★ premium' : '◇ cheap'}
    </span>
  )
}

// ─── Matrix cell ──────────────────────────────────────────────────────────────

function Cell({
  cell, layer, role, selected, onSelect,
}: {
  cell:     MatrixCell | undefined
  layer:    CognitiveLayer
  role:     string
  selected: boolean
  onSelect: () => void
}) {
  const empty  = !cell
  const style  = cell ? st(cell.status) : DEFAULT_STYLE
  const color  = LAYER_COLOR[layer]
  const bg     = LAYER_BG[layer]

  return (
    <td
      onClick={empty ? undefined : onSelect}
      title={empty ? `${layer} × ${role} — empty` : `${cell.node_name} (${cell.status})`}
      style={{ padding: 4, verticalAlign: 'top', cursor: empty ? 'default' : 'pointer' }}
    >
      <div style={{
        minWidth:     100,
        height:       68,
        borderRadius: 7,
        padding:      '6px 8px',
        display:      'flex',
        flexDirection:'column',
        gap:          3,
        transition:   'all .14s ease',
        opacity:      empty ? 0.28 : 1,
        background:   selected ? bg : empty ? 'var(--bg-muted)' : style.bg,
        border:       selected
          ? `2px solid ${color}`
          : `1px solid ${empty ? 'var(--border-light, rgba(0,0,0,.05))' : style.border}`,
        boxShadow:    selected ? `0 0 0 3px ${color}18` : 'none',
      }}>
        {empty ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 13, color: 'var(--text-4)', opacity: .4 }}>—</span>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0, background: style.dot }} />
              <span style={{
                fontSize: 11, fontWeight: 600, color: 'var(--text-1)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
              }}>
                {cell.node_name}
              </span>
            </div>
            <div style={{ fontSize: 9.5, fontFamily: 'var(--mono)', color: 'var(--text-3)', paddingLeft: 11 }}>
              {fmtMs(cell.duration_ms)}
            </div>
            <div style={{ paddingLeft: 11 }}>
              <TierBadge tier={cell.model_tier} />
            </div>
          </>
        )}
      </div>
    </td>
  )
}

// ─── Detail panel ─────────────────────────────────────────────────────────────

function DetailPanel({
  cell, layer, role, roleMeta, onClose,
}: {
  cell:     MatrixCell
  layer:    CognitiveLayer
  role:     string
  roleMeta: RoleMeta | undefined
  onClose:  () => void
}) {
  const s     = st(cell.status)
  const color = LAYER_COLOR[layer]
  const bg    = LAYER_BG[layer]

  return (
    <Card padding={0} style={{ position: 'sticky', top: 0 }}>
      <CardHeader
        title={cell.node_name}
        sub={`${layer} × ${role}`}
        right={
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 20, lineHeight: 1, padding: '0 4px' }}
          >×</button>
        }
      />
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* Status */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
          padding: '4px 10px', borderRadius: 20,
          background: s.bg, border: `1px solid ${s.border}`,
          fontSize: 12, fontWeight: 600, color: s.dot,
        }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.dot }} />
          {cell.status}
          {cell.attempt > 1 && <span style={{ fontWeight: 400, opacity: .7 }}>(attempt {cell.attempt})</span>}
        </div>

        {/* Cognitive layer */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
            Cognitive Layer (row)
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ padding: '3px 10px', borderRadius: 12, background: bg, color, fontSize: 12, fontWeight: 600 }}>
              {layer}
            </span>
            <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>{LAYER_DESC[layer]}</span>
          </div>
        </div>

        {/* Agent role — open string with domain attribution */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
            Agent Role (column)
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', fontFamily: 'var(--mono)' }}>{role}</span>
            {roleMeta?.domain && domainBadge(roleMeta.domain)}
          </div>
          {roleMeta?.description && (
            <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 4, lineHeight: 1.5 }}>
              {roleMeta.description}
            </div>
          )}
        </div>

        {/* Metrics grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {[
            { label: 'Duration',   value: fmtMs(cell.duration_ms),  mono: true  },
            { label: 'Model tier', value: cell.model_tier ?? '—',   mono: false },
          ].map(({ label, value, mono }) => (
            <div key={label} style={{ background: 'var(--bg-muted)', borderRadius: 7, padding: '8px 10px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 3 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', fontFamily: mono ? 'var(--mono)' : undefined }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* Model */}
        {cell.model && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>Model</div>
            <code style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-2)', background: 'var(--bg-muted)', padding: '2px 6px', borderRadius: 4 }}>
              {cell.model}
            </code>
          </div>
        )}

        {/* Error */}
        {cell.error && (
          <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.3)', borderRadius: 7 }}>
            <div style={{ fontSize: 10, color: '#dc2626', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 4 }}>Error</div>
            <div style={{ fontSize: 11.5, fontFamily: 'var(--mono)', color: '#dc2626', wordBreak: 'break-word', lineHeight: 1.5 }}>{cell.error}</div>
          </div>
        )}

        {/* Node ID */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>Node ID</div>
          <code style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-4)', wordBreak: 'break-all' }}>{cell.node_id}</code>
        </div>
      </div>
    </Card>
  )
}

// ─── Summary strip ────────────────────────────────────────────────────────────

function SummaryStrip({ summary, roleCount, domain }: {
  summary:   { active_cells: number; success_cells: number; failed_cells: number; coverage_pct: number; success_rate: number; total_possible: number }
  roleCount: number
  domain:    string | null
}) {
  const stats = [
    { label: 'Active cells',   value: String(summary.active_cells),   sub: `of ${summary.total_possible} possible` },
    { label: 'Coverage',       value: `${summary.coverage_pct}%`,     sub: `${LAYERS.length} layers × ${roleCount} roles` },
    { label: 'Success rate',   value: `${summary.success_rate}%`,     sub: `${summary.success_cells} of ${summary.active_cells}` },
    { label: 'Failed',         value: String(summary.failed_cells),   sub: summary.failed_cells > 0 ? 'review needed' : 'all clear' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
      {stats.map(({ label, value, sub }) => (
        <div key={label} style={{ background: 'var(--bg-muted)', borderRadius: 8, padding: '10px 14px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{label}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1 }}>{value}</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3, display: 'flex', alignItems: 'center', gap: 5 }}>
            {sub}
            {label === 'Coverage' && domain && domainBadge(domain)}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Layer legend ─────────────────────────────────────────────────────────────

function LayerLegend() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {LAYERS.map(layer => (
        <div
          key={layer}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '3px 10px', borderRadius: 20,
            background: LAYER_BG[layer], border: `1px solid ${LAYER_COLOR[layer]}44`,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: LAYER_COLOR[layer] }} />
          <span style={{ fontSize: 11, fontWeight: 600, color: LAYER_COLOR[layer] }}>{layer}</span>
          <span style={{ fontSize: 10.5, color: LAYER_COLOR[layer], opacity: .65 }}>— {LAYER_DESC[layer]}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Cross-domain example code ────────────────────────────────────────────────

const DOMAIN_EXAMPLES: Record<string, { label: string; node: { cognitive_layer: string; agent_role: string } }[]> = {
  tech:          [{ label: 'ops node',        node: { cognitive_layer: 'PERCEIVE', agent_role: 'OPS' } },
                  { label: 'analyst node',     node: { cognitive_layer: 'REASON',  agent_role: 'ANALYST' } }],
  finance:       [{ label: 'quant node',       node: { cognitive_layer: 'REASON',  agent_role: 'QUANT' } },
                  { label: 'risk node',        node: { cognitive_layer: 'EVALUATE',agent_role: 'RISK_MANAGER' } }],
  healthcare:    [{ label: 'clinician node',   node: { cognitive_layer: 'REASON',  agent_role: 'CLINICIAN' } },
                  { label: 'pharmacist node',  node: { cognitive_layer: 'PLAN',    agent_role: 'PHARMACIST' } }],
  legal:         [{ label: 'paralegal node',   node: { cognitive_layer: 'RETRIEVE',agent_role: 'PARALEGAL' } },
                  { label: 'partner node',     node: { cognitive_layer: 'PLAN',    agent_role: 'PARTNER' } }],
  manufacturing: [{ label: 'engineer node',    node: { cognitive_layer: 'REASON',  agent_role: 'ENGINEER' } },
                  { label: 'inspector node',   node: { cognitive_layer: 'EVALUATE',agent_role: 'QUALITY_INSPECTOR' } }],
}

// ─── Empty states ─────────────────────────────────────────────────────────────

function EmptySelectExecution() {
  const [exDomain, setExDomain] = useState('tech')
  const examples = DOMAIN_EXAMPLES[exDomain] ?? []

  return (
    <div style={{ padding: '40px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, color: 'var(--text-3)' }}>
      <svg width="44" height="44" viewBox="0 0 44 44" fill="none" opacity=".35">
        <rect x="3"  y="3"  width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="25" y="3"  width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="3"  y="25" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="25" y="25" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.5"/>
        <line x1="19" y1="11" x2="25" y2="11" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 2"/>
        <line x1="19" y1="33" x2="25" y2="33" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 2"/>
        <line x1="11" y1="19" x2="11" y2="25" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 2"/>
        <line x1="33" y1="19" x2="33" y2="25" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 2"/>
      </svg>
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: 14, color: 'var(--text-2)', fontWeight: 500, marginBottom: 4 }}>
          Select an execution to view its Cognitive Matrix
        </p>
        <p style={{ fontSize: 12 }}>
          Rows = cognitive layers (fixed) &nbsp;·&nbsp; Columns = agent roles (domain-specific)
        </p>
      </div>

      {/* Domain selector */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
        {Object.keys(DOMAIN_EXAMPLES).map(d => (
          <button key={d} onClick={() => setExDomain(d)} style={{
            padding: '3px 12px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer',
            background: d === exDomain ? (DOMAIN_COLORS[d]?.bg ?? 'var(--bg-muted)') : 'var(--bg-muted)',
            color:      d === exDomain ? (DOMAIN_COLORS[d]?.color ?? 'var(--text-2)') : 'var(--text-3)',
            border:     `1px solid ${d === exDomain ? (DOMAIN_COLORS[d]?.color ?? 'var(--border)') + '66' : 'var(--border)'}`,
          }}>
            {d}
          </button>
        ))}
      </div>

      {/* Example node snippet */}
      <pre style={{
        padding: '10px 14px', background: 'var(--bg-muted)', borderRadius: 8,
        fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-2)', lineHeight: 1.65,
        overflowX: 'auto', maxWidth: 480, width: '100%',
      }}>
{`{
  "name": "my-node",
  "type": "AGENT",
  "handler": "my_handler",
  "cognitive_layer": "${examples[0]?.node.cognitive_layer ?? 'REASON'}",
  "agent_role":      "${examples[0]?.node.agent_role      ?? 'ANALYST'}"
}`}
      </pre>
    </div>
  )
}

function EmptyNoCoordinates() {
  return (
    <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-3)' }}>
      <p style={{ fontSize: 14, color: 'var(--text-2)', fontWeight: 500, marginBottom: 8 }}>
        No matrix coordinates in this execution
      </p>
      <p style={{ fontSize: 12, maxWidth: 420, margin: '0 auto', lineHeight: 1.6 }}>
        Add <code style={{ fontFamily: 'var(--mono)', fontSize: 11, background: 'var(--bg-muted)', padding: '1px 5px', borderRadius: 3 }}>cognitive_layer</code> and{' '}
        <code style={{ fontFamily: 'var(--mono)', fontSize: 11, background: 'var(--bg-muted)', padding: '1px 5px', borderRadius: 3 }}>agent_role</code> to your nodes to populate the matrix.
        Works with any domain vocabulary — tech, finance, healthcare, legal, manufacturing, or custom.
      </p>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function MatrixViewPage() {
  const [selectedExecId, setSelectedExecId] = useState('')
  const [selectedCell,   setSelectedCell]   = useState<{ layer: CognitiveLayer; role: string } | null>(null)

  const { data: execs, isLoading: execsLoading } = useExecutions({ limit: 50 })
  const { data: view,  isLoading: viewLoading, error: viewError } = useMatrixView(selectedExecId)

  // v1.2: COLUMNS come from the API — dynamic, domain-specific
  const roles: string[]                        = useMemo(() => view?.roles ?? [], [view])
  const roleMeta: Record<string, RoleMeta>     = useMemo(() => view?.role_meta ?? {}, [view])
  const cellMap:  Record<string, MatrixCell>   = useMemo(() => view?.cells ?? {}, [view])

  const hasCoordinates = roles.length > 0

  // Detect dominant domain (for display in header + summary)
  const dominantDomain = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const r of roles) {
      const d = roleMeta[r]?.domain
      if (d) counts[d] = (counts[d] ?? 0) + 1
    }
    let best: string | null = null
    let max = 0
    for (const [d, n] of Object.entries(counts)) {
      if (n > max) { max = n; best = d }
    }
    return best
  }, [roles, roleMeta])

  const selectedCellData = selectedCell
    ? cellMap[`${selectedCell.layer}:${selectedCell.role}`] ?? null
    : null

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── Header ── */}
      <Card padding={0}>
        <div style={{ padding: '14px 18px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 14 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', display: 'flex', alignItems: 'center', gap: 8 }}>
              Cognitive Execution Matrix
              {dominantDomain && domainBadge(dominantDomain)}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>
              {hasCoordinates
                ? `${LAYERS.length} cognitive layers × ${roles.length} agent roles (${dominantDomain ?? 'custom domain'})`
                : '7 fixed cognitive layers × domain-specific agent roles'}
            </div>
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
            <label style={{ fontSize: 12, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>Execution</label>
            <select
              value={selectedExecId}
              onChange={e => { setSelectedExecId(e.target.value); setSelectedCell(null) }}
              aria-label="Select execution"
              style={{
                padding: '6px 10px', background: 'var(--bg-elevated)',
                border: '1px solid var(--border-med)', borderRadius: 8,
                fontSize: 12, color: 'var(--text-1)', fontFamily: 'var(--mono)',
                minWidth: 260, cursor: 'pointer',
              }}
            >
              <option value="">— pick an execution —</option>
              {execsLoading
                ? <option disabled>Loading…</option>
                : execs?.executions.map(e => (
                    <option key={e.execution_id} value={e.execution_id}>
                      {shortId(e.execution_id)}  {e.matrix_name}  [{e.status}]
                    </option>
                  ))
              }
            </select>
            {view && <ExecBadge status={view.status} />}
          </div>
        </div>
      </Card>

      {/* ── Summary strip ── */}
      {view && hasCoordinates && (
        <SummaryStrip summary={view.summary} roleCount={roles.length} domain={dominantDomain} />
      )}

      {/* ── Matrix + detail panel ── */}
      <div style={{ display: 'grid', gridTemplateColumns: hasCoordinates && selectedCellData ? '1fr 290px' : '1fr', gap: 16 }}>

        <Card padding={0}>
          {(viewLoading || (execsLoading && !selectedExecId)) && (
            <div style={{ padding: '40px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={56} />)}
            </div>
          )}

          {viewError && !viewLoading && (
            <ErrorState message={(viewError as Error).message} />
          )}

          {!selectedExecId && !viewLoading && <EmptySelectExecution />}

          {view && !hasCoordinates && !viewLoading && <EmptyNoCoordinates />}

          {view && hasCoordinates && !viewLoading && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'separate', borderSpacing: '4px', minWidth: '100%' }}>
                <thead>
                  <tr>
                    {/* Corner */}
                    <th style={{
                      minWidth: 110, padding: '8px 8px 8px 16px',
                      textAlign: 'right', fontSize: 9.5, color: 'var(--text-4)',
                      fontWeight: 500, whiteSpace: 'nowrap',
                    }}>
                      Layer ↓ &nbsp; Role →
                    </th>

                    {/* Dynamic column headers — one per role in this execution */}
                    {roles.map(role => {
                      const meta   = roleMeta[role]
                      const domain = meta?.domain ?? null
                      return (
                        <th
                          key={role}
                          title={meta?.description ?? role}
                          style={{
                            minWidth: 108, padding: '6px 6px 8px',
                            textAlign: 'center', verticalAlign: 'bottom',
                          }}
                        >
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                            <span style={{
                              fontSize: 10.5, fontWeight: 700, color: 'var(--text-2)',
                              letterSpacing: '.04em', textTransform: 'uppercase',
                            }}>
                              {role}
                            </span>
                            {domain && domainBadge(domain)}
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>

                <tbody>
                  {LAYERS.map(layer => (
                    <tr key={layer}>
                      {/* Row header */}
                      <td style={{ padding: '4px 6px 4px 16px', whiteSpace: 'nowrap' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: LAYER_COLOR[layer], letterSpacing: '.04em' }}>
                            {layer}
                          </span>
                          <span style={{ fontSize: 9.5, color: 'var(--text-4)' }}>
                            {LAYER_DESC[layer]}
                          </span>
                        </div>
                      </td>

                      {/* Dynamic cells */}
                      {roles.map(role => {
                        const key = `${layer}:${role}`
                        const sel = selectedCell?.layer === layer && selectedCell?.role === role
                        return (
                          <Cell
                            key={key}
                            cell={cellMap[key]}
                            layer={layer}
                            role={role}
                            selected={sel}
                            onSelect={() => sel ? setSelectedCell(null) : setSelectedCell({ layer, role })}
                          />
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Legend */}
              <div style={{
                padding: '10px 16px 14px', borderTop: '1px solid var(--border)',
                display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center',
              }}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {[
                    { s: 'SUCCESS', l: 'Success' }, { s: 'FAILED',   l: 'Failed' },
                    { s: 'FALLBACK',l: 'Fallback' },{ s: 'SKIPPED',  l: 'Skipped' },
                  ].map(({ s, l }) => (
                    <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: st(s).dot }} />
                      <span style={{ color: 'var(--text-3)' }}>{l}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center' }}>
                  <TierBadge tier="cheap" />
                  <TierBadge tier="premium" />
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* Detail panel */}
        {hasCoordinates && selectedCellData && selectedCell && (
          <DetailPanel
            cell={selectedCellData}
            layer={selectedCell.layer}
            role={selectedCell.role}
            roleMeta={roleMeta[selectedCell.role]}
            onClose={() => setSelectedCell(null)}
          />
        )}
      </div>

      {/* ── Layer guide ── */}
      <Card padding={0}>
        <CardHeader title="Cognitive layer guide" sub="The fixed ROW axis — universal across every domain and industry" />
        <div style={{ padding: '0 16px 16px' }}>
          <LayerLegend />
        </div>
      </Card>

      {/* ── Role vocabulary guide — only shown when an execution with coordinates is selected ── */}
      {hasCoordinates && roles.length > 0 && (
        <Card padding={0}>
          <CardHeader
            title="Agent role vocabulary"
            sub={`${roles.length} roles detected in this execution${dominantDomain ? ` · ${dominantDomain} domain` : ''}`}
          />
          <div style={{ padding: '0 16px 16px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {roles.map(role => {
              const meta   = roleMeta[role]
              const domain = meta?.domain ?? null
              const colors = domain ? (DOMAIN_COLORS[domain] ?? null) : null
              return (
                <div
                  key={role}
                  title={meta?.description ?? role}
                  style={{
                    padding: '5px 12px', borderRadius: 20, fontSize: 11.5, fontWeight: 500,
                    background: colors?.bg ?? 'var(--bg-muted)',
                    color:      colors?.color ?? 'var(--text-2)',
                    border:     `1px solid ${colors?.color ? colors.color + '44' : 'var(--border)'}`,
                    cursor:     'default',
                  }}
                >
                  {role}
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
