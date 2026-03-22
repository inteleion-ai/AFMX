import { useEffect, useRef, type ReactNode } from 'react'

interface ModalProps {
  open:      boolean
  onClose:   () => void
  title:     string
  subtitle?: string
  children:  ReactNode
  footer?:   ReactNode
  maxWidth?: number
}

export function Modal({
  open, onClose, title, subtitle, children, footer, maxWidth = 560,
}: ModalProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      style={{
        position:   'fixed', inset: 0,
        background: 'rgba(0,0,0,.65)',
        backdropFilter: 'blur(6px)',
        zIndex:     500,
        display:    'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding:    20,
        animation:  'fadeUp .15s ease',
      }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={ref}
        style={{
          background:   'var(--bg-elevated)',
          border:       '1px solid var(--border-med)',
          borderRadius: 'var(--r-2xl)',
          boxShadow:    'var(--shadow-xl)',
          width:        '100%',
          maxWidth,
          maxHeight:    '92vh',
          overflowY:    'auto',
          animation:    'fadeUp .15s ease',
        }}
      >
        {/* Header */}
        <div
          style={{
            display:    'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            padding:    '22px 24px 0',
          }}
        >
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-.3px' }}>
              {title}
            </div>
            {subtitle && (
              <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 3 }}>{subtitle}</div>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              color: 'var(--text-3)', padding: 4,
              borderRadius: 'var(--r-sm)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all var(--t-fast)', marginTop: -2,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '18px 24px' }}>
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div
            style={{
              display:     'flex',
              alignItems:  'center',
              gap:         8,
              padding:     '14px 24px 20px',
              borderTop:   '1px solid var(--border)',
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── KeyReveal ── */
export function KeyReveal({ value }: { value: string }) {
  return (
    <div
      style={{
        padding:      '12px 14px',
        background:   'var(--green-dim)',
        border:       '1px solid rgba(34,197,94,.25)',
        borderRadius: 'var(--r-md)',
        marginTop:    12,
      }}
    >
      <div
        style={{
          fontSize:      10.5, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '.06em',
          color:         'var(--green)', marginBottom: 6,
        }}
      >
        ⚡ Key created — copy now, shown once only
      </div>
      <div
        style={{
          fontFamily:  'var(--mono)',
          fontSize:    12,
          color:       'var(--green)',
          wordBreak:   'break-all',
          userSelect:  'all',
          cursor:      'text',
        }}
      >
        {value}
      </div>
    </div>
  )
}
