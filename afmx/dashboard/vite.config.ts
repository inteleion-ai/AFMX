import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const API_TARGET = env.VITE_API_URL ?? 'http://localhost:8100'

  return {
    plugins: [react()],

    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },

    // CRITICAL: base must match the URL path where FastAPI serves the SPA.
    // FastAPI serves index.html at /afmx/ui and /afmx/ui/* — assets at /assets.
    // Setting base to '/' means all asset paths are absolute (e.g. /assets/index.js)
    // which FastAPI correctly handles via the /assets mount.
    base: '/',

    server: {
      host:  '0.0.0.0',
      port:  5173,
      proxy: {
        '/afmx':   { target: API_TARGET, changeOrigin: true },
        '/health': { target: API_TARGET, changeOrigin: true },
        '/metrics':{ target: API_TARGET, changeOrigin: true },
        '/docs':   { target: API_TARGET, changeOrigin: true },
        '/assets': { target: API_TARGET, changeOrigin: true },
      },
    },

    build: {
      // Output directly into afmx/static/ so FastAPI picks it up automatically
      outDir:    path.resolve(__dirname, '../static'),
      // Clean the output dir on each build to avoid stale chunks accumulating
      emptyOutDir: true,
      sourcemap:   false,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            query:  ['@tanstack/react-query'],
            charts: ['recharts'],
          },
        },
      },
    },
  }
})
