import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// ─── Apply saved theme synchronously BEFORE first React paint ────────────────
// Without this, the first render has no .dark/.light class on <html>, so all
// CSS custom properties are undefined → black/transparent screen for one frame.
//
// We read directly from localStorage (same key Zustand persist uses) so this
// runs before any React component mounts.
;(function applyInitialTheme() {
  try {
    const stored = localStorage.getItem('afmx-theme')
    const parsed = stored ? (JSON.parse(stored) as { state?: { theme?: string } }) : null
    const theme  = parsed?.state?.theme ?? 'dark'
    document.documentElement.classList.add(theme === 'light' ? 'light' : 'dark')
  } catch {
    // If localStorage is unavailable or JSON is corrupt, fall back to dark.
    document.documentElement.classList.add('dark')
  }
})()

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('[AFMX] Missing #root element in index.html')

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
