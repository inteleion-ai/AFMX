import { useToastStore, type ToastType } from '../../store'

const ICONS: Record<ToastType, string> = {
  success: '✓', error: '✕', info: 'ℹ', warn: '⚠',
}

const COLORS: Record<ToastType, { border: string; icon: string }> = {
  success: { border: 'var(--green)',  icon: 'var(--green)'  },
  error:   { border: 'var(--red)',    icon: 'var(--red)'    },
  info:    { border: 'var(--brand)',  icon: 'var(--brand)'  },
  warn:    { border: 'var(--amber)',  icon: 'var(--amber)'  },
}

export function ToastContainer() {
  const { toasts, dismiss } = useToastStore()

  return (
    <div
      style={{
        position: 'fixed', bottom: 20, right: 20,
        zIndex:   9999,
        display:  'flex', flexDirection: 'column', gap: 8,
        pointerEvents: 'none',
      }}
    >
      {toasts.map(t => {
        const c = COLORS[t.type]
        return (
          <div
            key={t.id}
            onClick={() => dismiss(t.id)}
            style={{
              display:      'flex',
              alignItems:   'center',
              gap:          10,
              padding:      '10px 14px',
              background:   'var(--bg-elevated)',
              border:       '1px solid var(--border-med)',
              borderLeft:   `3px solid ${c.border}`,
              borderRadius: 'var(--r-lg)',
              boxShadow:    'var(--shadow-lg)',
              fontSize:     13,
              fontWeight:   500,
              color:        'var(--text-1)',
              minWidth:     260,
              maxWidth:     380,
              cursor:       'pointer',
              pointerEvents: 'auto',
              animation:    'slideIn .2s ease',
            }}
          >
            <span style={{ color: c.icon, fontSize: 14, flexShrink: 0 }}>
              {ICONS[t.type]}
            </span>
            {t.message}
          </div>
        )
      })}
    </div>
  )
}
