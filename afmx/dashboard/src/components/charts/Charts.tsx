import {
  ResponsiveContainer, BarChart, Bar,
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { format } from 'date-fns'
import { TOOLTIP_STYLE, AXIS_TICK, GRID, fmtMs } from '../../utils/fmt'

/* ── Shared tick formatter ── */
const tickTs = (v: number) => format(new Date(v), 'HH:mm')

/* ── ExecutionTimeline — stacked bar: completed vs failed per bucket ── */
interface TimelineBucket { bucket: number; completed: number; failed: number }

export function ExecutionTimeline({
  data, height = 160,
}: { data: TimelineBucket[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }} barGap={1}>
        <CartesianGrid {...GRID} />
        <XAxis
          dataKey="bucket"
          tickFormatter={tickTs}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
        />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(v: number) => format(new Date(v), 'MMM d HH:mm')}
        />
        <Bar dataKey="completed" stackId="s" fill="var(--green)" radius={[0,0,0,0]} name="Completed" />
        <Bar dataKey="failed"    stackId="s" fill="var(--red)"   radius={[3,3,0,0]} name="Failed"    />
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── SuccessRateArea ── */
interface SrPoint { ts: number; rate: number }

export function SuccessRateArea({
  data, height = 140,
}: { data: SrPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
        <defs>
          <linearGradient id="srGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="var(--green)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--green)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" tickFormatter={tickTs} tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          domain={[0, 1]}
          tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'Success rate']}
          labelFormatter={(v: number) => format(new Date(v), 'HH:mm')}
        />
        <Area
          type="monotone"
          dataKey="rate"
          stroke="var(--green)"
          strokeWidth={2}
          fill="url(#srGrad)"
          dot={false}
          activeDot={{ r: 4, fill: 'var(--green)' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── DurationLine — p50 (solid) + p95 (dashed) ── */
interface DurPoint { ts: number; p50: number; p95: number }

export function DurationLine({
  data, height = 140,
}: { data: DurPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" tickFormatter={tickTs} tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tickFormatter={(v: number) => fmtMs(v)}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number, name: string) => [
            fmtMs(v),
            name === 'p50' ? 'p50 (median)' : 'p95',
          ]}
          labelFormatter={(v: number) => format(new Date(v), 'HH:mm')}
        />
        <Line
          type="monotone"
          dataKey="p50"
          stroke="var(--brand)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: 'var(--brand)' }}
        />
        <Line
          type="monotone"
          dataKey="p95"
          stroke="var(--amber)"
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ── Waterfall — per-node Gantt timing ── */
interface WaterfallRow {
  name:       string
  startPct:   number
  widthPct:   number
  color:      string
  durationMs: number | null
}

export function Waterfall({ rows }: { rows: WaterfallRow[] }) {
  if (!rows.length) {
    return (
      <div className="empty-state" style={{ padding: '32px 0' }}>
        <p>No timing data — node timestamps not recorded for this execution</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {rows.map((r, i) => (
        <div
          key={i}
          style={{
            display:             'grid',
            gridTemplateColumns: '140px 1fr 64px',
            alignItems:          'center',
            gap:                 10,
            padding:             '5px 0',
            borderBottom:        i < rows.length - 1 ? '1px solid var(--border-light)' : 'none',
          }}
        >
          {/* Node name */}
          <div
            title={r.name}
            style={{
              fontSize:     11.5,
              color:        'var(--text-2)',
              overflow:     'hidden',
              textOverflow: 'ellipsis',
              whiteSpace:   'nowrap',
              fontFamily:   'var(--mono)',
            }}
          >
            {r.name}
          </div>

          {/* Bar track */}
          <div
            style={{
              position:     'relative',
              height:       16,
              background:   'var(--bg-muted)',
              borderRadius: 3,
              overflow:     'hidden',
            }}
          >
            <div
              style={{
                position:     'absolute',
                left:         `${r.startPct}%`,
                width:        `${Math.max(r.widthPct, 0.5)}%`,
                height:       '100%',
                background:   r.color,
                borderRadius: 3,
                minWidth:     4,
                opacity:      0.88,
              }}
            />
          </div>

          {/* Duration label */}
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize:   10.5,
              color:      'var(--text-3)',
              textAlign:  'right',
            }}
          >
            {r.durationMs != null ? fmtMs(r.durationMs) : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── MiniBar — inline progress sparkbar for table cells ── */
export function MiniBar({
  value,
  max,
  color = 'var(--brand)',
}: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div
      style={{
        width:        64,
        height:       4,
        background:   'var(--border-med)',
        borderRadius: 99,
        overflow:     'hidden',
      }}
    >
      <div
        style={{
          width:        `${pct}%`,
          height:       '100%',
          background:   color,
          borderRadius: 99,
          transition:   'width .4s ease',
        }}
      />
    </div>
  )
}
