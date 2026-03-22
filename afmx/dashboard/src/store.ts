import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/* ─── Theme ─────────────────────────────────────────────── */
interface ThemeStore {
  theme: 'dark' | 'light'
  toggle:   () => void
  setTheme: (t: 'dark' | 'light') => void   // renamed: was `set` — shadowed Zustand's setState
}

export const useTheme = create<ThemeStore>()(
  persist(
    (setState) => ({
      theme:    'dark',
      toggle:   () => setState(s => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
      setTheme: (theme) => setState({ theme }),
    }),
    { name: 'afmx-theme' }
  )
)

/* ─── API Key ────────────────────────────────────────────── */
interface ApiKeyStore {
  apiKey:    string
  setApiKey: (k: string) => void
}

export const useApiKeyStore = create<ApiKeyStore>()(
  persist(
    (setState) => ({
      apiKey:    '',
      setApiKey: (apiKey) => setState({ apiKey }),
    }),
    { name: 'afmx-apikey' }
  )
)

/* ─── Toasts ─────────────────────────────────────────────── */
export type ToastType = 'success' | 'error' | 'info' | 'warn'

export interface Toast {
  id:      string
  type:    ToastType
  message: string
}

interface ToastStore {
  toasts:  Toast[]
  push:    (type: ToastType, message: string) => void
  dismiss: (id: string) => void
}

let _toastId = 0

export const useToastStore = create<ToastStore>((setState) => ({
  toasts: [],
  push: (type, message) => {
    const id = String(++_toastId)
    setState(s => ({ toasts: [...s.toasts, { id, type, message }] }))
    setTimeout(
      () => setState(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
      4000,
    )
  },
  dismiss: (id) => setState(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))

/* ── Convenience helpers — call outside React components ── */
export const toast = {
  success: (m: string) => useToastStore.getState().push('success', m),
  error:   (m: string) => useToastStore.getState().push('error',   m),
  info:    (m: string) => useToastStore.getState().push('info',    m),
  warn:    (m: string) => useToastStore.getState().push('warn',    m),
}
