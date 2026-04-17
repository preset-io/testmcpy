import React, { useState, useEffect, useCallback } from 'react'
import {
  GitCompare,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowUp,
  ArrowDown,
  Minus,
  Plus,
  Cpu,
  Clock,
  RefreshCw,
} from 'lucide-react'

function formatDuration(ms) {
  if (!ms) return '-'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

function RunComparison() {
  const [runs, setRuns] = useState([])
  const [selectedRunIds, setSelectedRunIds] = useState([])
  const [comparison, setComparison] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [error, setError] = useState(null)

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true)
    try {
      const res = await fetch('/api/results/list?limit=100')
      if (res.ok) {
        const data = await res.json()
        setRuns(data.runs || [])
      }
    } catch (err) {
      console.error('Failed to load runs:', err)
    } finally {
      setLoadingRuns(false)
    }
  }, [])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const toggleRun = (runId) => {
    setSelectedRunIds(prev => {
      if (prev.includes(runId)) {
        return prev.filter(id => id !== runId)
      }
      return [...prev, runId]
    })
  }

  const compareRuns = async () => {
    if (selectedRunIds.length < 2) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: selectedRunIds }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Failed: ${res.status}`)
      }
      const data = await res.json()
      setComparison(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const getCellStyle = (cell) => {
    if (!cell || cell.status === 'missing') return 'bg-surface-elevated text-text-disabled'
    if (cell.passed) return 'bg-success/10 text-success'
    return 'bg-error/10 text-error'
  }

  const getChangeIcon = (change) => {
    switch (change) {
      case 'regression':
        return <ArrowDown size={12} className="text-error" title="Regression" />
      case 'improvement':
        return <ArrowUp size={12} className="text-success" title="Improvement" />
      case 'new':
        return <Plus size={12} className="text-info-light" title="New test" />
      default:
        return null
    }
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <GitCompare size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-semibold text-text-primary">Run Comparison</h1>
              <p className="text-sm text-text-tertiary">Compare test runs side by side</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={compareRuns}
              disabled={selectedRunIds.length < 2 || loading}
              className="btn btn-primary disabled:opacity-50"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <GitCompare size={16} />}
              Compare ({selectedRunIds.length})
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 md:p-6 space-y-6">
        {error && (
          <div className="p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm">
            {error}
          </div>
        )}

        {/* Run selector */}
        {!comparison && (
          <div className="p-4 rounded-xl bg-surface border border-border">
            <h3 className="text-sm font-semibold text-text-primary mb-3">
              Select runs to compare (min 2)
            </h3>
            {loadingRuns ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="animate-spin text-primary" size={24} />
              </div>
            ) : runs.length === 0 ? (
              <div className="text-center py-8 text-text-tertiary">
                No test runs found. Run some tests first.
              </div>
            ) : (
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {runs.map(run => {
                  const isSelected = selectedRunIds.includes(run.run_id)
                  const passRate = run.total_tests > 0
                    ? ((run.passed / run.total_tests) * 100).toFixed(0)
                    : 0
                  return (
                    <div
                      key={run.run_id}
                      onClick={() => toggleRun(run.run_id)}
                      className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-primary/10 border border-primary/40'
                          : 'hover:bg-surface-hover border border-transparent'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        readOnly
                        className="rounded border-border flex-shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm text-text-primary truncate">
                            {run.test_file}
                          </span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            Number(passRate) >= 90 ? 'bg-success/20 text-success' :
                            Number(passRate) >= 70 ? 'bg-warning/20 text-warning' :
                            'bg-error/20 text-error'
                          }`}>
                            {passRate}%
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-text-tertiary">
                          <span className="flex items-center gap-1">
                            <Cpu size={10} /> {run.model}
                          </span>
                          <span>{run.provider}</span>
                          <span>{new Date(run.timestamp).toLocaleDateString()}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* Comparison matrix */}
        {comparison && (
          <>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text-primary">
                Comparison Matrix ({comparison.total_questions} tests)
              </h3>
              <button
                onClick={() => setComparison(null)}
                className="btn btn-ghost text-xs"
              >
                <RefreshCw size={14} /> New Comparison
              </button>
            </div>

            <div className="rounded-xl bg-surface border border-border overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="p-3 text-left text-xs text-text-tertiary uppercase tracking-wide sticky left-0 bg-surface z-10">
                      Test Case
                    </th>
                    {comparison.columns.map(col => (
                      <th key={col.run_id} className="p-3 text-center min-w-[140px]">
                        <div className="text-xs font-semibold text-text-primary">{col.model}</div>
                        <div className="text-[10px] text-text-tertiary">{col.provider}</div>
                        <div className={`text-xs font-bold mt-1 ${
                          col.pass_rate >= 90 ? 'text-success' :
                          col.pass_rate >= 70 ? 'text-warning' : 'text-error'
                        }`}>
                          {col.pass_rate}%
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.rows.map((row, idx) => (
                    <tr key={row.question_id} className={idx % 2 === 0 ? '' : 'bg-surface-elevated/50'}>
                      <td className="p-3 text-text-primary font-medium text-xs sticky left-0 bg-inherit z-10 max-w-[200px] truncate">
                        {row.question_id}
                      </td>
                      {comparison.columns.map(col => {
                        const cell = row.cells[col.run_id]
                        return (
                          <td key={col.run_id} className={`p-3 text-center ${getCellStyle(cell)}`}>
                            <div className="flex items-center justify-center gap-1">
                              {cell?.status === 'pass' && <CheckCircle size={14} />}
                              {cell?.status === 'fail' && <XCircle size={14} />}
                              {cell?.status === 'missing' && <Minus size={14} />}
                              {getChangeIcon(cell?.change)}
                            </div>
                            {cell?.score != null && (
                              <div className="text-[10px] font-mono mt-0.5 opacity-80">
                                {(cell.score * 100).toFixed(0)}%
                              </div>
                            )}
                            {cell?.duration_ms != null && (
                              <div className="text-[10px] text-text-tertiary mt-0.5 flex items-center justify-center gap-0.5">
                                <Clock size={8} /> {formatDuration(cell.duration_ms)}
                              </div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs text-text-tertiary flex-wrap">
              <span className="flex items-center gap-1"><CheckCircle size={12} className="text-success" /> Pass</span>
              <span className="flex items-center gap-1"><XCircle size={12} className="text-error" /> Fail</span>
              <span className="flex items-center gap-1"><Minus size={12} className="text-text-disabled" /> Missing</span>
              <span className="flex items-center gap-1"><ArrowDown size={12} className="text-error" /> Regression</span>
              <span className="flex items-center gap-1"><ArrowUp size={12} className="text-success" /> Improvement</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default RunComparison
