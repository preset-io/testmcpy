import React from 'react'
import { CheckCircle, XCircle, Wrench, Flag, Calculator } from 'lucide-react'
import Badge from './Badge'

// Plain-language explainer for a test's 0..1 score. Consumes the
// `score_breakdown` object the backend attaches to each result (see
// testmcpy/scoring.py) and answers "what is this number and why".
//
// Used in both the /reports test detail and the /performance drill panel so
// the score is explained the same way everywhere.

function pct(v) {
  return `${Math.round((v ?? 0) * 100)}%`
}

function fmt(v) {
  return (v ?? 0).toFixed(2)
}

function scoreColor(v) {
  if (v >= 0.999) return 'text-success'
  if (v >= 0.5) return 'text-warning'
  return 'text-error'
}

function ScoreBreakdown({ breakdown, compact = false }) {
  if (!breakdown) return null

  const {
    base_score = 0,
    final_score = 0,
    penalty_source = null,
    penalty_multiplier = 1,
    evaluator_breakdown = [],
    factors = [],
  } = breakdown

  const hasPenalty = penalty_source != null && final_score < base_score - 0.0001
  // Width of the "kept" portion of the bar (final relative to base).
  const keptPct = base_score > 0 ? Math.min(100, (final_score / base_score) * 100) : 0
  const fpFactor = factors.find(f => f.label?.startsWith('False-positive'))
  const manualFactor = factors.find(f => f.label?.startsWith('Manually'))

  return (
    <div className="rounded-lg border border-border bg-surface p-3 space-y-3">
      {/* Headline */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Calculator size={14} className="text-text-tertiary" />
          <span className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Why this score
          </span>
        </div>
        <div className="flex items-baseline gap-1 font-mono">
          <span className={`text-lg font-bold ${scoreColor(final_score)}`}>{fmt(final_score)}</span>
          <span className="text-xs text-text-disabled">/ 1.00</span>
        </div>
      </div>

      {/* Equation: base × penalty = final */}
      <div className="flex items-center flex-wrap gap-1.5 text-xs text-text-secondary font-mono">
        <span title="Mean of all evaluator scores">base {fmt(base_score)}</span>
        {hasPenalty ? (
          <>
            <span className="text-text-disabled">×</span>
            <span className="text-error" title={penalty_source === 'manual' ? 'Manual false-positive penalty' : 'False-positive tool-call penalty'}>
              {fmt(penalty_multiplier)}
            </span>
          </>
        ) : null}
        <span className="text-text-disabled">=</span>
        <span className={`font-semibold ${scoreColor(final_score)}`}>{fmt(final_score)}</span>
      </div>

      {/* Segmented bar: kept vs penalised */}
      <div className="h-2 w-full rounded-full bg-error/20 overflow-hidden" title={`${pct(final_score / (base_score || 1))} of the base score kept`}>
        <div
          className={`h-full rounded-full ${final_score >= 0.999 ? 'bg-success' : final_score >= 0.5 ? 'bg-warning' : 'bg-error'}`}
          style={{ width: `${keptPct}%` }}
        />
      </div>

      {/* Penalty explanation */}
      {fpFactor && (
        <div className="flex items-start gap-2 text-xs text-text-secondary">
          <Wrench size={13} className="text-error flex-shrink-0 mt-0.5" />
          <span>
            <span className="font-medium text-error">−{pct(1 - penalty_multiplier)}</span>{' '}
            false-positive penalty — {fpFactor.detail}.
          </span>
        </div>
      )}
      {manualFactor && (
        <div className="flex items-start gap-2 text-xs text-text-secondary">
          <Flag size={13} className="text-warning flex-shrink-0 mt-0.5" />
          <span>
            <span className="font-medium text-warning">−{pct(1 - penalty_multiplier)}</span>{' '}
            {manualFactor.detail}
          </span>
        </div>
      )}

      {/* Per-evaluator contributions */}
      {!compact && evaluator_breakdown.length > 0 && (
        <div className="space-y-1 pt-1 border-t border-border">
          <div className="text-[10px] uppercase tracking-wide text-text-disabled">
            {evaluator_breakdown.length} evaluator{evaluator_breakdown.length === 1 ? '' : 's'} · equal weight
          </div>
          {evaluator_breakdown.map((ev, idx) => (
            <div key={idx} className="flex items-center justify-between gap-2 text-xs">
              <span className="flex items-center gap-1.5 min-w-0">
                {ev.passed ? (
                  <CheckCircle size={12} className="text-success flex-shrink-0" />
                ) : (
                  <XCircle size={12} className="text-error flex-shrink-0" />
                )}
                <span className={`truncate ${ev.passed ? 'text-text-secondary' : 'text-error'}`}>
                  {ev.name}
                </span>
              </span>
              <span className="font-mono text-text-tertiary flex-shrink-0">{pct(ev.score)}</span>
            </div>
          ))}
        </div>
      )}

      {/* No-penalty reassurance */}
      {!hasPenalty && (
        <div className="flex items-center gap-2 text-xs text-text-tertiary">
          <Badge variant="success" size="xs">no penalty</Badge>
          <span>No unexpected tool calls — final score equals the evaluator average.</span>
        </div>
      )}
    </div>
  )
}

export default ScoreBreakdown
