import React, { useState } from 'react'
import { CheckCircle, XCircle, ChevronDown, ChevronRight } from 'lucide-react'

/**
 * Collapsible test result panel showing test details
 * Displays test name, status, duration, cost, and expandable details
 */
function TestResultPanel({ result, initialExpanded = false }) {
  const [expanded, setExpanded] = useState(initialExpanded)

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Header (always visible) */}
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {result.passed ? (
            <CheckCircle size={18} className="text-success flex-shrink-0" />
          ) : (
            <XCircle size={18} className="text-error flex-shrink-0" />
          )}
          <span className="font-medium text-sm text-text-primary">{result.test_name}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-text-tertiary">
          {result.duration && (
            <span>{result.duration.toFixed(2)}s</span>
          )}
          {result.cost > 0 && (
            <span className="font-mono">${result.cost.toFixed(4)}</span>
          )}
          {expanded ? (
            <ChevronDown size={16} className="text-text-secondary" />
          ) : (
            <ChevronRight size={16} className="text-text-secondary" />
          )}
        </div>
      </div>

      {/* Details (collapsible) */}
      {expanded && (
        <div className="border-t border-border p-4 bg-surface-elevated space-y-3">
          {/* Reason */}
          {result.reason && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">Result</h4>
              <p className="text-sm text-text-primary leading-relaxed">{result.reason}</p>
            </div>
          )}

          {/* Error */}
          {result.error && (
            <div>
              <h4 className="text-xs font-semibold text-error mb-1.5">Error</h4>
              <div className="p-3 bg-error/10 border border-error/30 rounded-lg">
                <p className="text-sm text-error font-mono">{result.error}</p>
              </div>
            </div>
          )}

          {/* LLM Response */}
          {result.llm_response && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">LLM Response</h4>
              <div className="p-3 bg-surface rounded-lg border border-border">
                <pre className="text-xs text-text-primary whitespace-pre-wrap font-mono">
                  {typeof result.llm_response === 'string'
                    ? result.llm_response
                    : JSON.stringify(result.llm_response, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Tool Calls */}
          {result.tool_calls && result.tool_calls.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">
                Tool Calls ({result.tool_calls.length})
              </h4>
              <div className="space-y-2">
                {result.tool_calls.map((call, idx) => (
                  <div key={idx} className="p-3 bg-surface rounded-lg border border-border">
                    <div className="text-sm font-medium text-primary mb-1">{call.name}</div>
                    {call.arguments && (
                      <pre className="text-xs text-text-tertiary font-mono whitespace-pre-wrap">
                        {typeof call.arguments === 'string'
                          ? call.arguments
                          : JSON.stringify(call.arguments, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evaluator Details */}
          {result.evaluator_results && result.evaluator_results.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">
                Evaluators ({result.evaluator_results.length})
              </h4>
              <div className="space-y-1.5">
                {result.evaluator_results.map((evaluator, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 bg-surface rounded border border-border"
                  >
                    <div className="flex items-center gap-2">
                      {evaluator.passed ? (
                        <CheckCircle size={14} className="text-success" />
                      ) : (
                        <XCircle size={14} className="text-error" />
                      )}
                      <span className="text-xs text-text-primary">{evaluator.name}</span>
                    </div>
                    {evaluator.reason && (
                      <span className="text-xs text-text-tertiary">{evaluator.reason}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          {(result.model || result.provider) && (
            <div className="pt-2 border-t border-border">
              <div className="flex gap-4 text-xs text-text-tertiary">
                {result.provider && (
                  <div>
                    <span className="text-text-disabled">Provider:</span>{' '}
                    <span className="text-text-secondary">{result.provider}</span>
                  </div>
                )}
                {result.model && (
                  <div>
                    <span className="text-text-disabled">Model:</span>{' '}
                    <span className="text-text-secondary">{result.model}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default TestResultPanel
