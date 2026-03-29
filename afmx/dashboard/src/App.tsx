import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTheme } from './store'
import Shell         from './components/layout/Shell'
import Overview      from './pages/Overview'
import Executions    from './pages/Executions'
import LiveStream    from './pages/LiveStream'
import RunMatrix     from './pages/RunMatrix'
import Matrices      from './pages/Matrices'
import Plugins       from './pages/Plugins'
import Audit         from './pages/Audit'
import Keys          from './pages/Keys'
import MatrixView    from './pages/MatrixView'
import Domains       from './pages/Domains'
import ErrorBoundary from './components/ui/ErrorBoundary'

// ─── Router basename ─────────────────────────────────────────────────────────
// In production, FastAPI serves the SPA at /afmx/ui — all asset URLs and
// React Router links must be relative to that prefix.
// In development, Vite serves from the root, so basename must be "/" otherwise
// the router matches nothing and the page renders blank.
const BASENAME = import.meta.env.PROD ? '/afmx/ui' : '/'

// ─── TanStack Query client ────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry:                2,
      staleTime:            30_000,
      refetchOnWindowFocus: false,
    },
  },
})

// ─── Theme applier ────────────────────────────────────────────────────────────
// Keeps the <html> class in sync with Zustand state whenever the user toggles
// the theme. The initial class is already set synchronously in main.tsx.
function ThemeApplier() {
  const { theme } = useTheme()
  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('dark', 'light')
    root.classList.add(theme)
  }, [theme])
  return null
}

// ─── App root ─────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeApplier />
        <BrowserRouter basename={BASENAME}>
          <Routes>
            {/* Shell is the persistent layout route: sidebar + topbar + toasts */}
            <Route element={<Shell />}>
              <Route index             element={<Overview />}   />
              <Route path="executions" element={<Executions />} />
              <Route path="stream"     element={<LiveStream />} />
              <Route path="run"        element={<RunMatrix />}  />
              <Route path="matrices"   element={<Matrices />}   />
              <Route path="plugins"    element={<Plugins />}    />
              <Route path="audit"      element={<Audit />}      />
              <Route path="keys"       element={<Keys />}       />
              <Route path="matrix"     element={<MatrixView />} />
              <Route path="domains"    element={<Domains />}    />
              {/* Catch-all: unknown paths fall back to overview */}
              <Route path="*"          element={<Overview />}   />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
