/// <reference types="vite/client" />

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_AFMX_URL?: string
  readonly MODE: string
  readonly DEV: boolean
  readonly PROD: boolean
}
