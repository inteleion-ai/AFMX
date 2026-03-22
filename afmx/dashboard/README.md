# AFMX Dashboard

Production-grade React SPA for the AFMX Agent Flow Matrix Execution Engine.

## Stack

| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript 5 (strict) |
| Routing | React Router v6 (layout routes) |
| Data fetching | TanStack Query v5 |
| Charts | Recharts |
| State | Zustand (persisted) |
| Build | Vite 5 |
| Lint | ESLint 8 + typescript-eslint |

## Pages

| Route | Description |
|---|---|
| `/afmx/ui` | Overview — KPIs, timeline chart, engine status, Agentability |
| `/afmx/ui/executions` | Execution list with Trace / Waterfall / Output modal |
| `/afmx/ui/stream` | Real-time WebSocket event log |
| `/afmx/ui/run` | Matrix editor — sync, async, validate |
| `/afmx/ui/matrices` | Saved matrix store — run or delete |
| `/afmx/ui/plugins` | Handler registry |
| `/afmx/ui/audit` | Audit log with JSON/CSV/NDJSON export |
| `/afmx/ui/keys` | API key management — create, revoke, permissions |

## Development

```bash
cd afmx/dashboard
npm install
npm run dev          # starts on http://localhost:5173
                     # proxies /afmx and /health to localhost:8100
```

## Production build

```bash
npm run build        # outputs to ../static/ (afmx/static/)
                     # FastAPI serves it automatically at /afmx/ui
```

## Type check + lint

```bash
npm run type-check   # tsc --noEmit
npm run lint         # ESLint with max-warnings 0
npm run build        # runs type-check then vite build
```

## Environment variables

See `.env.example` — copy to `.env` and adjust.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8100` | Backend target for dev proxy |
