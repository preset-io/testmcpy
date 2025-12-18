import React, { useState } from 'react'
import { CheckCircle, XCircle, ChevronDown, ChevronRight, Terminal } from 'lucide-react'

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

          {/* Provider Logs */}
          {result.logs && result.logs.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5 flex items-center gap-1.5">
                <Terminal size={12} />
                Provider Logs ({result.logs.length})
              </h4>
              <div className="p-3 bg-gray-900 rounded-lg border border-border max-h-64 overflow-y-auto">
                <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap">
                  {result.logs.map((log, idx) => (
                    <div key={idx} className={`leading-relaxed ${
                      log.includes('Error') || log.includes('❌') ? 'text-red-400' :
                      log.includes('Tool call') || log.includes('🔧') ? 'text-cyan-400' :
                      log.includes('✅') || log.includes('Parsed:') ? 'text-green-400' :
                      log.includes('Waiting') || log.includes('Running') ? 'text-yellow-400' :
                      'text-gray-300'
                    }`}>
                      {log}
                    </div>
                  ))}
                </pre>
              </div>
            </div>
          )}

          {/* LLM Response */}
          {(result.response || result.llm_response) && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">LLM Response</h4>
              <div className="p-3 bg-surface rounded-lg border border-border max-h-48 overflow-y-auto">
                <pre className="text-xs text-text-primary whitespace-pre-wrap font-mono">
                  {typeof (result.response || result.llm_response) === 'string'
                    ? (result.response || result.llm_response)
                    : JSON.stringify((result.response || result.llm_response), null, 2)}
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
          {result.evaluations && result.evaluations.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary mb-1.5">
                Evaluators ({result.evaluations.length})
              </h4>
              <div className="space-y-2">
                {result.evaluations.map((evaluation, idx) => {
                  const failed = !evaluation.passed
                  return (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border ${
                        failed
                          ? 'bg-error/5 border-error/30'
                          : 'bg-surface border-border'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        {evaluation.passed ? (
                          <CheckCircle size={14} className="text-success mt-0.5 flex-shrink-0" />
                        ) : (
                          <XCircle size={14} className="text-error mt-0.5 flex-shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-sm font-medium ${
                              failed ? 'text-error' : 'text-text-primary'
                            }`}>
                              {evaluation.evaluator || evaluation.name || 'Unknown Evaluator'}
                            </span>
                            {evaluation.score !== undefined && (
                              <span className="text-xs text-text-tertiary font-mono">
                                Score: {(evaluation.score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                          {evaluation.reason && (
                            <p className={`text-xs leading-relaxed ${
                              failed ? 'text-error-light' : 'text-text-secondary'
                            }`}>
                              {evaluation.reason}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
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
