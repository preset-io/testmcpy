import React from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { formatCost } from '../utils/formatters'
import { providerColor } from '../utils/providerColors'

// Reasoning-effort ordering; anything unknown (incl. 'default') sorts last so a
// model's points connect into a low → high effort curve.
const EFFORT_ORDER = ['minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'default']
const effortRank = (e) => {
  const i = EFFORT_ORDER.indexOf(e)
  return i === -1 ? EFFORT_ORDER.length : i
}

// Tooltip body for a single point on a model's effort curve.
const AccuracyCostTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null
  const p = payload[0].payload
  return (
    <div className="bg-surface-elevated border border-border rounded-lg p-3 text-xs shadow-lg">
      <div className="font-semibold text-text-primary mb-1">{p.series}</div>
      <div className="text-text-secondary space-y-0.5">
        <div>Effort: {p.effort}</div>
        <div>Pass rate: {Math.round(p.y)}%</div>
        <div>Avg cost / task: {formatCost(p.cost)}</div>
      </div>
    </div>
  )
}

// Effort-independent config identity: provider + model + MCP profile. Two rows
// that differ only by effort belong to the same curve; two rows that differ by
// provider/profile must NOT be merged (they'd form a misleading connected line
// and inherit one row's color).
const seriesKey = (c) =>
  `${c.provider || '?'}/${c.model}${c.mcp_profile ? ` @ ${c.mcp_profile}` : ''}`

// Build one connected effort curve per effort-independent identity. Exported so
// the grouping (the part that must not merge distinct provider/profile configs)
// is unit-testable without rendering recharts.
export function buildEffortSeries(configs) {
  const usable = (configs || []).filter((c) => c.n_results >= 1 && c.total_cost / c.n_results > 0)

  const byConfig = new Map()
  usable.forEach((c) => {
    const key = seriesKey(c)
    if (!byConfig.has(key)) {
      byConfig.set(key, { key, model: c.model, provider: c.provider, points: [] })
    }
    byConfig.get(key).points.push({
      series: key,
      model: c.model,
      cost: c.total_cost / c.n_results,
      y: c.pass_rate * 100,
      effort: c.effort || 'default',
      label: c.key,
    })
  })

  const series = Array.from(byConfig.values())
  series.forEach((s) => s.points.sort((a, b) => effortRank(a.effort) - effortRank(b.effort)))
  return series
}

// FrontierCode accuracy-vs-cost view: each provider/model/profile becomes a
// connected effort curve on a log cost axis. A series with one effort is a
// single point.
const AccuracyVsCostChart = ({ configs }) => {
  const series = buildEffortSeries(configs)
  const totalPoints = series.reduce((sum, s) => sum + s.points.length, 0)
  if (totalPoints === 0) {
    return (
      <p className="text-sm text-text-secondary">
        No cost/score data yet — run a bench with --efforts to see the curve.
      </p>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 8, right: 24, left: 8, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
        <XAxis
          type="number"
          dataKey="cost"
          name="Cost"
          scale="log"
          domain={['auto', 'auto']}
          tickFormatter={formatCost}
          tick={{ fontSize: 11, fill: 'currentColor' }}
          label={{
            value: 'Avg cost / task (log)',
            position: 'insideBottom',
            offset: -12,
            fontSize: 11,
            fill: 'currentColor',
          }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="Pass rate"
          domain={[0, 100]}
          tick={{ fontSize: 11, fill: 'currentColor' }}
          label={{
            value: 'Pass rate (%)',
            angle: -90,
            position: 'insideLeft',
            fontSize: 11,
            fill: 'currentColor',
          }}
        />
        <Tooltip content={<AccuracyCostTooltip />} cursor={false} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {series.map((s) => {
          const color = providerColor(s.provider, s.model)
          return (
            <Scatter
              key={s.key}
              name={s.key}
              data={s.points}
              line={{ stroke: color }}
              fill={color}
            />
          )
        })}
      </ScatterChart>
    </ResponsiveContainer>
  )
}

export default AccuracyVsCostChart
