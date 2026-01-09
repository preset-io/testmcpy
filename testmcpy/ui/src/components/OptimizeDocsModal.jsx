import React, { useState, useEffect } from 'react'
import { X, Loader, CheckCircle, AlertCircle, Wand2, Copy, Check, TrendingUp, AlertTriangle, Info } from 'lucide-react'

function OptimizeDocsModal({ tool, onClose }) {
  const [step, setStep] = useState('analyzing') // 'analyzing', 'success', 'error'
  const [analysis, setAnalysis] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [error, setError] = useState(null)
  const [cost, setCost] = useState(0)
  const [duration, setDuration] = useState(0)
  const [copiedSection, setCopiedSection] = useState(null)
  const [config, setConfig] = useState(null)

  useEffect(() => {
    loadConfig()
  }, [])

  useEffect(() => {
    if (config) {
      analyzeDocumentation()
    }
  }, [config])

  const loadConfig = async () => {
    try {
      const res = await fetch('/api/config')
      const data = await res.json()
      setConfig(data)
    } catch (error) {
      console.error('Failed to load config:', error)
      setError('Failed to load configuration')
      setStep('error')
    }
  }

  const analyzeDocumentation = async () => {
    try {
      setStep('analyzing')
      setError(null)

      const provider = config?.DEFAULT_PROVIDER?.value || 'anthropic'
      const model = config?.DEFAULT_MODEL?.value || 'claude-haiku-4-5'

      const response = await fetch('/api/mcp/optimize-docs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: tool.name,
          description: tool.description,
          input_schema: tool.input_schema,
          provider: provider,
          model: model,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to analyze documentation')
      }

      const data = await response.json()
      setAnalysis(data.analysis)
      setSuggestions(data.suggestions)
      setCost(data.cost)
      setDuration(data.duration)
      setStep('success')

    } catch (err) {
      console.error('Error analyzing documentation:', err)
      setError(err.message)
      setStep('error')
    }
  }

  const copyToClipboard = (text, section) => {
    navigator.clipboard.writeText(text)
    setCopiedSection(section)
    setTimeout(() => setCopiedSection(null), 2000)
  }

  const handleClose = () => {
    if (step === 'analyzing') {
      // Don't allow closing during analysis
      return
    }
    onClose()
  }

  const getScoreColor = (score) => {
    if (score >= 75) return 'text-success'
    if (score >= 50) return 'text-warning'
    return 'text-error'
  }

  const getScoreBgColor = (score) => {
    if (score >= 75) return 'bg-success/10 border-success/30'
    if (score >= 50) return 'bg-warning/10 border-warning/30'
    return 'bg-error/10 border-error/30'
  }

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'high':
        return 'text-error bg-error/10 border-error/20'
      case 'medium':
        return 'text-warning bg-warning/10 border-warning/20'
      case 'low':
        return 'text-info bg-info/10 border-info/20'
      default:
        return 'text-text-secondary bg-surface-elevated border-border'
    }
  }

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'clarity':
        return <Info size={14} />
      case 'completeness':
        return <CheckCircle size={14} />
      case 'actionability':
        return <TrendingUp size={14} />
      case 'examples':
        return <AlertTriangle size={14} />
      case 'constraints':
        return <AlertCircle size={14} />
      default:
        return <Info size={14} />
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface border border-border rounded-xl shadow-strong max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-500/10 rounded-lg flex items-center justify-center">
              <Wand2 size={20} className="text-purple-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text-primary">Optimize Tool Documentation</h2>
              <p className="text-sm text-text-secondary mt-0.5">
                AI-powered analysis for <span className="font-mono text-primary">{tool.name}</span>
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={step === 'analyzing'}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X size={20} className="text-text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {step === 'analyzing' && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader className="w-12 h-12 text-purple-500 animate-spin mb-4" />
              <h3 className="text-lg font-semibold text-text-primary mb-2">Analyzing Documentation...</h3>
              <p className="text-text-secondary text-center max-w-md">
                The LLM is evaluating the tool description against best practices for LLM tool calling
              </p>
            </div>
          )}

          {step === 'success' && analysis && suggestions && (
            <div className="space-y-6">
              {/* Score Summary */}
              <div className={`p-4 rounded-lg border ${getScoreBgColor(analysis.score)}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`text-3xl font-bold ${getScoreColor(analysis.score)}`}>
                      {analysis.score}/100
                    </div>
                    <div>
                      <h3 className="font-semibold text-text-primary">Documentation Quality Score</h3>
                      <p className="text-sm text-text-secondary mt-0.5">
                        {analysis.issues.length} issue{analysis.issues.length !== 1 ? 's' : ''} found
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-xs font-semibold uppercase tracking-wide ${getScoreColor(analysis.score)}`}>
                      {analysis.clarity}
                    </div>
                    <div className="text-xs text-text-tertiary mt-1">
                      ${cost.toFixed(4)} · {duration.toFixed(2)}s
                    </div>
                  </div>
                </div>
              </div>

              {/* Issues Found */}
              {analysis.issues && analysis.issues.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                    <AlertCircle size={16} className="text-warning" />
                    Issues Identified
                  </h3>
                  <div className="space-y-2">
                    {analysis.issues.map((issue, idx) => (
                      <div key={idx} className="bg-surface-elevated border border-border rounded-lg p-4">
                        <div className="flex items-start gap-3">
                          <div className={`mt-0.5 p-1.5 rounded ${getSeverityColor(issue.severity)}`}>
                            {getCategoryIcon(issue.category)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded border ${getSeverityColor(issue.severity)}`}>
                                {issue.severity || 'medium'}
                              </span>
                              <span className="text-xs text-text-tertiary">
                                {issue.category || 'general'}
                              </span>
                            </div>
                            <h4 className="text-sm font-semibold text-text-primary mb-2">
                              {issue.issue}
                            </h4>
                            {issue.current && (
                              <div className="mb-2">
                                <div className="text-xs text-text-tertiary mb-1">Current:</div>
                                <div className="text-sm text-text-secondary bg-surface p-2 rounded border border-border font-mono">
                                  "{issue.current}"
                                </div>
                              </div>
                            )}
                            {issue.suggestion && (
                              <div>
                                <div className="text-xs text-text-tertiary mb-1">Suggestion:</div>
                                <div className="text-sm text-text-primary">
                                  {issue.suggestion}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Before/After Comparison */}
              <div>
                <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                  <TrendingUp size={16} className="text-success" />
                  Description Comparison
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  {/* Current Description */}
                  <div className="bg-surface-elevated border border-border rounded-lg overflow-hidden">
                    <div className="px-4 py-2 bg-surface border-b border-border flex items-center justify-between">
                      <h4 className="text-xs font-semibold text-text-secondary uppercase">Current</h4>
                      <button
                        onClick={() => copyToClipboard(tool.description, 'current')}
                        className="p-1 hover:bg-surface-hover rounded transition-colors"
                        title="Copy current description"
                      >
                        {copiedSection === 'current' ? (
                          <Check size={14} className="text-success" />
                        ) : (
                          <Copy size={14} className="text-text-tertiary" />
                        )}
                      </button>
                    </div>
                    <div className="p-4">
                      <p className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
                        {tool.description}
                      </p>
                    </div>
                  </div>

                  {/* Optimized Description */}
                  <div className="bg-success/5 border border-success/20 rounded-lg overflow-hidden">
                    <div className="px-4 py-2 bg-success/10 border-b border-success/20 flex items-center justify-between">
                      <h4 className="text-xs font-semibold text-success uppercase">Optimized</h4>
                      <button
                        onClick={() => copyToClipboard(suggestions.improved_description, 'optimized')}
                        className="p-1 hover:bg-success/20 rounded transition-colors"
                        title="Copy optimized description"
                      >
                        {copiedSection === 'optimized' ? (
                          <Check size={14} className="text-success" />
                        ) : (
                          <Copy size={14} className="text-success" />
                        )}
                      </button>
                    </div>
                    <div className="p-4">
                      <p className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
                        {suggestions.improved_description}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Specific Improvements */}
              {suggestions.improvements && suggestions.improvements.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                    <CheckCircle size={16} className="text-primary" />
                    Specific Improvements
                  </h3>
                  <div className="space-y-3">
                    {suggestions.improvements.map((improvement, idx) => (
                      <div key={idx} className="bg-surface-elevated border border-border rounded-lg p-4">
                        <h4 className="text-sm font-semibold text-text-primary mb-2">
                          {idx + 1}. {improvement.issue}
                        </h4>
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <div className="text-xs text-text-tertiary mb-1">Before:</div>
                              <div className="text-sm text-text-secondary bg-surface p-2 rounded border border-border">
                                {improvement.before}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs text-text-tertiary mb-1">After:</div>
                              <div className="text-sm text-success bg-success/5 p-2 rounded border border-success/20">
                                {improvement.after}
                              </div>
                            </div>
                          </div>
                          {improvement.explanation && (
                            <div className="text-xs text-text-secondary bg-info/5 border border-info/20 rounded p-2">
                              <span className="font-semibold text-info">Why: </span>
                              {improvement.explanation}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 'error' && error && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-16 h-16 bg-error/10 rounded-full flex items-center justify-center mb-4">
                <AlertCircle size={32} className="text-error" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary mb-2">Analysis Failed</h3>
              <p className="text-text-secondary text-center max-w-md mb-4">{error}</p>
              <button
                onClick={analyzeDocumentation}
                className="btn btn-secondary text-sm"
              >
                Try Again
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-border flex items-center justify-end gap-3">
          {step === 'success' && (
            <>
              <button
                onClick={() => copyToClipboard(suggestions.improved_description, 'footer')}
                className="btn btn-secondary text-sm"
              >
                {copiedSection === 'footer' ? (
                  <>
                    <Check size={16} />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={16} />
                    <span>Copy Optimized</span>
                  </>
                )}
              </button>
              <button onClick={handleClose} className="btn btn-primary">
                <span>Done</span>
              </button>
            </>
          )}
          {step === 'error' && (
            <button onClick={handleClose} className="btn btn-secondary">
              <span>Close</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default OptimizeDocsModal
