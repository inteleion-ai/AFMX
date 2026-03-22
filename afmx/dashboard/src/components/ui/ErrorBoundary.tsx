import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props  { children: ReactNode; fallback?: ReactNode }
interface State  { hasError: boolean; error: Error | null }

/**
 * ErrorBoundary — catches uncaught render errors and shows a recovery UI
 * instead of a blank white screen. Required for production robustness.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <App />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // In production you could ship to a telemetry endpoint here.
    // For now, log to console.error (allowed by ESLint config).
    console.error('[AFMX ErrorBoundary]', error, info.componentStack)
  }

  reset = () => this.setState({ hasError: false, error: null })

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      this.props.fallback ?? (
        <div
          style={{
            height:         '100vh',
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'center',
            background:     'var(--bg-base)',
            color:          'var(--text-1)',
            fontFamily:     'var(--font)',
            flexDirection:  'column',
            gap:            16,
            padding:        24,
            textAlign:      'center',
          }}
        >
          {/* Logo mark */}
          <div
            style={{
              width:        40,
              height:       40,
              borderRadius: 10,
              background:   'linear-gradient(135deg, var(--brand) 0%, var(--purple) 100%)',
              display:      'flex',
              alignItems:   'center',
              justifyContent: 'center',
              fontSize:     15,
              fontWeight:   800,
              color:        '#fff',
              marginBottom: 8,
            }}
          >
            AX
          </div>

          <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-.3px' }}>
            Something went wrong
          </div>

          {this.state.error && (
            <pre
              style={{
                fontSize:     11,
                fontFamily:   'var(--mono)',
                color:        'var(--text-3)',
                background:   'var(--bg-surface)',
                border:       '1px solid var(--border)',
                borderRadius: 8,
                padding:      '10px 14px',
                maxWidth:     480,
                overflowX:    'auto',
                whiteSpace:   'pre-wrap',
                wordBreak:    'break-word',
                textAlign:    'left',
              }}
            >
              {this.state.error.message}
            </pre>
          )}

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={this.reset}
              style={{
                padding:      '7px 16px',
                borderRadius: 8,
                background:   'var(--brand)',
                color:        '#fff',
                border:       'none',
                fontSize:     13,
                fontWeight:   600,
                cursor:       'pointer',
              }}
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding:      '7px 16px',
                borderRadius: 8,
                background:   'var(--bg-elevated)',
                color:        'var(--text-1)',
                border:       '1px solid var(--border-med)',
                fontSize:     13,
                fontWeight:   500,
                cursor:       'pointer',
              }}
            >
              Reload page
            </button>
          </div>
        </div>
      )
    )
  }
}
