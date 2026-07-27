import React from 'react'
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { providerColor } from '../utils/providerColors'

const percent = (v) => `${Math.round(v * 100)}%`

// Strip the "suite :: " prefix so the y-axis reads as just provider/model.
const shortLabel = (key) => String(key || '').split(' :: ').pop()

// Minimal per-bar tooltip: just the pass rate for the hovered config.
const SuiteTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null
  const c = payload[0].payload
  return (
    <div className="bg-surface-elevated border border-border rounded-lg p-2 text-xs shadow-lg">
      <div className="font-semibold text-text-primary">{c.shortLabel}</div>
      <div className="text-text-secondary">Pass rate: {percent(c.pass_rate)}</div>
    </div>
  )
}

// One faceted card per suite, each ranking that suite's configs by pass rate.
const SuiteFacetBars = ({ configs }) => {
  const withSuite = (configs || []).filter((c) => c.suite)
  if (withSuite.length === 0) {
    return <p className="text-sm text-text-secondary">No per-suite data.</p>
  }

  // Group by suite name.
  const bySuite = new Map()
  withSuite.forEach((c) => {
    if (!bySuite.has(c.suite)) bySuite.set(c.suite, [])
    bySuite.get(c.suite).push(c)
  })

  const suites = Array.from(bySuite.keys()).sort()

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {suites.map((suite) => {
        const group = [...bySuite.get(suite)]
          .sort((a, b) => b.pass_rate - a.pass_rate)
          .map((c) => ({ ...c, shortLabel: shortLabel(c.key) }))
        const height = Math.max(90, group.length * 30)
        return (
          <div key={suite} className="bg-surface-elevated border border-border rounded-lg p-4">
            <h4 className="font-semibold text-text-primary mb-3 text-sm">{suite}</h4>
            <ResponsiveContainer width="100%" height={height}>
              <BarChart
                data={group}
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
                  dataKey="shortLabel"
                  width={140}
                  tick={{ fontSize: 10, fill: 'currentColor' }}
                />
                <Tooltip content={<SuiteTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Bar dataKey="pass_rate" radius={[0, 3, 3, 0]}>
                  {group.map((c, i) => (
                    <Cell key={i} fill={providerColor(c.provider, c.model)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      })}
    </div>
  )
}

export default SuiteFacetBars
