import { useState } from 'react'
import { useMatrices, useDeleteMatrixMutation } from '../hooks/useApi'
import { Card, CardHeader, Skeleton, ErrorState } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { api } from '../api'
import { useApiKeyStore, toast } from '../store'
import { fmtDate } from '../utils/fmt'

export default function Matrices() {
  const { data, isLoading, error } = useMatrices()
  const deleteMut = useDeleteMatrixMutation()
  const apiKey = useApiKeyStore(s => s.apiKey) || undefined
  const [runningName, setRunningName] = useState<string | null>(null)

  const runMatrix = async (name: string) => {
    setRunningName(name)
    try {
      const r = await api.executeMatrix(name, apiKey)
      toast.success(`${name} → ${r.status} ${r.duration_ms != null ? `(${r.duration_ms.toFixed(0)}ms)` : ''}`)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setRunningName(null)
    }
  }

  if (error) return <ErrorState message={error.message} />

  return (
    <div className="fade-up">
      <Card padding={0}>
        <CardHeader
          title="Saved Matrices"
          sub="Named, versioned matrix definitions stored server-side"
        />
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Description</th>
                <th>Tags</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {[120, 60, 180, 100, 100, 100].map((w, j) => (
                      <td key={j}><Skeleton h={14} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : (data?.matrices ?? []).length === 0 ? (
                <tr><td colSpan={6}>
                  <div className="empty-state">
                    <p>No saved matrices — post to /afmx/matrices to save one</p>
                  </div>
                </td></tr>
              ) : data!.matrices.map(m => (
                <tr key={m.name}>
                  <td>
                    <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>
                      {m.name}
                    </span>
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>
                      {m.version}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-2)', fontSize: 12, maxWidth: 240 }}>
                    {m.description || '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {m.tags.map(t => (
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
                  <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                    {fmtDate(m.created_at)}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Button
                        size="xs"
                        variant="secondary"
                        loading={runningName === m.name}
                        onClick={() => runMatrix(m.name)}
                      >
                        ▶ Run
                      </Button>
                      <Button
                        size="xs"
                        variant="danger"
                        loading={deleteMut.isPending}
                        onClick={() => {
                          if (confirm(`Delete '${m.name}'?`)) deleteMut.mutate(m.name)
                        }}
                      >
                        Delete
                      </Button>
                    </div>
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
