import React, { useState, useEffect, useCallback } from 'react'
import {
  BarChart3,
  TrendingUp,
  DollarSign,
  Clock,
  Hash,
  CheckCircle,
  XCircle,
  RefreshCw,
  Loader2,
  Filter,
  Calendar,
  Cpu,
} from 'lucide-react'

function formatNumber(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

function formatCost(cost) {
  if (!cost) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}

function formatMs(ms) {
  if (!ms) return '0ms'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

// Simple SVG bar chart component
function BarChartSVG({ data, dataKey, color = '#6366f1', label = '' }) {
  if (!data.length) return <div className="text-xs text-text-tertiary text-center py-8">No data</div>

  const maxVal = Math.max(...data.map(d => d[dataKey] || 0), 1)
  const barWidth = Math.max(12, Math.floor(600 / data.length) - 4)
  const chartWidth = Math.max(600, data.length * (barWidth + 4))
  const chartHeight = 160

  return (
    <div className="overflow-x-auto">
      <svg width={chartWidth} height={chartHeight + 40} className="w-full" viewBox={`0 0 ${chartWidth} ${chartHeight + 40}`} preserveAspectRatio="xMinYMid meet">
        {/* Bars */}
        {data.map((d, i) => {
          const val = d[dataKey] || 0
          const h = (val / maxVal) * chartHeight
          const x = i * (barWidth + 4) + 2
          const y = chartHeight - h
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={h}
                fill={color}
                opacity={0.8}
                rx={2}
              >
                <title>{`${d.period}: ${typeof val === 'number' && val % 1 !== 0 ? val.toFixed(1) : val}`}</title>
              </rect>
              {/* X-axis label */}
              {data.length <= 14 && (
                <text
                  x={x + barWidth / 2}
                  y={chartHeight + 14}
                  textAnchor="middle"
                  className="fill-text-tertiary"
                  fontSize="9"
                >
                  {(d.period || '').slice(-5)}
                </text>
              )}
            </g>
          )
        })}
        {/* Y-axis labels */}
        <text x={4} y={12} className="fill-text-tertiary" fontSize="9">{typeof maxVal === 'number' && maxVal % 1 !== 0 ? maxVal.toFixed(1) : maxVal}</text>
        <text x={4} y={chartHeight} className="fill-text-tertiary" fontSize="9">0</text>
      </svg>
      {label && <div className="text-xs text-text-tertiary text-center mt-1">{label}</div>}
    </div>
  )
}

function MetricsDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [granularity, setGranularity] = useState('daily')
  const [dateRange, setDateRange] = useState(30) // days
  const [providerFilter, setProviderFilter] = useState('')
  const [modelFilter, setModelFilter] = useState('')

  const loadMetrics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      const now = new Date()
      const from = new Date(now.getTime() - dateRange * 24 * 60 * 60 * 1000)
      params.set('date_from', from.toISOString())
      params.set('date_to', now.toISOString())
      params.set('granularity', granularity)
      if (providerFilter) params.set('llm_provider', providerFilter)
      if (modelFilter) params.set('model', modelFilter)

      const res = await fetch(`/api/metrics?${params}`)
      if (!res.ok) throw new Error(`Failed to load metrics: ${res.status}`)
      const data = await res.json()
      setMetrics(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [dateRange, granularity, providerFilter, modelFilter])

  useEffect(() => {
    loadMetrics()
  }, [loadMetrics])

  if (loading && !metrics) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    )
  }

  const summary = metrics?.summary || {}
  const timeSeries = metrics?.time_series || []
  const modelBreakdown = metrics?.model_breakdown || []

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <BarChart3 size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-semibold text-text-primary">Metrics Dashboard</h1>
              <p className="text-sm text-text-tertiary">Aggregate performance metrics over time</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Date range */}
            <div className="flex items-center gap-1 bg-surface border border-border rounded-lg px-2 py-1.5">
              <Calendar size={14} className="text-text-tertiary" />
              <select
                value={dateRange}
                onChange={(e) => setDateRange(Number(e.target.value))}
                className="bg-transparent text-sm text-text-primary outline-none cursor-pointer"
              >
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
            </div>

            {/* Granularity */}
            <div className="flex items-center gap-1 bg-surface border border-border rounded-lg px-2 py-1.5">
              <Filter size={14} className="text-text-tertiary" />
              <select
                value={granularity}
                onChange={(e) => setGranularity(e.target.value)}
                className="bg-transparent text-sm text-text-primary outline-none cursor-pointer"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>

            {/* Provider filter */}
            <input
              type="text"
              placeholder="Provider..."
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="bg-surface border border-border rounded-lg px-2 py-1.5 text-sm text-text-primary w-24 placeholder:text-text-disabled outline-none focus:border-primary"
            />

            {/* Model filter */}
            <input
              type="text"
              placeholder="Model..."
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="bg-surface border border-border rounded-lg px-2 py-1.5 text-sm text-text-primary w-24 placeholder:text-text-disabled outline-none focus:border-primary"
            />

            <button
              onClick={loadMetrics}
              className="btn btn-ghost"
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        {error && (
          <div className="p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm">
            {error}
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="flex items-center gap-2 text-text-tertiary text-xs font-medium uppercase tracking-wide mb-2">
              <TrendingUp size={14} />
              Total Runs
            </div>
            <div className="text-2xl font-bold text-text-primary">{summary.total_runs || 0}</div>
            <div className="text-xs text-text-tertiary mt-1">{summary.total_questions || 0} questions</div>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="flex items-center gap-2 text-text-tertiary text-xs font-medium uppercase tracking-wide mb-2">
              <CheckCircle size={14} className="text-success" />
              Pass Rate
            </div>
            <div className={`text-2xl font-bold ${
              summary.pass_rate >= 90 ? 'text-success' :
              summary.pass_rate >= 70 ? 'text-warning' : 'text-error'
            }`}>
              {summary.pass_rate || 0}%
            </div>
            <div className="text-xs text-text-tertiary mt-1">
              {summary.total_passed || 0} passed / {summary.total_failed || 0} failed
            </div>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="flex items-center gap-2 text-text-tertiary text-xs font-medium uppercase tracking-wide mb-2">
              <DollarSign size={14} />
              Total Cost
            </div>
            <div className="text-2xl font-bold text-text-primary">{formatCost(summary.total_cost)}</div>
            <div className="text-xs text-text-tertiary mt-1">Avg {formatCost(summary.avg_cost_per_run)} per run</div>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="flex items-center gap-2 text-text-tertiary text-xs font-medium uppercase tracking-wide mb-2">
              <Clock size={14} />
              Avg Latency
            </div>
            <div className="text-2xl font-bold text-text-primary">{formatMs(summary.avg_latency_ms)}</div>
            <div className="text-xs text-text-tertiary mt-1">{formatNumber(summary.total_tokens || 0)} tokens total</div>
          </div>
        </div>

        {/* Charts */}
        {timeSeries.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="p-4 rounded-xl bg-surface border border-border">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Pass Rate Over Time (%)</h3>
              <BarChartSVG data={timeSeries} dataKey="pass_rate" color="#22c55e" />
            </div>

            <div className="p-4 rounded-xl bg-surface border border-border">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Cost Over Time ($)</h3>
              <BarChartSVG data={timeSeries} dataKey="cost" color="#f59e0b" />
            </div>

            <div className="p-4 rounded-xl bg-surface border border-border">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Avg Latency Over Time (ms)</h3>
              <BarChartSVG data={timeSeries} dataKey="avg_latency_ms" color="#6366f1" />
            </div>

            <div className="p-4 rounded-xl bg-surface border border-border">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Questions Over Time</h3>
              <BarChartSVG data={timeSeries} dataKey="questions" color="#06b6d4" />
            </div>
          </div>
        )}

        {timeSeries.length === 0 && !loading && (
          <div className="text-center py-12">
            <BarChart3 size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
            <p className="text-text-tertiary">No data for the selected period</p>
            <p className="text-text-disabled text-sm mt-1">Run some tests to see metrics here</p>
          </div>
        )}

        {/* Model Breakdown */}
        {modelBreakdown.length > 0 && (
          <div className="p-4 rounded-xl bg-surface border border-border">
            <h3 className="text-sm font-semibold text-text-primary mb-3">Model Breakdown</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-text-tertiary uppercase tracking-wide border-b border-border">
                    <th className="pb-2 pr-4">Model</th>
                    <th className="pb-2 pr-4">Provider</th>
                    <th className="pb-2 pr-4">Runs</th>
                    <th className="pb-2 pr-4">Pass Rate</th>
                    <th className="pb-2 pr-4">Avg Latency</th>
                    <th className="pb-2 pr-4">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {modelBreakdown.map((m, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="py-2 pr-4 font-medium text-text-primary flex items-center gap-2">
                        <Cpu size={14} className="text-text-tertiary" />
                        {m.model}
                      </td>
                      <td className="py-2 pr-4 text-text-secondary">{m.provider}</td>
                      <td className="py-2 pr-4 text-text-secondary">{m.runs}</td>
                      <td className="py-2 pr-4">
                        <span className={`font-medium ${
                          m.pass_rate >= 90 ? 'text-success' :
                          m.pass_rate >= 70 ? 'text-warning' : 'text-error'
                        }`}>
                          {m.pass_rate}%
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-text-secondary font-mono">{formatMs(m.avg_latency_ms)}</td>
                      <td className="py-2 pr-4 text-text-secondary font-mono">{formatCost(m.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default MetricsDashboard
