import { usePlugins } from '../hooks/useApi'
import { Card, CardHeader, Skeleton, ErrorState } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'

export default function Plugins() {
  const { data, isLoading, error } = usePlugins()

  if (error) return <ErrorState message={error.message} />

  const tools   = data?.tools   ?? []
  const agents  = data?.agents  ?? []
  const funcs   = data?.functions ?? []
  const all     = [...tools, ...agents, ...funcs]

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {[
          { label: 'Tools',     count: tools.length,  accent: 'var(--brand)'  },
          { label: 'Agents',    count: agents.length, accent: 'var(--green)'  },
          { label: 'Functions', count: funcs.length,  accent: 'var(--purple)' },
        ].map(c => (
          <div key={c.label} style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--r-xl)', padding: '18px 20px',
            borderLeft: `3px solid ${c.accent}`,
          }}>
            <div style={{ fontSize: 10.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>
              {c.label}
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, color: c.accent, fontFamily: 'var(--mono)', letterSpacing: '-2px' }}>
              {isLoading ? '—' : c.count}
            </div>
          </div>
        ))}
      </div>

      {/* Handler table */}
      <Card padding={0}>
        <CardHeader title="Handler Registry" sub={`${all.length} handlers registered`} />
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Handler Key</th>
                <th>Type</th>
                <th>Description</th>
                <th>Tags</th>
                <th>Version</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {[100, 70, 200, 120, 60, 60].map((w, j) => (
                      <td key={j}><Skeleton h={14} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : all.length === 0 ? (
                <tr><td colSpan={6}>
                  <div className="empty-state">
                    <p>No handlers registered — check startup_handlers.py</p>
                  </div>
                </td></tr>
              ) : all.map(p => (
                <tr key={p.key}>
                  <td>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--brand)' }}>{p.key}</span>
                  </td>
                  <td>
                    <Badge
                      variant={p.type === 'tool' ? 'brand' : p.type === 'agent' ? 'green' : 'purple'}
                    >
                      {p.type}
                    </Badge>
                  </td>
                  <td style={{ color: 'var(--text-2)', fontSize: 12, maxWidth: 300 }}>
                    {p.description || '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {p.tags.map(t => (
                        <span key={t} style={{
                          padding: '1px 6px', background: 'var(--bg-muted)',
                          color: 'var(--text-3)', borderRadius: 'var(--r-full)',
                          fontSize: 10.5, fontWeight: 600,
                        }}>
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.version}</span>
                  </td>
                  <td>
                    <Badge variant={p.enabled ? 'green' : 'red'}>{p.enabled ? 'Active' : 'Disabled'}</Badge>
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
