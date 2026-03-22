import { NavLink } from 'react-router-dom'
import { useHealth } from '../../hooks/useApi'
import { useTheme, useApiKeyStore } from '../../store'
import { fmtSec } from '../../utils/fmt'
import type { CSSProperties } from 'react'

/* ── Nav structure ── */
const NAV_GROUPS = [
  {
    label: 'Monitor',
    items: [
      { to: '/',           label: 'Overview',       Icon: IconGrid     },
      { to: '/executions', label: 'Executions',     Icon: IconList     },
      { to: '/stream',     label: 'Live Stream',    Icon: IconWave     },
    ],
  },
  {
    label: 'Build',
    items: [
      { to: '/run',      label: 'Run Matrix',     Icon: IconPlay     },
      { to: '/matrices', label: 'Saved Matrices', Icon: IconDocument },
      { to: '/plugins',  label: 'Plugins',        Icon: IconPlugin   },
    ],
  },
  {
    label: 'Governance',
    items: [
      { to: '/audit', label: 'Audit Log', Icon: IconAudit },
      { to: '/keys',  label: 'API Keys',  Icon: IconKey   },
    ],
  },
]

export default function Sidebar() {
  const { data: health } = useHealth()
  const { theme, toggle } = useTheme()
  const { apiKey, setApiKey } = useApiKeyStore()
  const alive = health?.status === 'healthy'

  return (
    <aside
      style={{
        width:         'var(--sidebar-w)',
        flexShrink:    0,
        background:    'var(--bg-surface)',
        borderRight:   '1px solid var(--border)',
        display:       'flex',
        flexDirection: 'column',
        height:        '100%',
        overflow:      'hidden',
      }}
    >
      {/* ── Logo ── */}
      <div
        style={{
          height:      'var(--topbar-h)',
          display:     'flex',
          alignItems:  'center',
          gap:         10,
          padding:     '0 16px',
          borderBottom:'1px solid var(--border)',
          flexShrink:  0,
        }}
      >
        <div
          style={{
            width:        30,
            height:       30,
            borderRadius: 'var(--r-md)',
            background:   'linear-gradient(135deg, var(--brand) 0%, var(--purple) 100%)',
            display:      'flex',
            alignItems:   'center',
            justifyContent: 'center',
            flexShrink:   0,
            fontSize:     12,
            fontWeight:   800,
            color:        '#fff',
            letterSpacing:'-.5px',
            boxShadow:    '0 0 0 1px rgba(255,255,255,.06)',
          }}
        >
          AX
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-.3px' }}>
            AFMX
          </div>
          <div style={{ fontSize: 9.5, color: 'var(--text-3)', letterSpacing: '.06em', textTransform: 'uppercase' }}>
            Execution Engine
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav style={{ flex: 1, padding: '8px 0', overflowY: 'auto' }}>
        {NAV_GROUPS.map(g => (
          <div key={g.label} style={{ marginBottom: 4 }}>
            <div
              style={{
                fontSize:      9.5,
                fontWeight:    700,
                color:         'var(--text-3)',
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                padding:       '8px 14px 6px',
              }}
            >
              {g.label}
            </div>
            {g.items.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                style={({ isActive }): CSSProperties => ({
                  display:        'flex',
                  alignItems:     'center',
                  gap:            9,
                  padding:        '7px 10px',
                  margin:         '1px 6px',
                  borderRadius:   'var(--r-md)',
                  fontSize:       13,
                  fontWeight:     500,
                  textDecoration: 'none',
                  transition:     'all var(--t-fast)',
                  color:          isActive ? 'var(--brand)' : 'var(--text-2)',
                  background:     isActive ? 'var(--brand-dim)' : 'transparent',
                })}
              >
                {({ isActive }) => (
                  <>
                    <Icon active={isActive} />
                    {label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* ── API key input ── */}
      <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
        <div
          style={{
            fontSize:      10,
            color:         'var(--text-3)',
            marginBottom:  5,
            textTransform: 'uppercase',
            letterSpacing: '.06em',
            fontWeight:    600,
          }}
        >
          API Key
        </div>
        <div style={{ position: 'relative' }}>
          <svg
            width="11" height="11" viewBox="0 0 11 11" fill="none"
            style={{
              position:  'absolute',
              left:      8,
              top:       '50%',
              transform: 'translateY(-50%)',
              color:     'var(--text-3)',
              pointerEvents: 'none',
            }}
          >
            <circle cx="4.5" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M6.5 5L9.5 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="8" y1="3.5" x2="9.5" y2="5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="Optional"
            aria-label="API Key"
            style={{
              width:        '100%',
              padding:      '6px 8px 6px 24px',
              background:   'var(--bg-muted)',
              border:       '1px solid var(--border-med)',
              borderRadius: 'var(--r-md)',
              fontSize:     11.5,
              color:        'var(--text-1)',
              outline:      'none',
              fontFamily:   'var(--mono)',
            }}
          />
        </div>
      </div>

      {/* ── Footer: health + theme toggle ── */}
      <div
        style={{
          padding:     '10px 14px',
          borderTop:   '1px solid var(--border)',
          display:     'flex',
          alignItems:  'center',
          gap:         8,
          flexShrink:  0,
        }}
      >
        <span
          style={{
            width:      7,
            height:     7,
            borderRadius: '50%',
            background: alive ? 'var(--green)' : 'var(--red)',
            flexShrink: 0,
            animation:  alive ? 'pulsering 2s infinite' : 'none',
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-2)' }}>
            {alive ? 'Engine online' : 'Unreachable'}
          </div>
          {health && (
            <div
              style={{
                fontSize:   10,
                color:      'var(--text-3)',
                fontFamily: 'var(--mono)',
                marginTop:  1,
                overflow:   'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              v{health.version} · up {fmtSec(health.uptime_seconds)}
            </div>
          )}
        </div>
        <button
          onClick={toggle}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          aria-label="Toggle colour theme"
          style={{
            width:        26,
            height:       26,
            display:      'flex',
            alignItems:   'center',
            justifyContent: 'center',
            borderRadius: 'var(--r-md)',
            color:        'var(--text-3)',
            transition:   'all var(--t-fast)',
            flexShrink:   0,
          }}
        >
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
        </button>
      </div>
    </aside>
  )
}

/* ── Icon components ── */
function IconGrid({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <rect x="1"   y="1"   width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="1"   width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="1"   y="8.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  )
}
function IconList({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <path d="M2 4h11M2 7.5h11M2 11h7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  )
}
function IconWave({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <path d="M1 7.5h2l2 5 3-10 2 5h2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}
function IconPlay({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <polygon points="3.5 2 12 7.5 3.5 13" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
    </svg>
  )
}
function IconDocument({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <rect x="2" y="1" width="11" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M5 5h5M5 7.5h5M5 10h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  )
}
function IconPlugin({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <path d="M8 1.5l2 4 4 .5-3 2.9.7 4L8 10.5l-3.7 2.4.7-4-3-2.9 4-.5z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
    </svg>
  )
}
function IconAudit({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <rect x="1.5" y="1.5" width="12" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M4.5 5h6M4.5 7.5h6M4.5 10h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  )
}
function IconKey({ active }: { active: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ opacity: active ? 1 : 0.65, color: active ? 'var(--brand)' : 'currentColor', flexShrink: 0 }}>
      <circle cx="5" cy="9" r="3" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M7.5 7L13 1.5M11 3.5l1.5 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  )
}
function IconSun() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M3 3l1 1M10 10l1 1M11 3l-1 1M4 10l-1 1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  )
}
function IconMoon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M12 8.5a5.5 5.5 0 1 1-7-7 4.5 4.5 0 0 0 7 7z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
    </svg>
  )
}
