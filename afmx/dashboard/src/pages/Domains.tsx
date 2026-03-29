/**
 * Domains — Agent Role Vocabulary Explorer
 *
 * v1.2: The open column axis.
 *
 * Shows all registered domain packs — the industry-specific role
 * vocabularies that define the COLUMN axis of the Cognitive Matrix.
 *
 * Built-in packs: tech, finance, healthcare, legal, manufacturing.
 * Custom packs can be registered via DomainRegistry at startup.
 *
 * Apache-2.0 License. See LICENSE for details.
 */
import { useState } from 'react'
import { useDomains } from '../hooks/useApi'
import { Card, CardHeader, Skeleton, ErrorState } from '../components/ui/Card'
import type { DomainPack } from '../types'

// ─── Domain brand colors (matching MatrixView) ────────────────────────────────

const DOMAIN_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  tech:          { bg: '#EEEDFE', color: '#3C3489', border: '#AFA9EC' },
  finance:       { bg: '#FAEEDA', color: '#633806', border: '#EF9F27' },
  healthcare:    { bg: '#E1F5EE', color: '#085041', border: '#5DCAA5' },
  legal:         { bg: '#F1EFE8', color: '#2C2C2A', border: '#B4B2A9' },
  manufacturing: { bg: '#FAECE7', color: '#712B13', border: '#F0997B' },
}

const DEFAULT_STYLE = { bg: 'var(--bg-muted)', color: 'var(--text-2)', border: 'var(--border)' }

function domainStyle(name: string) {
  return DOMAIN_STYLE[name] ?? DEFAULT_STYLE
}

// ─── Role card ────────────────────────────────────────────────────────────────

function RoleRow({ role, description }: { role: string; description: string }) {
  return (
    <div style={{
      display:       'flex',
      alignItems:    'flex-start',
      gap:           12,
      padding:       '8px 0',
      borderBottom:  '0.5px solid var(--color-border-tertiary)',
    }}>
      <code style={{
        fontSize:     11.5,
        fontFamily:   'var(--font-mono)',
        fontWeight:   600,
        color:        'var(--color-text-primary)',
        minWidth:     180,
        flexShrink:   0,
        paddingTop:   1,
      }}>
        {role}
      </code>
      <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
        {description}
      </span>
    </div>
  )
}

// ─── Domain pack card ─────────────────────────────────────────────────────────

