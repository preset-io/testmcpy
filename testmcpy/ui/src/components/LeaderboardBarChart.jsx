import React from 'react'
import {
  BarChart,
  Bar,
  Cell,
  ErrorBar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { formatCost, formatTokens } from '../utils/formatters'
import { providerColor } from '../utils/providerColors'

const percent = (v) => `${Math.round(v * 100)}%`

// Tooltip body for a single ranked config. `payload[0].payload` is the config
// object so we can surface the richer per-task metrics behind each bar.
const LeaderboardTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null
  const c = payload[0].payload
  const avgCostPerTask = c.n_results > 0 ? c.total_cost / c.n_results : 0
  return (
    <div className="bg-surface-elevated border border-border rounded-lg p-3 text-xs shadow-lg">
      <div className="font-semibold text-text-primary mb-1">{c.key}</div>
      <div className="text-text-secondary space-y-0.5">
        <div>Pass rate: {percent(c.pass_rate)}</div>
        <div>±stddev: {percent(c.score_stddev || 0)}</div>
        <div>Avg cost / task: {formatCost(avgCostPerTask)}</div>
        <div>Output tokens: {formatTokens(c.avg_tokens_output)}</div>
        <div>Steps: {Math.round(c.avg_steps || 0)}</div>
      </div>
    </div>
  )
}

// DeepSWE-style ranked leaderboard: one horizontal bar per config, sorted by
// pass rate, colored by provider family, with a score-stddev error bar.
const LeaderboardBarChart = ({ configs, colorFor = providerColor }) => {
  if (!configs || configs.length === 0) {
    return <p className="text-sm text-text-secondary">No data</p>
  }

  const data = [...configs].sort((a, b) => b.pass_rate - a.pass_rate)
  const height = Math.max(120, data.length * 34)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 24, left: 0, bottom: 4 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
        <XAxis
          type="number"
          domain={[0, 1]}
          tickFormatter={percent}
          tick={{ fontSize: 11, fill: 'currentColor' }}
        />
        <YAxis
          type="category"
          dataKey="key"
          width={200}
          tick={{ fontSize: 10, fill: 'currentColor' }}
        />
        <Tooltip content={<LeaderboardTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="pass_rate" radius={[0, 3, 3, 0]}>
          {data.map((c, i) => (
            <Cell key={i} fill={colorFor(c.provider, c.model)} />
          ))}
          <ErrorBar
            dataKey="score_stddev"
            direction="x"
            width={4}
            strokeWidth={1.5}
            stroke="currentColor"
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default LeaderboardBarChart
