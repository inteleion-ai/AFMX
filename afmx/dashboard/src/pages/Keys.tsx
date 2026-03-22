import { useState } from 'react'
import { useApiKeys, useAdminStats, useCreateKeyMutation, useRevokeKeyMutation } from '../hooks/useApi'
import { Card, CardHeader, StatCard, Skeleton, ErrorState } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Modal, KeyReveal } from '../components/ui/Modal'
import { fmtDate, fmtRelative, truncate } from '../utils/fmt'
import type { ApiKey } from '../types'

const ROLES = ['VIEWER', 'SERVICE', 'DEVELOPER', 'OPERATOR', 'ADMIN'] as const
type Role = typeof ROLES[number]

function roleBadge(role: string) {
  const variant =
    role === 'ADMIN'     ? 'red'   :
    role === 'OPERATOR'  ? 'amber' :
    role === 'DEVELOPER' ? 'brand' :
    role === 'SERVICE'   ? 'green' : 'muted'
  return <Badge variant={variant}>{role}</Badge>
}

/* ── Create key form ── */
interface CreateKeyFormValues {
  name:        string
  role:        Role
  tenant_id:   string
  description: string
  expires_in_days: string
}

function CreateKeyModal({
  open, onClose,
}: { open: boolean; onClose: () => void }) {
  const createMut = useCreateKeyMutation()
  const [form, setForm] = useState<CreateKeyFormValues>({
    name: '', role: 'DEVELOPER', tenant_id: 'default',
    description: '', expires_in_days: '',
  })
  const [newKey, setNewKey] = useState('')
  const [err, setErr]       = useState('')

  const set = (k: keyof CreateKeyFormValues) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async () => {
    setErr('')
    if (!form.name.trim()) { setErr('Name is required'); return }
    const body = {
      name:        form.name.trim(),
      role:        form.role,
      tenant_id:   form.tenant_id.trim() || 'default',
      description: form.description.trim(),
      expires_in_days: form.expires_in_days ? Number(form.expires_in_days) : undefined,
    }
    try {
      const r = await createMut.mutateAsync(body) as ApiKey & { message: string }
      setNewKey(r.key)
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  const handleClose = () => {
    setForm({ name: '', role: 'DEVELOPER', tenant_id: 'default', description: '', expires_in_days: '' })
    setNewKey('')
    setErr('')
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Create API Key"
      subtitle="Keys are shown once — copy immediately after creation"
      footer={
        !newKey ? (
          <>
            <Button variant="primary" onClick={submit} loading={createMut.isPending}>
              Create Key
            </Button>
            <Button variant="ghost" onClick={handleClose}>Cancel</Button>
          </>
        ) : (
          <Button variant="primary" onClick={handleClose}>Done</Button>
        )
      }
    >
      {err && (
        <div style={{
          padding: '9px 13px', background: 'var(--red-dim)',
          border: '1px solid rgba(239,68,68,.25)', borderRadius: 'var(--r-md)',
          color: 'var(--red)', fontSize: 12.5, marginBottom: 14,
        }}>
          {err}
        </div>
      )}

      {newKey ? (
        <KeyReveal value={newKey} />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                Name <span style={{ color: 'var(--red)' }}>*</span>
              </label>
              <input
                className="field-input"
                value={form.name}
                onChange={set('name')}
                placeholder="e.g. ci-pipeline"
                autoFocus
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                Role
              </label>
              <select className="field-input" value={form.role} onChange={set('role')}>
                <option value="VIEWER">VIEWER — read only</option>
                <option value="SERVICE">SERVICE — execute + read</option>
                <option value="DEVELOPER">DEVELOPER — full execution</option>
                <option value="OPERATOR">OPERATOR — execution + matrices</option>
                <option value="ADMIN">ADMIN — all permissions</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                Tenant ID
              </label>
              <input className="field-input" value={form.tenant_id} onChange={set('tenant_id')} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                Expires In Days
                <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>
                  (blank = never)
                </span>
              </label>
              <input
                className="field-input"
                type="number"
                min={1}
                value={form.expires_in_days}
                onChange={set('expires_in_days')}
                placeholder="e.g. 90"
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
              Description
            </label>
            <input
              className="field-input"
              value={form.description}
              onChange={set('description')}
              placeholder="What is this key for?"
            />
          </div>
        </>
      )}
    </Modal>
  )
}

/* ── Page ── */
export default function Keys() {
  const { data, isLoading, error } = useApiKeys()
  const { data: stats }            = useAdminStats()
  const revokeMut = useRevokeKeyMutation()
  const [creating, setCreating]    = useState(false)

  if (error && error.message.includes('401')) {
    return (
      <div className="fade-up">
        <div style={{
          padding: '16px 18px', borderRadius: 'var(--r-md)',
          background: 'var(--amber-dim)', border: '1px solid rgba(245,158,11,.3)',
          color: 'var(--amber)', fontSize: 13, marginBottom: 16,
        }}>
          RBAC is enabled — enter an ADMIN API key in the sidebar to manage keys
        </div>
      </div>
    )
  }

  if (error) return <ErrorState message={error.message} />

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Stats row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <StatCard label="API Keys"         value={stats.api_keys}    accent="var(--brand)" />
          <StatCard label="Audit Events"     value={stats.audit_events} accent="var(--green)" />
          <StatCard label="Executions"       value={stats.executions_in_store} accent="var(--amber)" />
          <StatCard label="Handlers"         value={stats.handlers}    accent="var(--purple)" />
        </div>
      )}

      {/* Header actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Button
          variant="primary"
          onClick={() => setCreating(true)}
          icon={
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <line x1="6" y1="2" x2="6" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <line x1="2" y1="6" x2="10" y2="6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        >
          Create Key
        </Button>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
          {data ? `${data.count} key${data.count !== 1 ? 's' : ''}` : ''}
        </span>

        {/* Role legend */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {ROLES.map(r => roleBadge(r))}
        </div>
      </div>

      {/* Keys table */}
      <Card padding={0}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Tenant</th>
                <th>Key Preview</th>
                <th>Created</th>
                <th>Last Used</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {[120, 80, 80, 140, 110, 110, 60, 60].map((w, j) => (
                      <td key={j}><Skeleton h={13} w={w} /></td>
                    ))}
                  </tr>
                ))
              ) : (data?.keys ?? []).length === 0 ? (
                <tr><td colSpan={8}>
                  <div className="empty-state">
                    <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                      <circle cx="14" cy="22" r="7" stroke="currentColor" strokeWidth="1.5"/>
                      <path d="M20 16L33 3M29 7l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                    <p>No API keys — create one to get started</p>
                  </div>
                </td></tr>
              ) : data!.keys.map(k => (
                <tr key={k.id}>
                  <td>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>{k.name}</div>
                      {k.description && (
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                          {truncate(k.description, 40)}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>{roleBadge(k.role)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-2)' }}>{k.tenant_id}</td>
                  <td>
                    <span
                      className="mono"
                      style={{
                        fontSize: 11, color: 'var(--text-2)',
                        background: 'var(--bg-muted)',
                        padding: '2px 7px', borderRadius: 'var(--r-sm)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {k.key}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {fmtDate(k.created_at)}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {k.last_used_at
                      ? fmtRelative(k.last_used_at)
                      : <span style={{ color: 'var(--text-4)' }}>Never</span>
                    }
                  </td>
                  <td>
                    <Badge variant={k.active ? 'green' : 'red'}>
                      {k.active ? 'Active' : 'Revoked'}
                    </Badge>
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    {k.active && (
                      <Button
                        size="xs"
                        variant="danger"
                        loading={revokeMut.isPending}
                        onClick={() => {
                          if (confirm(`Revoke key '${k.name}'?\n\nThis immediately blocks all API calls using this key.`)) {
                            revokeMut.mutate(k.id)
                          }
                        }}
                      >
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Permissions reference */}
      <Card padding={0}>
        <CardHeader title="Role Permissions" sub="What each role can do" />
        <div style={{ padding: 16, display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
          {[
            { role: 'VIEWER',    color: 'var(--text-3)', perms: ['execution:read','matrix:read','plugin:read','adapter:read','metrics:read','audit:read'] },
            { role: 'SERVICE',   color: 'var(--green)',  perms: ['execution:execute','execution:read','matrix:read','matrix:execute'] },
            { role: 'DEVELOPER', color: 'var(--brand)',  perms: ['execution:execute','execution:read','execution:cancel','execution:retry','execution:resume','matrix:read','plugin:read','metrics:read'] },
            { role: 'OPERATOR',  color: 'var(--amber)',  perms: ['All DEVELOPER +','matrix:write','matrix:delete','audit:read','audit:export'] },
            { role: 'ADMIN',     color: 'var(--red)',    perms: ['All OPERATOR +','admin:read','admin:write'] },
          ].map(r => (
            <div key={r.role}>
              <div style={{ fontSize: 11.5, fontWeight: 700, color: r.color, marginBottom: 8 }}>
                {r.role}
              </div>
              {r.perms.map(p => (
                <div key={p} style={{
                  fontSize: 10.5, color: 'var(--text-3)',
                  fontFamily: 'var(--mono)', marginBottom: 3,
                  paddingLeft: 8,
                  borderLeft: `2px solid ${r.color}44`,
                }}>
                  {p}
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>

      <CreateKeyModal open={creating} onClose={() => setCreating(false)} />
    </div>
  )
}