function DomainCard({ pack, expanded, onToggle }: {
  pack:     DomainPack
  expanded: boolean
  onToggle: () => void
}) {
  const style = domainStyle(pack.name)
  const roles = Object.entries(pack.roles)

  return (
    <div style={{
      background:   'var(--color-background-primary)',
      border:       `0.5px solid var(--color-border-tertiary)`,
      borderRadius: 12,
      overflow:     'hidden',
    }}>
      {/* Header */}
      <button
        onClick={onToggle}
        style={{
          width:      '100%',
          background: 'none',
          border:     'none',
          cursor:     'pointer',
          padding:    '16px 18px',
          textAlign:  'left',
          display:    'flex',
          alignItems: 'flex-start',
          gap:        14,
        }}
      >
        {/* Domain color swatch */}
        <div style={{
          width:        40,
          height:       40,
          borderRadius: 8,
          background:   style.bg,
          border:       `1px solid ${style.border}`,
          flexShrink:   0,
          display:      'flex',
          alignItems:   'center',
          justifyContent:'center',
          fontSize:     14,
          fontWeight:   700,
          color:        style.color,
        }}>
          {pack.name.slice(0, 2).toUpperCase()}
        </div>

        {/* Title + meta */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)' }}>
              {pack.name}
            </span>
            <span style={{
              fontSize: 10.5, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase',
              padding: '1px 7px', borderRadius: 10,
              background: style.bg, color: style.color, border: `1px solid ${style.border}`,
            }}>
              {pack.role_count} roles
            </span>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.5, margin: 0, marginBottom: 6 }}>
            {pack.description}
          </p>
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
            {pack.tags.map(t => (
              <span key={t} style={{
                fontSize: 10.5, padding: '1px 7px', borderRadius: 10,
                background: 'var(--color-background-secondary)', color: 'var(--color-text-tertiary)',
                border: '0.5px solid var(--color-border-tertiary)',
              }}>
                {t}
              </span>
            ))}
          </div>
        </div>

        {/* Chevron */}
        <svg
          width="16" height="16" viewBox="0 0 16 16" fill="none"
          style={{ flexShrink: 0, marginTop: 2, transition: 'transform .2s ease', transform: expanded ? 'rotate(180deg)' : 'none', color: 'var(--color-text-tertiary)' }}
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* Role table — only shown when expanded */}
      {expanded && (
        <div style={{ padding: '0 18px 16px', borderTop: '0.5px solid var(--color-border-tertiary)' }}>
          <div style={{ marginTop: 12 }}>
            {roles.map(([role, description]) => (
              <RoleRow key={role} role={role} description={description} />
            ))}
          </div>

          {/* Usage example */}
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
              Usage example
            </div>
            <pre style={{
              padding: '10px 14px', borderRadius: 8, fontSize: 11.5,
              fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)',
              background: 'var(--color-background-secondary)', lineHeight: 1.65,
              overflowX: 'auto', margin: 0,
            }}>
{`from afmx.domains.${pack.name} import ${pack.name.charAt(0).toUpperCase() + pack.name.slice(1)}Domain

node = Node(
    name       = "my-agent",
    type       = NodeType.AGENT,
    handler    = "my_handler",
    cognitive_layer = "REASON",
    agent_role      = "${roles[0]?.[0] ?? 'ANALYST'}",
)`}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Cognitive layer reference ────────────────────────────────────────────────

const LAYERS = [
  { name: 'PERCEIVE',  desc: 'Ingest signals, alerts, documents, telemetry',  tier: 'cheap',   color: '#185FA5', bg: '#E6F1FB' },
  { name: 'RETRIEVE',  desc: 'Fetch knowledge, RAG, DB lookups, log retrieval', tier: 'cheap',  color: '#0F6E56', bg: '#E1F5EE' },
  { name: 'REASON',    desc: 'Analysis, correlation, synthesis',               tier: 'premium', color: '#534AB7', bg: '#EEEDFE' },
  { name: 'PLAN',      desc: 'Strategy, fix plans, runbooks',                  tier: 'premium', color: '#854F0B', bg: '#FAEEDA' },
  { name: 'ACT',       desc: 'Execute tools, APIs, deployments',               tier: 'cheap',   color: '#993C1D', bg: '#FAECE7' },
  { name: 'EVALUATE',  desc: 'Validate, test, audit, verify',                  tier: 'premium', color: '#3B6D11', bg: '#EAF3DE' },
  { name: 'REPORT',    desc: 'Summarise, escalate, alert',                     tier: 'cheap',   color: '#5F5E5A', bg: '#F1EFE8' },
]

function LayerReference() {
  return (
    <Card padding={0}>
      <CardHeader
        title="Cognitive layer reference"
        sub="The FIXED ROW axis — universal across every industry, never changes"
      />
      <div style={{ padding: '0 0 4px' }}>
        {LAYERS.map((l, i) => (
          <div
            key={l.name}
            style={{
              display:      'flex',
              alignItems:   'center',
              gap:          14,
              padding:      '10px 18px',
              borderBottom: i < LAYERS.length - 1 ? '0.5px solid var(--color-border-tertiary)' : 'none',
            }}
          >
            <div style={{
              width: 88, flexShrink: 0,
              display: 'flex', alignItems: 'center', gap: 7,
            }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: l.color,
              }} />
              <code style={{ fontSize: 11.5, fontWeight: 700, color: l.color, letterSpacing: '.03em' }}>
                {l.name}
              </code>
            </div>
            <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', flex: 1 }}>
              {l.desc}
            </span>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase',
              padding: '2px 7px', borderRadius: 10, flexShrink: 0,
              background: l.tier === 'premium' ? 'rgba(127,119,221,.15)' : 'rgba(34,197,94,.12)',
              color:      l.tier === 'premium' ? '#3C3489' : '#15803d',
              border:     `1px solid ${l.tier === 'premium' ? 'rgba(127,119,221,.35)' : 'rgba(34,197,94,.3)'}`,
            }}>
              {l.tier === 'premium' ? '★ premium' : '◇ cheap'} LLM
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DomainsPage() {
  const { data, isLoading, error } = useDomains()
  const [expanded, setExpanded] = useState<string | null>('tech')
  const [filter, setFilter]     = useState('')

  const packs: DomainPack[] = data?.domains ?? []
  const filtered = filter.trim()
    ? packs.filter(p =>
        p.name.includes(filter.toLowerCase()) ||
        p.description.toLowerCase().includes(filter.toLowerCase()) ||
        p.tags.some(t => t.includes(filter.toLowerCase())) ||
        Object.keys(p.roles).some(r => r.toLowerCase().includes(filter.toLowerCase()))
      )
    : packs

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── Header ── */}
      <Card padding={0}>
        <div style={{ padding: '16px 18px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 4 }}>
            Domain Packs — Agent Role Vocabulary
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', margin: 0, lineHeight: 1.6, maxWidth: 720 }}>
            The <strong>column axis</strong> of the Cognitive Matrix is open — any industry vocabulary is valid.
            Domain packs define role strings for specific industries.
            The <strong>row axis</strong> (CognitiveLayer) is fixed and universal across all domains.
          </p>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 16, alignItems: 'start' }}>

        {/* ── Domain packs list ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* Search */}
          <input
            type="search"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Search domains, roles, or tags…"
            style={{
              padding:      '8px 12px',
              border:       '0.5px solid var(--color-border-secondary)',
              borderRadius: 8,
              fontSize:     13,
              color:        'var(--color-text-primary)',
              background:   'var(--color-background-primary)',
              width:        '100%',
            }}
          />

          {isLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={80} />)}
            </div>
          )}

          {error && <ErrorState message={(error as Error).message} />}

          {!isLoading && filtered.length === 0 && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 13 }}>
              {filter ? `No domains match "${filter}"` : 'No domain packs registered'}
            </div>
          )}

          {filtered.map(pack => (
            <DomainCard
              key={pack.name}
              pack={pack}
              expanded={expanded === pack.name}
              onToggle={() => setExpanded(expanded === pack.name ? null : pack.name)}
            />
          ))}

          {/* Custom domain callout */}
          <div style={{
            padding:      '14px 16px',
            background:   'var(--color-background-secondary)',
            border:       '0.5px solid var(--color-border-tertiary)',
            borderRadius: 10,
            fontSize:     12.5,
            color:        'var(--color-text-secondary)',
            lineHeight:   1.6,
          }}>
            <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 6 }}>
              Registering a custom domain
            </div>
            <pre style={{
              margin: 0, padding: '10px 12px', borderRadius: 7, fontSize: 11.5,
              fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)',
              background: 'var(--color-background-primary)', overflowX: 'auto', lineHeight: 1.65,
            }}>
{`from afmx.domains import DomainPack, domain_registry

domain_registry.register(DomainPack(
    name        = "logistics",
    description = "Logistics and supply chain",
    roles = {
        "DISPATCHER": "Route assignment",
        "TRACKER":    "Shipment monitoring",
        "PLANNER":    "Demand forecasting",
    },
    tags = ["logistics", "supply-chain"],
))`}
            </pre>
          </div>
        </div>

        {/* ── Right column: layer reference + design axiom ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <LayerReference />

          {/* Design axiom */}
          <div style={{
            padding:    '14px 16px',
            background: '#EEEDFE',
            border:     '0.5px solid #AFA9EC',
            borderRadius: 10,
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#3C3489', marginBottom: 8 }}>
              The matrix design axiom
            </div>
            <div style={{ fontSize: 12, color: '#534AB7', lineHeight: 1.7 }}>
              <strong>Rows (CognitiveLayer)</strong> — what TYPE of thinking the node does.
              Fixed forever. Universal across every industry.
            </div>
            <div style={{ fontSize: 12, color: '#534AB7', lineHeight: 1.7, marginTop: 4 }}>
              <strong>Columns (AgentRole)</strong> — which DOMAIN role does the node belong to.
              Open string. Domain-specific. Change per industry without touching the engine.
            </div>
            <div style={{ fontSize: 11.5, color: '#7F77DD', marginTop: 10, lineHeight: 1.6, borderTop: '0.5px solid #AFA9EC', paddingTop: 10 }}>
              An OPS engineer at a fintech company and a RISK_MANAGER both run REASON-layer nodes.
              The cognitive layer determines <em>how</em> the LLM is selected.
              The role determines <em>who</em> is doing the thinking in that domain.
            </div>
          </div>

          {/* API reference */}
          <Card padding={0}>
            <CardHeader title="API endpoints" sub="Domain packs via REST" />
            <div style={{ padding: '0 16px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { method: 'GET', path: '/afmx/domains',       desc: 'List all domain packs' },
                { method: 'GET', path: '/afmx/domains/{name}',desc: 'Get a specific domain pack' },
                { method: 'GET', path: '/afmx/matrix-view/{id}', desc: 'Matrix view with role_meta' },
              ].map(({ method, path, desc }) => (
                <div key={path} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 5, flexShrink: 0,
                    background: 'rgba(59,130,246,.12)', color: '#1d4ed8',
                    border: '0.5px solid rgba(59,130,246,.3)',
                  }}>
                    {method}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <code style={{ fontSize: 11.5, fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)', display: 'block', marginBottom: 1 }}>
                      {path}
                    </code>
                    <span style={{ fontSize: 11.5, color: 'var(--color-text-tertiary)' }}>{desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
