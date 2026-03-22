import type { ReactNode, CSSProperties, ButtonHTMLAttributes } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize    = 'xs' | 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:   ButtonVariant
  size?:      ButtonSize
  loading?:   boolean
  icon?:      ReactNode
  iconRight?: ReactNode
}

const VARIANT_STYLES: Record<ButtonVariant, CSSProperties> = {
  primary: {
    background:  'var(--brand)',
    color:       '#fff',
    border:      '1px solid var(--brand)',
  },
  secondary: {
    background:  'var(--bg-elevated)',
    color:       'var(--text-1)',
    border:      '1px solid var(--border-med)',
  },
  ghost: {
    background:  'transparent',
    color:       'var(--text-2)',
    border:      '1px solid transparent',
  },
  danger: {
    background:  'transparent',
    color:       'var(--red)',
    border:      '1px solid var(--red-ring)',
  },
}

const SIZE_STYLES: Record<ButtonSize, CSSProperties> = {
  xs: { padding: '3px 8px',  fontSize: 11, gap: 4 },
  sm: { padding: '5px 10px', fontSize: 12, gap: 5 },
  md: { padding: '7px 14px', fontSize: 13, gap: 6 },
}

export function Button({
  variant  = 'secondary',
  size     = 'sm',
  loading  = false,
  icon,
  iconRight,
  children,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const v = VARIANT_STYLES[variant]
  const s = SIZE_STYLES[size]

  return (
    <button
      disabled={disabled || loading}
      style={{
        display:        'inline-flex',
        alignItems:     'center',
        justifyContent: 'center',
        borderRadius:   'var(--r-md)',
        fontWeight:     600,
        lineHeight:     1,
        whiteSpace:     'nowrap',
        transition:     'opacity var(--t-fast), background var(--t-fast)',
        cursor:         disabled || loading ? 'not-allowed' : 'pointer',
        opacity:        disabled || loading ? 0.55 : 1,
        ...v,
        ...s,
        ...style,
      }}
      {...rest}
    >
      {loading ? (
        <span
          style={{
            width:            12,
            height:           12,
            borderRadius:     '50%',
            border:           '1.5px solid currentColor',
            borderTopColor:   'transparent',
            animation:        'spin .7s linear infinite',
            display:          'inline-block',
            flexShrink:       0,
          }}
        />
      ) : icon}
      {children}
      {iconRight}
    </button>
  )
}

/* ── Icon-only button ── */
interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  size?:  number
  label?: string
}

export function IconButton({ size = 28, label, children, style, ...rest }: IconButtonProps) {
  return (
    <button
      title={label}
      aria-label={label}
      style={{
        width:        size,
        height:       size,
        display:      'flex',
        alignItems:   'center',
        justifyContent: 'center',
        borderRadius: 'var(--r-md)',
        color:        'var(--text-2)',
        transition:   'all var(--t-fast)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}
