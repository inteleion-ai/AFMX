import type { ReactNode, CSSProperties } from 'react'

/* ── Card ── */
interface CardProps {
  children:  ReactNode
  padding?:  number | string
  style?:    CSSProperties
  className?: string
  onClick?:  () => void
}

export function Card({ children, padding = 16, style, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background:   'var(--bg-surface)',
        border:       '1px solid var(--border)',
        borderRadius: 'var(--r-xl)',
        overflow:     'hidden',
        transition:   'border-color var(--t-slow)',
        cursor:       onClick ? 'pointer' : undefined,
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── CardHeader ── */
export function CardHeader({
  title,
  sub,
  right,
}: {
  title:   ReactNode
  sub?:    ReactNode
  right?:  ReactNode
}) {
  return (
    <div
      style={{
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'space-between',
        padding:        '13px 16px',
        borderBottom:   '1px solid var(--border)',
        gap:            12,
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{title}</div>
        {sub && (
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{sub}</div>
        )}
      </div>
      {right && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{right}</div>}
    </div>
  )
}

/* ── StatCard ── */
interface StatCardProps {
  label:    string
  value:    ReactNode
  sub?:     string
  accent?:  string   // left-border colour
  icon?:    ReactNode
}

export function StatCard({ label, value, sub, accent = 'var(--brand)', icon }: StatCardProps) {
  return (
    <div
      style={{
        background:   'var(--bg-surface)',
        border:       '1px solid var(--border)',
        borderRadius: 'var(--r-xl)',
        padding:      '18px 20px',
        position:     'relative',
        overflow:     'hidden',
      }}
    >
      {/* left accent bar */}
      <div
        style={{
          position:     'absolute',
          top: 0, left: 0,
          width:        3, height: '100%',
          background:   accent,
          borderRadius: '3px 0 0 3px',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <div
          style={{
            fontSize:      10.5,
            fontWeight:    600,
            letterSpacing: '.05em',
            textTransform: 'uppercase',
            color:         'var(--text-3)',
          }}
        >
          {label}
        </div>
        {icon && <div style={{ color: accent, opacity: .75 }}>{icon}</div>}
      </div>
      <div
        style={{
          fontSize:      28,
          fontWeight:    800,
          letterSpacing: '-1.5px',
          lineHeight:    1,
          color:         'var(--text-1)',
          fontFamily:    'var(--mono)',
          marginBottom:  6,
        }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{sub}</div>
      )}
    </div>
  )
}

/* ── Skeleton ── */
export function Skeleton({ w = '100%', h = 16 }: { w?: string | number; h?: number }) {
  return (
    <div
      className="skeleton"
      style={{ width: w, height: h, borderRadius: 'var(--r-sm)' }}
    />
  )
}

/* ── ErrorState ── */
export function ErrorState({ message }: { message: string }) {
  return (
    <div
      style={{
        padding:      '16px 18px',
        borderRadius: 'var(--r-md)',
        background:   'var(--red-dim)',
        border:       '1px solid rgba(239,68,68,.25)',
        color:        'var(--red)',
        fontSize:     13,
        display:      'flex',
        alignItems:   'center',
        gap:          10,
      }}
    >
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
        <circle cx="7.5" cy="7.5" r="6.5" stroke="currentColor" strokeWidth="1.4"/>
        <path d="M7.5 5v3.5M7.5 10.5v.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      </svg>
      {message}
    </div>
  )
}

/* ── Divider ── */
export function Divider({ my = 16 }: { my?: number }) {
  return <div style={{ height: 1, background: 'var(--border)', margin: `${my}px 0` }} />
}
