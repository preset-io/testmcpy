import React, { useState, useEffect, useCallback } from 'react'
import {
  Shield,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Cpu,
} from 'lucide-react'

const SEVERITY_COLORS = {
  critical: { bg: 'bg-error/20', text: 'text-error', border: 'border-error/30', fill: '#ef4444' },
  high: { bg: 'bg-orange-500/20', text: 'text-orange-500', border: 'border-orange-500/30', fill: '#f97316' },
  medium: { bg: 'bg-warning/20', text: 'text-warning', border: 'border-warning/30', fill: '#eab308' },
  low: { bg: 'bg-info-light/20', text: 'text-info-light', border: 'border-info-light/30', fill: '#06b6d4' },
}

// Simple donut chart using SVG
function DonutChart({ data }) {
  const total = Object.values(data).reduce((sum, s) => sum + s.total, 0)
  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-text-tertiary text-sm">
        No security data
      </div>
    )
  }

  const radius = 60
  const strokeWidth = 20
  const circumference = 2 * Math.PI * radius
  let offset = 0

  const severityOrder = ['critical', 'high', 'medium', 'low']
  const segments = severityOrder
    .filter(s => data[s]?.total > 0)
    .map(severity => {
      const count = data[severity].total
      const pct = count / total
      const dashLen = circumference * pct
      const dashOffset = circumference - offset
      offset += dashLen
      return { severity, count, pct, dashLen, dashOffset }
    })

  return (
    <div className="flex items-center gap-6">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r={radius} fill="none" stroke="currentColor" strokeWidth={strokeWidth} className="text-surface-elevated" />
        {segments.map(seg => (
          <circle
            key={seg.severity}
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke={SEVERITY_COLORS[seg.severity].fill}
            strokeWidth={strokeWidth}
            strokeDasharray={`${seg.dashLen} ${circumference - seg.dashLen}`}
            strokeDashoffset={seg.dashOffset}
            transform="rotate(-90 80 80)"
          />
        ))}
        <text x="80" y="75" textAnchor="middle" className="fill-text-primary text-lg font-bold">{total}</text>
        <text x="80" y="93" textAnchor="middle" className="fill-text-tertiary text-xs">checks</text>
      </svg>

      <div className="space-y-2">
        {severityOrder.map(severity => {
          const s = data[severity]
          if (!s || s.total === 0) return null
          const colors = SEVERITY_COLORS[severity]
          return (
            <div key={severity} className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${colors.bg} border ${colors.border}`} />
              <span className={`text-sm font-medium capitalize ${colors.text}`}>{severity}</span>
              <span className="text-xs text-text-tertiary">
                {s.passed}/{s.total} passed
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SecurityDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [severityFilter, setSeverityFilter] = useState('all')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/security')
      if (!res.ok) throw new Error(`Failed: ${res.status}`)
      const result = await res.json()
      setData(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const summary = data?.summary || {}
  const breakdown = data?.severity_breakdown || {}
  const results = data?.results || []

  const filteredResults = severityFilter === 'all'
    ? results
    : results.filter(r => r.severity === severityFilter)

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Shield size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-semibold text-text-primary">Security Dashboard</h1>
              <p className="text-sm text-text-tertiary">Security-focused evaluator results</p>
            </div>
          </div>
          <button
            onClick={loadData}
            className="btn btn-ghost"
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        {error && (
          <div className="p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm">
            {error}
          </div>
        )}

        {loading && !data ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="animate-spin text-primary" size={32} />
          </div>
        ) : summary.total === 0 ? (
          <div className="text-center py-16">
            <Shield size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
            <p className="text-text-tertiary">No security evaluator results found</p>
            <p className="text-text-disabled text-sm mt-1">
              Add security evaluators like no_leaked_data, response_not_includes to your test suites
            </p>
          </div>
        ) : (
          <>
            {/* Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-surface border border-border col-span-1 md:col-span-2">
                <h3 className="text-sm font-semibold text-text-primary mb-3">Risk Summary</h3>
                <DonutChart data={breakdown} />
              </div>

              <div className="space-y-3">
                <div className="p-4 rounded-xl bg-surface border border-border">
                  <div className="text-xs text-text-tertiary uppercase tracking-wide mb-1">Total Checks</div>
                  <div className="text-2xl font-bold text-text-primary">{summary.total}</div>
                </div>
                <div className="p-4 rounded-xl bg-surface border border-border">
                  <div className="text-xs text-text-tertiary uppercase tracking-wide mb-1">Pass Rate</div>
                  <div className={`text-2xl font-bold ${
                    summary.pass_rate >= 90 ? 'text-success' :
                    summary.pass_rate >= 70 ? 'text-warning' : 'text-error'
                  }`}>
                    {summary.pass_rate}%
                  </div>
                </div>
                <div className="p-4 rounded-xl bg-surface border border-border">
                  <div className="text-xs text-text-tertiary uppercase tracking-wide mb-1">Failures</div>
                  <div className="text-2xl font-bold text-error">{summary.failed}</div>
                </div>
              </div>
            </div>

            {/* Severity filter */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-text-tertiary">Filter:</span>
              {['all', 'critical', 'high', 'medium', 'low'].map(sev => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`text-xs px-2 py-1 rounded-lg transition-colors capitalize ${
                    severityFilter === sev
                      ? 'bg-primary text-white'
                      : 'bg-surface border border-border text-text-secondary hover:bg-surface-hover'
                  }`}
                >
                  {sev}
                  {sev !== 'all' && breakdown[sev]?.total > 0 && (
                    <span className="ml-1">({breakdown[sev].total})</span>
                  )}
                </button>
              ))}
            </div>

            {/* Results table */}
            <div className="rounded-xl bg-surface border border-border overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-text-tertiary uppercase tracking-wide border-b border-border">
                    <th className="p-3">Status</th>
                    <th className="p-3">Evaluator</th>
                    <th className="p-3">Severity</th>
                    <th className="p-3">Test</th>
                    <th className="p-3">Model</th>
                    <th className="p-3">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.map((r, idx) => {
                    const colors = SEVERITY_COLORS[r.severity] || SEVERITY_COLORS.low
                    return (
                      <tr key={idx} className={idx % 2 === 0 ? '' : 'bg-surface-elevated/50'}>
                        <td className="p-3">
                          {r.passed ? (
                            <CheckCircle size={16} className="text-success" />
                          ) : (
                            <XCircle size={16} className="text-error" />
                          )}
                        </td>
                        <td className="p-3 font-mono text-text-primary">{r.evaluator}</td>
                        <td className="p-3">
                          <span className={`text-xs px-2 py-0.5 rounded capitalize ${colors.bg} ${colors.text}`}>
                            {r.severity}
                          </span>
                        </td>
                        <td className="p-3 text-text-secondary max-w-[160px] truncate" title={r.question_id}>
                          {r.question_id}
                        </td>
                        <td className="p-3 text-text-secondary flex items-center gap-1">
                          <Cpu size={12} className="text-text-tertiary" />
                          {r.model}
                        </td>
                        <td className="p-3 text-text-tertiary max-w-[200px] truncate" title={r.reason}>
                          {r.reason || '-'}
                        </td>
                      </tr>
                    )
                  })}
                  {filteredResults.length === 0 && (
                    <tr>
                      <td colSpan="6" className="p-8 text-center text-text-tertiary">
                        No results match the selected filter
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default SecurityDashboard
