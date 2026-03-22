import { useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import { IconButton } from '../ui/Button'

const META: Record<string, { title: string; subtitle: string }> = {
  '/':           { title: 'Overview',       subtitle: 'Engine health · concurrency · execution activity' },
  '/executions': { title: 'Executions',     subtitle: 'History with node-level trace and retry controls' },
  '/stream':     { title: 'Live Stream',    subtitle: 'Real-time WebSocket execution event feed' },
  '/run':        { title: 'Run Matrix',     subtitle: 'Execute a matrix definition — sync or async' },
  '/matrices':   { title: 'Saved Matrices', subtitle: 'Server-side matrix store' },
  '/plugins':    { title: 'Plugins',        subtitle: 'Registered handlers — tools, agents, functions' },
  '/audit':      { title: 'Audit Log',      subtitle: 'Every operation with full provenance' },
  '/keys':       { title: 'API Keys',       subtitle: 'RBAC key management — 5 roles · 16 permissions' },
}

export default function TopBar() {
  const { pathname } = useLocation()
  const meta = META[pathname] ?? { title: 'AFMX', subtitle: '' }
  const qc   = useQueryClient()
  const [spinning, setSpinning] = useState(false)

  const refresh = useCallback(() => {
    setSpinning(true)
    qc.invalidateQueries()
    setTimeout(() => setSpinning(false), 700)
  }, [qc])

  return (
    <header
      style={{
        height:      'var(--topbar-h)',
        background:  'var(--bg-surface)',
        borderBottom:'1px solid var(--border)',
        display:     'flex',
        alignItems:  'center',
        padding:     '0 20px',
        gap:         12,
        flexShrink:  0,
      }}
    >
      {/* Page title */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-1)', letterSpacing: '-.2px' }}>
          {meta.title}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1 }}>
          {meta.subtitle}
        </div>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Refresh */}
      <IconButton onClick={refresh} label="Refresh (R)" size={30}>
        <svg
          width="14" height="14" viewBox="0 0 14 14" fill="none"
          style={{ animation: spinning ? 'spin .7s linear infinite' : 'none' }}
        >
          <path d="M13 7a6 6 0 1 1-6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          <polyline points="9 1 13 1 13 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </IconButton>

      {/* Docs link */}
      <a
        href="/docs"
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display:     'flex',
          alignItems:  'center',
          gap:         5,
          padding:     '5px 10px',
          borderRadius:'var(--r-md)',
          fontSize:    12,
          fontWeight:  500,
          color:       'var(--text-2)',
          textDecoration: 'none',
          border:      '1px solid transparent',
          transition:  'all var(--t-fast)',
        }}
      >
        API Docs
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M1.5 8.5l7-7M5 1.5h3v3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </a>
    </header>
  )
}
