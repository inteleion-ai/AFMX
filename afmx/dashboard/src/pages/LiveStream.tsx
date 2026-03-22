import { useState, useRef, useEffect } from 'react'
import { Card, CardHeader, ErrorState } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { format } from 'date-fns'
import type { StreamEvent } from '../types'

const EVENT_COLORS: Record<string, string> = {
  'execution.started':   'var(--brand)',
  'execution.completed': 'var(--green)',
  'execution.failed':    'var(--red)',
  'execution.aborted':   'var(--text-3)',
  'execution.timeout':   'var(--amber)',
  'node.started':        'var(--cyan)',
  'node.completed':      'var(--green)',
  'node.failed':         'var(--red)',
  'node.skipped':        'var(--text-3)',
  'node.retrying':       'var(--amber)',
  'node.fallback':       'var(--purple)',
  'circuit_breaker.open':   'var(--red)',
  'circuit_breaker.closed': 'var(--green)',
  'connected':           'var(--brand)',
  'eof':                 'var(--text-3)',
  'ping':                'var(--text-4)',
}

interface LogEntry { ts: string; type: string; data: string }

export default function LiveStream() {
  const [execId, setExecId]   = useState('')
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [status, setStatus]   = useState<'idle'|'connecting'|'live'|'done'|'error'>('idle')
  const [count, setCount]     = useState(0)
  const wsRef  = useRef<WebSocket | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  const STATUS_PILL: Record<typeof status, { label: string; color: string; bg: string }> = {
    idle:       { label: 'Not connected', color: 'var(--text-3)',  bg: 'var(--bg-muted)' },
    connecting: { label: 'Connecting…',   color: 'var(--amber)',   bg: 'var(--amber-dim)' },
    live:       { label: 'Streaming',     color: 'var(--green)',   bg: 'var(--green-dim)' },
    done:       { label: 'Complete',      color: 'var(--brand)',   bg: 'var(--brand-dim)' },
    error:      { label: 'Error',         color: 'var(--red)',     bg: 'var(--red-dim)' },
  }

  const connect = () => {
    if (!execId.trim()) return
    disconnect()
    setEntries([])
    setCount(0)
    setStatus('connecting')

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/afmx/ws/stream/${execId.trim()}`)
    wsRef.current = ws

    ws.onopen  = () => setStatus('live')
    ws.onclose = () => setStatus(s => s === 'live' ? 'done' : s)
    ws.onerror = () => setStatus('error')
    ws.onmessage = e => {
      let msg: StreamEvent
      try { msg = JSON.parse(e.data) } catch { return }
      if (msg.type === 'ping') return

      setCount(c => c + 1)
      const entry: LogEntry = {
        ts:   format(new Date(), 'HH:mm:ss.SSS'),
        type: msg.type,
        data: JSON.stringify(msg.data ?? {}),
      }
      setEntries(prev => [...prev.slice(-499), entry])
      if (msg.type === 'eof') setStatus('done')
    }
  }

  const disconnect = () => {
    wsRef.current?.close()
    wsRef.current = null
    setStatus('idle')
  }

  // Auto-scroll
  useEffect(() => {
    if (boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight
    }
  }, [entries])

  const pill = STATUS_PILL[status]

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          className="field-input mono"
          value={execId}
          onChange={e => setExecId(e.target.value)}
          placeholder="Execution ID…"
          style={{ width: 340 }}
          onKeyDown={e => e.key === 'Enter' && connect()}
        />
        <button
          onClick={connect}
          disabled={!execId.trim()}
          style={{
            padding: '7px 14px', borderRadius: 'var(--r-md)',
            background: 'var(--brand)', color: '#fff',
            border: 'none', fontSize: 13, fontWeight: 600,
            cursor: execId.trim() ? 'pointer' : 'not-allowed',
            opacity: execId.trim() ? 1 : .5,
            transition: 'opacity var(--t-fast)',
          }}
        >
          Connect
        </button>
        <button
          onClick={disconnect}
          style={{
            padding: '7px 14px', borderRadius: 'var(--r-md)',
            background: 'var(--bg-elevated)', color: 'var(--text-2)',
            border: '1px solid var(--border-med)', fontSize: 13, fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Disconnect
        </button>

        <div style={{ flex: 1 }} />

        <button
          onClick={() => setEntries([])}
          style={{ fontSize: 12, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Clear
        </button>

        {/* Status pill */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 10px', borderRadius: 'var(--r-full)',
          background: pill.bg, fontSize: 12, fontWeight: 600,
          color: pill.color,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: pill.color, flexShrink: 0,
            animation: status === 'live' ? 'pulsering 1.4s infinite' : 'none',
          }}/>
          {pill.label}
        </div>

        {count > 0 && (
          <span style={{ fontSize: 11.5, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
            {count} events
          </span>
        )}
      </div>

      {/* Log box */}
      <Card padding={0}>
        <div
          ref={boxRef}
          style={{
            height:     420,
            overflowY:  'auto',
            fontFamily: 'var(--mono)',
            fontSize:   11.5,
            lineHeight: 1,
            padding:    '6px 0',
          }}
        >
          {entries.length === 0 ? (
            <div className="empty-state" style={{ height: '100%' }}>
              <svg width="36" height="36" viewBox="0 0 36 36" fill="none" style={{ opacity: .2 }}>
                <path d="M3 18h5l4 11 6-22 4 11h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <p>Connect to an execution ID to watch events in real-time</p>
            </div>
          ) : entries.map((e, i) => (
            <div
              key={i}
              style={{
                display: 'grid',
                gridTemplateColumns: '90px 200px 1fr',
                gap: 12,
                padding: '3px 14px',
                transition: 'background var(--t-fast)',
              }}
            >
              <span style={{ color: 'var(--text-4)', fontSize: 10.5 }}>{e.ts}</span>
              <span style={{ color: EVENT_COLORS[e.type] ?? 'var(--text-2)', fontWeight: 600 }}>
                {e.type}
              </span>
              <span style={{ color: 'var(--text-3)', wordBreak: 'break-all' }}>
                {e.data}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
