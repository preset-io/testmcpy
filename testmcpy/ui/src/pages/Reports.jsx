import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import TraceView from '../components/TraceView'
import {
  FileText,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Trash2,
  Server,
  Cpu,
  Zap,
  AlertTriangle,
  Hash,
  Wrench,
  MessageSquare,
  BarChart3,
  ClipboardCheck,
  Link2,
  Download,
} from 'lucide-react'

const AUTO_REFRESH_INTERVAL = 10000

function formatDate(timestamp) {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString()
}

function formatDuration(seconds) {
  if (!seconds) return '0s'
  if (seconds < 0.1) return `${(seconds * 1000).toFixed(0)}ms`
  return `${seconds.toFixed(1)}s`
}

function formatCost(cost) {
  if (!cost) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}

function formatTokens(tokens) {
  if (!tokens) return '0'
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(0)}K`
  return tokens.toString()
}

function getPassRate(passed, total) {
  if (!total) return 0
  return (passed / total) * 100
}

function getPassRateColor(rate) {
  if (rate >= 90) return 'text-success'
  if (rate >= 70) return 'text-warning'
  return 'text-error'
}

function getPassRateBgColor(rate) {
  if (rate >= 90) return 'bg-success/20 text-success'
  if (rate >= 70) return 'bg-warning/20 text-warning'
  return 'bg-error/20 text-error'
}

function stripMcpPrefix(name) {
  if (!name) return name
  return name.replace(/^mcp__[^_]+__/, '')
}

// Collapsible section component
function CollapsibleSection({ title, icon: Icon, badge, defaultOpen = false, children, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={className}>
      <button
        className="flex items-center gap-2 w-full text-left py-1.5 hover:text-text-primary transition-colors"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown size={14} className="text-text-tertiary flex-shrink-0" /> : <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />}
        {Icon && <Icon size={14} className="text-text-secondary flex-shrink-0" />}
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wide">{title}</span>
        {badge !== undefined && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-surface-elevated text-text-tertiary">{badge}</span>
        )}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

// Tool call display
function ToolCallDisplay({ call, index }) {
  const [resultExpanded, setResultExpanded] = useState(false)
  const displayName = stripMcpPrefix(call.name)
  const args = call.arguments || call.input || {}
  const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2)
  const isEmptyArgs = !args || (typeof args === 'object' && Object.keys(args).length === 0)

  const result = call.result || call.output
  let resultStr = ''
  if (result) {
    if (typeof result === 'string') {
      resultStr = result
    } else if (result.content) {
      resultStr = typeof result.content === 'string' ? result.content : JSON.stringify(result.content, null, 2)
    } else {
      resultStr = JSON.stringify(result, null, 2)
    }
  }
  const isLongResult = resultStr.length > 300
  const isError = call.is_error || result?.is_error

  return (
    <div className="flex gap-2">
      <div className="flex flex-col items-center">
        <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${isError ? 'bg-error/20' : 'bg-primary/20'}`}>
          <Wrench size={10} className={isError ? 'text-error' : 'text-primary'} />
        </div>
        {/* connector line */}
        <div className="w-px flex-1 bg-border" />
      </div>
      <div className="flex-1 pb-3 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-sm font-medium text-primary">{displayName}</span>
          {isError && <span className="text-xs px-1.5 py-0.5 rounded bg-error/20 text-error">error</span>}
        </div>
        {!isEmptyArgs && (
          <pre className="text-xs font-mono bg-surface p-2 rounded border border-border overflow-x-auto mb-2 text-text-secondary">
            {argsStr}
          </pre>
        )}
        {isEmptyArgs && (
          <span className="text-xs text-text-disabled font-mono">(no arguments)</span>
        )}
        {resultStr && (
          <div className="mt-2">
            <span className="text-xs text-text-tertiary">Result:</span>
            {isLongResult && !resultExpanded ? (
              <div>
                <pre className="text-xs font-mono bg-surface p-2 rounded border border-border overflow-x-auto mt-1 text-text-secondary max-h-24 overflow-hidden">
                  {resultStr.substring(0, 300)}...
                </pre>
                <button
                  className="text-xs text-primary hover:underline mt-1"
                  onClick={() => setResultExpanded(true)}
                >
                  Show full result ({resultStr.length.toLocaleString()} chars)
                </button>
              </div>
            ) : (
              <pre className={`text-xs font-mono bg-surface p-2 rounded border border-border overflow-x-auto mt-1 max-h-96 overflow-y-auto ${isError ? 'text-error' : 'text-text-secondary'}`}>
                {resultStr}
              </pre>
            )}
            {isLongResult && resultExpanded && (
              <button
                className="text-xs text-primary hover:underline mt-1"
                onClick={() => setResultExpanded(false)}
              >
                Collapse
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Re-run modal for editing and re-running a test case
function RerunModal({ result, onClose }) {
  const [prompt, setPrompt] = useState(result.prompt || result.test_prompt || '')
  const [running, setRunning] = useState(false)
  const [rerunResult, setRerunResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRerun = async () => {
    if (!prompt.trim()) return
    setRunning(true)
    setError(null)
    setRerunResult(null)

    try {
      const res = await fetch('/api/tests/run-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          evaluators: (result.evaluations || []).map(e => ({
            name: e.evaluator || e.name || 'execution_successful',
            args: e.args || {},
          })),
        }),
      })

      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setRerunResult(data.result || data)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[80vh] bg-surface-elevated border border-border rounded-xl shadow-strong overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="font-semibold text-text-primary">Edit & Re-run: {result.test_name}</h3>
          <button onClick={onClose} className="p-1 hover:bg-surface-hover rounded text-text-tertiary">
            <XCircle size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="input w-full text-sm"
              rows={4}
              placeholder="Enter test prompt..."
            />
          </div>

          <button
            onClick={handleRerun}
            disabled={running || !prompt.trim()}
            className="btn btn-primary text-sm"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
            <span>{running ? 'Running...' : 'Re-run Test'}</span>
          </button>

          {error && (
            <div className="p-3 bg-error/10 border border-error/30 rounded-lg text-sm text-error">
              {error}
            </div>
          )}

          {/* Side-by-side comparison */}
          {rerunResult && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-3 rounded-lg border border-border bg-surface">
                <h4 className="text-xs font-semibold text-text-tertiary uppercase mb-2">Original</h4>
                <div className="flex items-center gap-2 mb-2">
                  {result.passed ? (
                    <span className="flex items-center gap-1 text-xs text-success"><CheckCircle size={12} /> PASS</span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-error"><XCircle size={12} /> FAIL</span>
                  )}
                  <span className="text-xs text-text-tertiary font-mono">{(result.score ?? (result.passed ? 1 : 0)).toFixed(2)}</span>
                </div>
                {result.error && <p className="text-xs text-error">{result.error}</p>}
              </div>
              <div className="p-3 rounded-lg border border-border bg-surface">
                <h4 className="text-xs font-semibold text-text-tertiary uppercase mb-2">Re-run</h4>
                <div className="flex items-center gap-2 mb-2">
                  {rerunResult.passed ? (
                    <span className="flex items-center gap-1 text-xs text-success"><CheckCircle size={12} /> PASS</span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-error"><XCircle size={12} /> FAIL</span>
                  )}
                  <span className="text-xs text-text-tertiary font-mono">{(rerunResult.score ?? (rerunResult.passed ? 1 : 0)).toFixed(2)}</span>
                </div>
                {rerunResult.error && <p className="text-xs text-error">{rerunResult.error}</p>}
                {rerunResult.duration && (
                  <p className="text-xs text-text-tertiary">{formatDuration(rerunResult.duration)}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Per-test expandable card
function TestResultCard({ result }) {
  const [expanded, setExpanded] = useState(!result.passed)
  const [showRerun, setShowRerun] = useState(false)
  const passRate = result.score !== undefined ? result.score : (result.passed ? 1.0 : 0.0)
  const toolCalls = result.tool_calls || []
  const evaluations = result.evaluations || []
  const evalsPassed = evaluations.filter(e => e.passed).length
  const failedEvals = evaluations.filter(e => !e.passed)
  const tokenUsage = result.token_usage?.total || result.token_usage?.input_tokens
    ? (result.token_usage.total || ((result.token_usage.input_tokens || 0) + (result.token_usage.output_tokens || 0)))
    : null

  // Find prompt from result - it may be in different places depending on data shape
  const prompt = result.prompt || result.test_prompt || null

  return (
    <div className={`border rounded-lg overflow-hidden ${result.passed ? 'border-border' : 'border-error/50 bg-error/5'}`}>
      {/* Header row */}
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {expanded
            ? <ChevronDown size={14} className="text-text-tertiary flex-shrink-0" />
            : <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />
          }
          <span className="font-medium text-sm text-text-primary truncate">{result.test_name}</span>
          {result.passed ? (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-success/20 text-success flex-shrink-0">
              <CheckCircle size={10} /> PASS
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-error/20 text-error flex-shrink-0">
              <XCircle size={10} /> FAIL
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-text-tertiary flex-shrink-0 ml-2">
          <span className="font-mono">{passRate.toFixed(2)}</span>
          {result.cost > 0 && <span className="font-mono">{formatCost(result.cost)}</span>}
          {tokenUsage && <span className="font-mono">{formatTokens(tokenUsage)}</span>}
          <span>{formatDuration(result.duration)}</span>
          <button
            onClick={(e) => { e.stopPropagation(); setShowRerun(true) }}
            className="px-2 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors text-[10px] font-medium"
            title="Edit & Re-run"
          >
            Re-run
          </button>
        </div>
      </div>
      {showRerun && <RerunModal result={result} onClose={() => setShowRerun(false)} />}

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border bg-surface-elevated px-4 py-3 space-y-4">
          {/* Prompt */}
          {prompt && (
            <div>
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-1">Prompt</p>
              <p className="text-sm text-text-primary bg-surface p-2 rounded border border-border">{prompt}</p>
            </div>
          )}

          {/* Failure Reason - show prominently for failed tests */}
          {!result.passed && failedEvals.length > 0 && (
            <div className="p-3 bg-error/10 border border-error/30 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} className="text-error" />
                <span className="text-xs font-semibold text-error uppercase tracking-wide">Failure Reason</span>
              </div>
              <div className="space-y-1">
                {failedEvals.map((ev, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <XCircle size={12} className="text-error mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-error">{ev.evaluator || ev.name}</span>
                      {ev.reason && <span className="text-sm text-error/80"> — {ev.reason}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {result.error && (
            <div className="p-3 bg-error/10 border border-error/30 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} className="text-error" />
                <span className="text-xs font-semibold text-error uppercase tracking-wide">Error</span>
              </div>
              <p className="text-sm text-error font-mono">{result.error}</p>
            </div>
          )}

          {/* Tool Calls */}
          {toolCalls.length > 0 && (
            <CollapsibleSection
              title="Tool Calls"
              icon={Wrench}
              badge={toolCalls.length}
              defaultOpen={true}
            >
              <div className="pl-1">
                {toolCalls.map((call, idx) => (
                  <ToolCallDisplay key={idx} call={call} index={idx} />
                ))}
              </div>
            </CollapsibleSection>
          )}

          {/* LLM Response */}
          {(result.response || result.llm_response) && (
            <CollapsibleSection
              title="LLM Response"
              icon={MessageSquare}
              defaultOpen={false}
            >
              <div className="prose prose-sm dark:prose-invert max-w-none p-3 bg-surface rounded-lg border border-border max-h-96 overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {typeof (result.response || result.llm_response) === 'string'
                    ? (result.response || result.llm_response)
                    : JSON.stringify((result.response || result.llm_response), null, 2)}
                </ReactMarkdown>
              </div>
            </CollapsibleSection>
          )}

          {/* Evaluations */}
          {evaluations.length > 0 && (
            <CollapsibleSection
              title="Evaluations"
              icon={ClipboardCheck}
              badge={`${evalsPassed}/${evaluations.length} passed`}
              defaultOpen={!result.passed}
            >
              <div className="space-y-1.5">
                {evaluations.map((ev, idx) => (
                  <div
                    key={idx}
                    className={`flex items-start gap-2 p-2 rounded-lg border ${
                      ev.passed
                        ? 'border-border bg-surface'
                        : 'border-error/30 bg-error/5'
                    }`}
                  >
                    {ev.passed ? (
                      <CheckCircle size={14} className="text-success mt-0.5 flex-shrink-0" />
                    ) : (
                      <XCircle size={14} className="text-error mt-0.5 flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className={`text-sm font-medium ${ev.passed ? 'text-text-primary' : 'text-error'}`}>
                          {ev.evaluator || ev.name || 'Unknown'}
                        </span>
                        {ev.score !== undefined && (
                          <span className="text-xs text-text-tertiary font-mono">
                            {(ev.score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      {ev.reason && (
                        <p className={`text-xs mt-0.5 ${ev.passed ? 'text-text-secondary' : 'text-error/80'}`}>
                          {ev.reason}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}

          {/* Metrics */}
          <CollapsibleSection
            title="Metrics"
            icon={BarChart3}
            defaultOpen={false}
          >
            <div className="flex flex-wrap gap-4 text-sm">
              <div className="flex items-center gap-1.5">
                <DollarSign size={14} className="text-text-tertiary" />
                <span className="text-text-secondary">Cost:</span>
                <span className="font-mono text-text-primary">{formatCost(result.cost)}</span>
              </div>
              {tokenUsage && (
                <div className="flex items-center gap-1.5">
                  <Hash size={14} className="text-text-tertiary" />
                  <span className="text-text-secondary">Tokens:</span>
                  <span className="font-mono text-text-primary">{tokenUsage.toLocaleString()}</span>
                </div>
              )}
              <div className="flex items-center gap-1.5">
                <Clock size={14} className="text-text-tertiary" />
                <span className="text-text-secondary">Duration:</span>
                <span className="font-mono text-text-primary">{formatDuration(result.duration)}</span>
              </div>
              {result.token_usage?.input_tokens && (
                <div className="flex items-center gap-1.5">
                  <span className="text-text-secondary">Input:</span>
                  <span className="font-mono text-text-primary">{result.token_usage.input_tokens.toLocaleString()}</span>
                </div>
              )}
              {result.token_usage?.output_tokens && (
                <div className="flex items-center gap-1.5">
                  <span className="text-text-secondary">Output:</span>
                  <span className="font-mono text-text-primary">{result.token_usage.output_tokens.toLocaleString()}</span>
                </div>
              )}
            </div>
          </CollapsibleSection>

          {/* Provider Logs */}
          {result.logs && result.logs.length > 0 && (
            <CollapsibleSection
              title="Provider Logs"
              badge={result.logs.length}
              defaultOpen={false}
            >
              <div className="p-3 bg-surface rounded-lg border border-border max-h-64 overflow-y-auto">
                <pre className="text-xs font-mono whitespace-pre-wrap">
                  {result.logs.map((log, idx) => (
                    <div key={idx} className={`leading-relaxed ${
                      log.includes('Error') || log.includes('error') ? 'text-red-400' :
                      log.includes('Tool call') || log.includes('tool') ? 'text-cyan-400' :
                      log.includes('success') || log.includes('Parsed') ? 'text-green-400' :
                      'text-text-secondary'
                    }`}>
                      {log}
                    </div>
                  ))}
                </pre>
              </div>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  )
}

// Smoke Test Result Card Component
function SmokeTestResultCard({ result }) {
  const [expanded, setExpanded] = useState(!result.success)

  return (
    <div className={`border rounded-lg overflow-hidden ${
      result.success ? 'border-border' : 'border-error/30'
    }`}>
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {result.success ? (
            <CheckCircle size={16} className="text-success" />
          ) : (
            <XCircle size={16} className="text-error" />
          )}
          <span className="font-medium">{result.test_name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-tertiary">
          <span>{result.duration_ms?.toFixed(0)}ms</span>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 border-t border-border bg-surface-elevated">
          {result.error_message && (
            <div className="mt-3 p-2 bg-error/10 border border-error/30 rounded">
              <p className="text-xs font-medium text-error mb-1">Error</p>
              <p className="text-sm text-error">{result.error_message}</p>
            </div>
          )}

          {result.tool_input && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-1">Input</p>
              <pre className="text-xs bg-surface p-2 rounded border border-border overflow-x-auto max-h-32">
                {JSON.stringify(result.tool_input, null, 2)}
              </pre>
            </div>
          )}

          {result.tool_output !== undefined && result.tool_output !== null && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-1">Output</p>
              <pre className="text-xs bg-surface p-2 rounded border border-border overflow-x-auto max-h-48">
                {typeof result.tool_output === 'string'
                  ? result.tool_output.substring(0, 2000)
                  : JSON.stringify(result.tool_output, null, 2)?.substring(0, 2000)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Reports() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState('tests')
  const [testRuns, setTestRuns] = useState([])
  const [smokeReports, setSmokeReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetails, setRunDetails] = useState(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [showTrace, setShowTrace] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const [filterStatus, setFilterStatus] = useState('all') // all, pass, fail
  const [filterSearch, setFilterSearch] = useState('')
  const autoRefreshRef = useRef(null)
  const deepLinkProcessed = useRef(false)

  const loadTestRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/results/list?limit=50')
      if (res.ok) {
        const data = await res.json()
        setTestRuns(data.runs || [])
      }
    } catch (error) {
      console.error('Failed to load test runs:', error)
    }
  }, [])

  const loadSmokeReports = useCallback(async () => {
    try {
      const res = await fetch('/api/smoke-reports/list?limit=50')
      if (res.ok) {
        const data = await res.json()
        setSmokeReports(data.reports || [])
      }
    } catch (error) {
      console.error('Failed to load smoke reports:', error)
    }
  }, [])

  const loadAllReports = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    await Promise.all([loadTestRuns(), loadSmokeReports()])
    if (showSpinner) setLoading(false)
  }, [loadTestRuns, loadSmokeReports])

  // Initial load
  useEffect(() => {
    loadAllReports()
  }, [loadAllReports])

  // Deep-link: load run from URL params after data loads
  useEffect(() => {
    if (deepLinkProcessed.current) return
    if (loading) return
    const runParam = searchParams.get('run')
    const typeParam = searchParams.get('type') || 'tests'
    if (runParam) {
      deepLinkProcessed.current = true
      setActiveTab(typeParam)
      loadRunDetails(runParam, typeParam)
    }
  }, [loading, searchParams])

  // Update URL when selecting a run
  const selectRun = useCallback((runId, type) => {
    setSearchParams({ run: runId, type }, { replace: true })
    loadRunDetails(runId, type)
  }, [setSearchParams])

  // Copy shareable link
  const copyRunLink = useCallback((runId, type) => {
    const url = new URL(window.location.href)
    url.searchParams.set('run', runId)
    url.searchParams.set('type', type)
    navigator.clipboard.writeText(url.toString()).then(() => {
      setCopiedLink(true)
      setTimeout(() => setCopiedLink(false), 2000)
    })
  }, [])

  // Export run as JSON
  const exportRunJson = useCallback(() => {
    if (!runDetails) return
    const blob = new Blob([JSON.stringify(runDetails, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${selectedRun?.id || 'export'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [runDetails, selectedRun])

  // Export run as CSV
  const exportRunCsv = useCallback(() => {
    if (!runDetails) return
    const results = runDetails.results || []
    if (results.length === 0) return

    const headers = ['test_name', 'passed', 'score', 'duration', 'cost', 'error']
    const rows = results.map(r => [
      r.test_name || r.name || '',
      r.passed ?? r.success ?? '',
      r.score ?? '',
      r.duration ?? (r.duration_ms ? r.duration_ms / 1000 : '') ?? '',
      r.cost ?? '',
      (r.error || '').replace(/"/g, '""'),
    ])

    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${selectedRun?.id || 'export'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [runDetails, selectedRun])

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      autoRefreshRef.current = setInterval(() => {
        loadAllReports(false)
      }, AUTO_REFRESH_INTERVAL)
    }
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [autoRefresh, loadAllReports])

  const loadRunDetails = async (runId, type) => {
    setLoadingDetails(true)
    setSelectedRun({ id: runId, type })
    try {
      const endpoint = type === 'tests'
        ? `/api/results/run/${runId}`
        : `/api/smoke-reports/report/${runId}`
      const res = await fetch(endpoint)
      if (res.ok) {
        const data = await res.json()
        setRunDetails(data)
      }
    } catch (error) {
      console.error('Failed to load run details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const deleteRun = async (runId, type) => {
    if (!confirm('Delete this report?')) return
    try {
      const endpoint = type === 'tests'
        ? `/api/results/run/${runId}`
        : `/api/smoke-reports/report/${runId}`
      await fetch(endpoint, { method: 'DELETE' })
      if (type === 'tests') {
        setTestRuns(prev => prev.filter(r => r.run_id !== runId))
      } else {
        setSmokeReports(prev => prev.filter(r => r.report_id !== runId))
      }
      if (selectedRun?.id === runId) {
        setSelectedRun(null)
        setRunDetails(null)
      }
    } catch (error) {
      console.error('Failed to delete:', error)
    }
  }

  // Filtered test runs
  const filteredTestRuns = testRuns.filter(run => {
    if (filterStatus === 'pass' && run.failed > 0) return false
    if (filterStatus === 'fail' && run.failed === 0) return false
    if (filterSearch && !run.test_file?.toLowerCase().includes(filterSearch.toLowerCase()) &&
        !run.model?.toLowerCase().includes(filterSearch.toLowerCase())) return false
    return true
  })

  const filteredSmokeReports = smokeReports.filter(report => {
    if (filterStatus === 'pass' && report.failed > 0) return false
    if (filterStatus === 'fail' && report.failed === 0) return false
    if (filterSearch && !report.profile_id?.toLowerCase().includes(filterSearch.toLowerCase())) return false
    return true
  })

  const renderRunListItem = (run) => {
    const rate = getPassRate(run.passed, run.total_tests)
    const rateBg = getPassRateBgColor(rate)
    return (
      <div
        key={run.run_id}
        className={`p-4 cursor-pointer transition-colors group ${
          selectedRun?.id === run.run_id
            ? 'bg-primary/10 border-l-2 border-l-primary'
            : 'hover:bg-surface border-l-2 border-l-transparent'
        }`}
        onClick={() => selectRun(run.run_id, 'tests')}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {run.failed === 0 ? (
                <CheckCircle size={14} className="text-success flex-shrink-0" />
              ) : (
                <XCircle size={14} className="text-error flex-shrink-0" />
              )}
              <span className="font-medium text-text-primary truncate text-sm">
                {run.test_file}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${rateBg}`}>
                {run.passed}/{run.total_tests} ({rate.toFixed(0)}%)
              </span>
              {run.total_cost > 0 && (
                <span className="text-xs text-text-tertiary font-mono flex items-center gap-0.5">
                  <DollarSign size={10} />{formatCost(run.total_cost)}
                </span>
              )}
              {run.total_tokens > 0 && (
                <span className="text-xs text-text-tertiary font-mono flex items-center gap-0.5">
                  <Hash size={10} />{formatTokens(run.total_tokens)}
                </span>
              )}
              {run.total_duration > 0 && (
                <span className="text-xs text-text-tertiary font-mono flex items-center gap-0.5">
                  <Clock size={10} />{formatDuration(run.total_duration)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1.5 text-xs text-text-disabled">
              <span className="flex items-center gap-1">
                <Cpu size={10} />
                {run.model || 'unknown'}
              </span>
              {run.provider && (
                <span className="text-text-disabled">{run.provider}</span>
              )}
            </div>
            <div className="text-xs text-text-disabled mt-1">
              {formatDate(run.timestamp)}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              deleteRun(run.run_id, 'tests')
            }}
            className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <Trash2 size={14} className="text-error" />
          </button>
        </div>
      </div>
    )
  }

  const renderTestRunDetails = () => {
    if (!runDetails) return null
    const meta = runDetails.metadata || {}
    const results = runDetails.results || []
    const rate = getPassRate(meta.passed, meta.total_tests)
    const rateColor = getPassRateColor(rate)

    return (
      <div className="p-6 space-y-6">
        {/* Summary Card */}
        <div className="p-5 rounded-xl bg-surface border border-border">
          <h2 className="text-lg font-bold text-text-primary mb-2">{meta.test_file}</h2>
          <div className="flex items-center gap-2 flex-wrap text-sm text-text-secondary mb-3">
            <span className="flex items-center gap-1">
              <Cpu size={14} className="text-text-tertiary" />
              {meta.model}
            </span>
            <span className="text-text-disabled">|</span>
            <span className="text-text-tertiary">{meta.provider}</span>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <span className={`text-sm font-semibold ${meta.failed === 0 ? 'text-success' : 'text-error'}`}>
              {meta.passed}/{meta.total_tests} passed
            </span>
            <span className={`text-sm font-bold ${rateColor}`}>
              {rate.toFixed(0)}%
            </span>
            <span className="text-sm text-text-secondary font-mono flex items-center gap-1">
              <DollarSign size={14} className="text-text-tertiary" />
              {formatCost(meta.total_cost)}
            </span>
            <span className="text-sm text-text-secondary font-mono flex items-center gap-1">
              <Hash size={14} className="text-text-tertiary" />
              {formatTokens(meta.total_tokens)}
            </span>
            <span className="text-sm text-text-secondary font-mono flex items-center gap-1">
              <Clock size={14} className="text-text-tertiary" />
              {formatDuration(meta.total_duration)}
            </span>
          </div>
          <div className="text-xs text-text-disabled mt-2">{formatDate(meta.timestamp)}</div>
        </div>

        {/* Pass/Fail summary bar */}
        {meta.total_tests > 0 && (
          <div className="flex rounded-full overflow-hidden h-2">
            {meta.passed > 0 && (
              <div
                className="bg-success"
                style={{ width: `${(meta.passed / meta.total_tests) * 100}%` }}
              />
            )}
            {meta.failed > 0 && (
              <div
                className="bg-error"
                style={{ width: `${(meta.failed / meta.total_tests) * 100}%` }}
              />
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowTrace(!showTrace)}
            className={`text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
              showTrace
                ? 'bg-primary text-white'
                : 'bg-surface border border-border text-text-secondary hover:bg-surface-hover'
            }`}
          >
            <Clock size={12} />
            {showTrace ? 'Hide Trace' : 'View Trace'}
          </button>
          <button
            onClick={() => copyRunLink(selectedRun.id, selectedRun.type)}
            className="text-xs px-3 py-1.5 rounded-lg bg-surface border border-border text-text-secondary hover:bg-surface-hover transition-colors flex items-center gap-1.5"
          >
            <Link2 size={12} />
            {copiedLink ? 'Copied!' : 'Copy Link'}
          </button>
          <button
            onClick={exportRunJson}
            className="text-xs px-3 py-1.5 rounded-lg bg-surface border border-border text-text-secondary hover:bg-surface-hover transition-colors flex items-center gap-1.5"
          >
            <Download size={12} />
            JSON
          </button>
          <button
            onClick={exportRunCsv}
            className="text-xs px-3 py-1.5 rounded-lg bg-surface border border-border text-text-secondary hover:bg-surface-hover transition-colors flex items-center gap-1.5"
          >
            <Download size={12} />
            CSV
          </button>
        </div>

        {/* Trace View */}
        {showTrace && selectedRun?.id && (
          <TraceView runId={selectedRun.id} onClose={() => setShowTrace(false)} />
        )}

        {/* Test Results */}
        <div>
          <h3 className="font-semibold text-text-primary mb-3">
            Test Results ({results.length})
          </h3>
          <div className="space-y-2">
            {results.map((result, idx) => (
              <TestResultCard key={idx} result={result} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  const renderSmokeDetails = () => {
    if (!runDetails) return null
    return (
      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-text-primary">Smoke Test Report</h2>
          <div className="flex items-center gap-4 mt-2 text-sm text-text-secondary">
            <span className="flex items-center gap-1">
              <Server size={14} />
              {runDetails.server_url}
            </span>
            <span className="flex items-center gap-1">
              <Clock size={14} />
              {formatDuration(runDetails.duration_ms / 1000)}
            </span>
          </div>
        </div>

        <div className={`p-4 rounded-lg border mb-6 ${
          runDetails.failed === 0
            ? 'bg-success/10 border-success/30'
            : 'bg-error/10 border-error/30'
        }`}>
          <div className="flex items-center gap-3">
            {runDetails.failed === 0 ? (
              <CheckCircle size={24} className="text-success" />
            ) : (
              <XCircle size={24} className="text-error" />
            )}
            <div>
              <h3 className="font-bold">
                {runDetails.failed === 0 ? 'All Tests Passed' : `${runDetails.passed}/${runDetails.total_tests} Passed`}
              </h3>
              <p className="text-sm text-text-secondary">
                Success Rate: {runDetails.success_rate?.toFixed(1)}%
              </p>
            </div>
          </div>
        </div>

        <h3 className="font-semibold mb-3">Test Details</h3>
        <div className="space-y-2">
          {runDetails.results?.map((result, idx) => (
            <SmokeTestResultCard key={idx} result={result} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <FileText size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-semibold text-text-primary">Reports</h1>
              <p className="text-sm text-text-tertiary">View all test results and smoke test reports</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-text-tertiary cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded border-border"
              />
              Auto-refresh
            </label>
            <button
              onClick={() => loadAllReports()}
              className="btn btn-ghost"
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-2 mt-4">
          <button
            onClick={() => setActiveTab('tests')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'tests'
                ? 'bg-primary text-white'
                : 'bg-surface hover:bg-surface-hover text-text-secondary'
            }`}
          >
            <FileText size={16} />
            Test Runs
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === 'tests' ? 'bg-surface-hover' : 'bg-surface-elevated'
            }`}>
              {testRuns.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('smoke')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'smoke'
                ? 'bg-primary text-white'
                : 'bg-surface hover:bg-surface-hover text-text-secondary'
            }`}
          >
            <Zap size={16} />
            Smoke Tests
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === 'smoke' ? 'bg-surface-hover' : 'bg-surface-elevated'
            }`}>
              {smokeReports.length}
            </span>
          </button>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-3 mt-3 flex-wrap">
          <input
            type="text"
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            placeholder="Filter by name or model..."
            className="input text-xs py-1.5 px-3 w-48"
          />
          <div className="flex items-center gap-1">
            {['all', 'pass', 'fail'].map(status => (
              <button
                key={status}
                onClick={() => setFilterStatus(status)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  filterStatus === status
                    ? status === 'pass' ? 'bg-success/20 text-success' : status === 'fail' ? 'bg-error/20 text-error' : 'bg-primary/20 text-primary'
                    : 'bg-surface hover:bg-surface-hover text-text-secondary'
                }`}
              >
                {status === 'all' ? 'All' : status === 'pass' ? 'Passed' : 'Failed'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* List Panel */}
        <div className={`w-full md:w-96 flex-shrink-0 border-b md:border-b-0 md:border-r border-border overflow-auto bg-surface-elevated ${selectedRun ? 'hidden md:block' : 'block'}`}>
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : activeTab === 'tests' ? (
            testRuns.length === 0 ? (
              <div className="p-8 text-center">
                <FileText size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">No test runs found</p>
                <p className="text-text-disabled text-sm mt-1">Run some tests to see results here</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filteredTestRuns.map(renderRunListItem)}
              </div>
            )
          ) : (
            smokeReports.length === 0 ? (
              <div className="p-8 text-center">
                <Zap size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">No smoke test reports found</p>
                <p className="text-text-disabled text-sm mt-1">Run a smoke test to see results here</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filteredSmokeReports.map((report) => (
                  <div
                    key={report.report_id}
                    className={`p-4 cursor-pointer transition-colors group ${
                      selectedRun?.id === report.report_id
                        ? 'bg-primary/10 border-l-2 border-l-primary'
                        : 'hover:bg-surface border-l-2 border-l-transparent'
                    }`}
                    onClick={() => selectRun(report.report_id, 'smoke')}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {report.failed === 0 ? (
                            <CheckCircle size={14} className="text-success flex-shrink-0" />
                          ) : (
                            <XCircle size={14} className="text-error flex-shrink-0" />
                          )}
                          <span className="font-medium text-text-primary truncate">
                            {report.profile_id || 'Smoke Test'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            report.failed === 0 ? 'bg-success/20 text-success' : 'bg-error/20 text-error'
                          }`}>
                            {report.passed}/{report.total_tests} passed
                          </span>
                          <span className="text-xs text-text-tertiary">
                            {report.success_rate?.toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-xs text-text-disabled">
                          <span className="flex items-center gap-1">
                            <Server size={10} />
                            {report.server_url?.split('/').pop() || 'MCP Server'}
                          </span>
                          <span>{formatDuration(report.duration_ms / 1000)}</span>
                        </div>
                        <div className="text-xs text-text-disabled mt-1">
                          {formatDate(report.timestamp)}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          deleteRun(report.report_id, 'smoke')
                        }}
                        className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 size={14} className="text-error" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        {/* Details Panel */}
        <div className={`flex-1 overflow-auto bg-background ${selectedRun ? 'block' : 'hidden md:block'}`}>
          {selectedRun && (
            <button onClick={() => { setSelectedRun(null); setRunDetails(null) }} className="md:hidden flex items-center gap-2 px-4 py-3 text-sm text-text-secondary hover:text-text-primary border-b border-border w-full">
              <ChevronRight size={16} className="rotate-180" />
              <span>Back to list</span>
            </button>
          )}
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : !runDetails ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <FileText size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">Select a report to view details</p>
              </div>
            </div>
          ) : selectedRun?.type === 'tests' ? (
            renderTestRunDetails()
          ) : (
            renderSmokeDetails()
          )}
        </div>
      </div>
    </div>
  )
}

export default Reports
