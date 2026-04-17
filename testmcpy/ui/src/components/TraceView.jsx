import React, { useState, useEffect } from 'react'
import {
  Loader2,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Wrench,
  Clock,
} from 'lucide-react'

function formatMs(ms) {
  if (!ms && ms !== 0) return '-'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

function ToolCallBar({ call, maxDuration }) {
  const [expanded, setExpanded] = useState(false)
  const widthPct = maxDuration > 0 ? Math.max(2, (call.duration_ms / maxDuration) * 100) : 100
  const leftPct = maxDuration > 0 ? (call.start_ms / maxDuration) * 100 : 0

  const barColor = call.status === 'error'
    ? 'bg-error'
    : 'bg-primary'

  return (
    <div className="mb-2">
      <div
        className="flex items-center gap-2 cursor-pointer hover:bg-surface-hover rounded-lg p-1.5 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={12} className="text-text-tertiary flex-shrink-0" /> : <ChevronRight size={12} className="text-text-tertiary flex-shrink-0" />}
        <Wrench size={12} className={call.status === 'error' ? 'text-error flex-shrink-0' : 'text-primary flex-shrink-0'} />
        <span className="text-xs font-mono font-medium text-text-primary truncate max-w-[120px]">{call.name}</span>
        <div className="flex-1 h-5 bg-surface-elevated rounded-full relative overflow-hidden mx-2">
          <div
            className={`absolute top-0 h-full rounded-full ${barColor} opacity-80 transition-all`}
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
          >
            <span className="absolute inset-0 flex items-center justify-center text-[9px] text-white font-medium">
              {formatMs(call.duration_ms)}
            </span>
          </div>
        </div>
        {call.status === 'error' ? (
          <XCircle size={14} className="text-error flex-shrink-0" />
        ) : (
          <CheckCircle size={14} className="text-success flex-shrink-0" />
        )}
      </div>

      {expanded && (
        <div className="ml-7 mt-1 space-y-2 pb-2">
          {/* Timing */}
          <div className="flex items-center gap-3 text-xs text-text-tertiary">
            <span className="flex items-center gap-1">
              <Clock size={10} /> Start: {formatMs(call.start_ms)}
            </span>
            <span>Duration: {formatMs(call.duration_ms)}</span>
          </div>

          {/* Arguments */}
          {call.arguments && Object.keys(call.arguments).length > 0 && (
            <div>
              <span className="text-xs font-semibold text-text-secondary">Arguments</span>
              <pre className="text-xs font-mono bg-surface p-2 rounded border border-border overflow-x-auto mt-1 max-h-32 overflow-y-auto text-text-secondary">
                {JSON.stringify(call.arguments, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {call.result && (
            <div>
              <span className="text-xs font-semibold text-text-secondary">Result</span>
              <pre className={`text-xs font-mono p-2 rounded border overflow-x-auto mt-1 max-h-48 overflow-y-auto ${
                call.is_error
                  ? 'bg-error/5 border-error/30 text-error'
                  : 'bg-surface border-border text-text-secondary'
              }`}>
                {typeof call.result === 'string'
                  ? call.result.substring(0, 2000)
                  : JSON.stringify(call.result, null, 2)?.substring(0, 2000)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TraceView({ runId, onClose }) {
  const [traces, setTraces] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!runId) return
    setLoading(true)
    setError(null)
    fetch(`/api/results/run/${runId}/traces`)
      .then(res => {
        if (!res.ok) throw new Error(`Failed: ${res.status}`)
        return res.json()
      })
      .then(data => setTraces(data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="animate-spin text-primary" size={24} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm">
        {error}
      </div>
    )
  }

  if (!traces?.traces?.length) {
    return (
      <div className="text-center py-8 text-text-tertiary text-sm">
        No trace data available for this run.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-text-tertiary">
          {traces.model} / {traces.provider} — {traces.traces.length} test(s)
        </div>
        {onClose && (
          <button onClick={onClose} className="text-xs text-text-tertiary hover:text-text-primary">
            Close
          </button>
        )}
      </div>

      {traces.traces.map((trace, idx) => {
        const maxDuration = trace.total_duration_ms || 1
        return (
          <div key={idx} className="p-3 rounded-lg bg-surface border border-border">
            <div className="flex items-center gap-2 mb-2">
              {trace.passed ? (
                <CheckCircle size={14} className="text-success flex-shrink-0" />
              ) : (
                <XCircle size={14} className="text-error flex-shrink-0" />
              )}
              <span className="text-sm font-medium text-text-primary">{trace.question_id}</span>
              <span className="text-xs text-text-tertiary ml-auto">{formatMs(trace.total_duration_ms)}</span>
            </div>

            {trace.tool_calls.length > 0 ? (
              <div className="ml-1">
                {trace.tool_calls.map((call, callIdx) => (
                  <ToolCallBar key={callIdx} call={call} maxDuration={maxDuration} />
                ))}
              </div>
            ) : (
              <div className="text-xs text-text-disabled ml-6">No tool calls</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default TraceView
