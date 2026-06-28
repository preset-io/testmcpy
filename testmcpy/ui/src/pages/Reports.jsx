import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useConfirm } from '../components/ConfirmDialog'
import { useNotification } from '../components/NotificationProvider'
import { useSearchParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import TraceView from '../components/TraceView'
import Badge from '../components/Badge'
import ScoreBreakdown from '../components/ScoreBreakdown'
import { Skeleton, ListItemSkeleton } from '../components/SkeletonLoader'
import { formatDate, formatDuration, formatCost, formatTokens } from '../utils/formatters'
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
  CheckSquare,
  Copy,
  Check,
} from 'lucide-react'

const AUTO_REFRESH_INTERVAL = 10000

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
          <Badge>{badge}</Badge>
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
          {isError && <Badge variant="error">error</Badge>}
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
function TestResultCard({ result, providerHint, onFpToggle }) {
  const [expanded, setExpanded] = useState(!result.passed)
  const [showRerun, setShowRerun] = useState(false)
  const [fpLoading, setFpLoading] = useState(false)
  const score = result.score !== undefined ? result.score : (result.passed ? 1.0 : 0.0)
  const breakdown = result.score_breakdown || null
  const toolCalls = result.tool_calls || []
  const evaluations = result.evaluations || []
  const evalsPassed = evaluations.filter(e => e.passed).length
  const failedEvals = evaluations.filter(e => !e.passed)
  const hasPenalty = !!breakdown && breakdown.penalty_source && breakdown.final_score < breakdown.base_score - 0.0001

  // One-sentence plain-English verdict so users don't have to decode the
  // score themselves. Covers the subtle "passed but lost points to extra
  // tool calls" case that the bare number hides.
  let verdictText
  if (result.passed) {
    verdictText = hasPenalty
      ? 'All checks passed, but points were lost to unexpected tool calls.'
      : 'All evaluator checks passed.'
  } else {
    const names = failedEvals.map(e => e.evaluator || e.name).filter(Boolean)
    verdictText = names.length
      ? `Failed: ${names.join(', ')}.`
      : 'Failed — see the breakdown below.'
  }
  const tokenUsage = result.token_usage?.total || result.token_usage?.input_tokens
    ? (result.token_usage.total || ((result.token_usage.input_tokens || 0) + (result.token_usage.output_tokens || 0)))
    : null

  // Find prompt from result - it may be in different places depending on data shape
  const prompt = result.prompt || result.test_prompt || null

  // The chatbot/assistant provider's endpoint doesn't return cost or
  // token counts. Showing "$0.00" / "0 tokens" reads as "the run was
  // free" which misleads users (SC-108367 #2). Treat these as
  // "not tracked" and render an em-dash with a tooltip instead.
  const isChatbotProvider = providerHint === 'assistant' || providerHint === 'chatbot'
  const costNotTracked = isChatbotProvider && (!result.cost || result.cost === 0)
  const tokensNotTracked = isChatbotProvider && !tokenUsage
  const hasResponse = !!(result.response || result.llm_response)

  // False positive state (optimistic)
  const [isFp, setIsFp] = useState(!!(result.manual_false_positive))
  const [fpRate, setFpRate] = useState(result.false_positive_rate ?? 0)
  const showFpBadge = isFp

  const handleFpToggle = async (e) => {
    e.stopPropagation()
    if (!result.id && !result.question_id) return
    const questionId = result.id || result.question_id
    const newValue = !isFp
    setIsFp(newValue)
    setFpLoading(true)
    try {
      await fetch(`/api/metrics/question/${questionId}/false-positive?is_false_positive=${newValue}`, { method: 'PATCH' })
      if (onFpToggle) onFpToggle(questionId, newValue)
    } catch (err) {
      // revert on error
      setIsFp(!newValue)
    } finally {
      setFpLoading(false)
    }
  }

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
          {showFpBadge && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 flex-shrink-0 font-semibold">
              FP
            </span>
          )}
        </div>
        <div className="flex items-center flex-wrap gap-3 text-xs text-text-tertiary flex-shrink-0 ml-2">
          <span
            className={`font-mono ${hasPenalty ? 'text-warning' : ''}`}
            title={
              hasPenalty
                ? `Final score after a false-positive tool-call penalty. Base (evaluator average) was ${breakdown.base_score.toFixed(2)}; expand for the breakdown.`
                : 'Final score = average of all evaluator scores (0.00–1.00). Expand for the breakdown.'
            }
          >
            <span className="text-text-disabled">score </span>
            {score.toFixed(2)}
            <span className="text-text-disabled">/1.00</span>
            {hasPenalty && <Zap size={10} className="inline ml-0.5 -mt-0.5" />}
          </span>
          {result.cost > 0 ? (
            <span className="font-mono" title="Estimated LLM call cost">{formatCost(result.cost)}</span>
          ) : costNotTracked ? (
            <span className="font-mono text-text-disabled" title="Cost not reported by the chatbot/assistant provider">— cost</span>
          ) : null}
          {tokenUsage ? (
            <span className="font-mono" title="Total tokens (input + output)">{formatTokens(tokenUsage)}</span>
          ) : tokensNotTracked ? (
            <span className="font-mono text-text-disabled" title="Token counts not reported by the chatbot/assistant provider">— tokens</span>
          ) : null}
          <span title="Wall-clock duration of the test (excluding wait times)">{formatDuration(result.duration)}</span>
          {(result.id || result.question_id) && (
            <button
              onClick={handleFpToggle}
              disabled={fpLoading}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                isFp
                  ? 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/30'
                  : 'bg-surface border border-border text-text-disabled hover:text-text-secondary'
              }`}
              title={isFp ? 'Unmark as False Positive' : 'Mark as False Positive'}
            >
              {fpLoading ? '...' : isFp ? 'Unmark FP' : 'Mark as FP'}
            </button>
          )}
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
          {/* Verdict banner — the one-glance "what happened and why" so the
              user doesn't have to decode the raw score. Prompt → Answer →
              Why-this-score follow below in that order. */}
          <div className={`flex items-start gap-2.5 p-3 rounded-lg border ${
            result.passed ? 'bg-success/5 border-success/30' : 'bg-error/5 border-error/30'
          }`}>
            {result.passed
              ? <CheckCircle size={18} className="text-success flex-shrink-0 mt-0.5" />
              : <XCircle size={18} className="text-error flex-shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className={`text-sm font-semibold ${result.passed ? 'text-success' : 'text-error'}`}>
                  {result.passed ? 'PASS' : 'FAIL'}
                </span>
                <span className="font-mono text-sm">
                  <span className={result.passed && !hasPenalty ? 'text-success' : hasPenalty ? 'text-warning' : 'text-error'}>
                    {score.toFixed(2)}
                  </span>
                  <span className="text-text-disabled"> / 1.00</span>
                </span>
              </div>
              <p className="text-sm text-text-secondary mt-0.5">{verdictText}</p>
            </div>
          </div>

          {/* Prompt — surfaced at the top so users can see what the
              test actually asked for at a glance. Missing for old runs
              saved before SC-108367 — show a "(not recorded)" hint then
              rather than silently omitting the section so users know
              what they're missing. */}
          <div>
            <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-1 flex items-center gap-1.5">
              <MessageSquare size={12} />
              User Prompt
            </p>
            {prompt ? (
              <p className="text-sm text-text-primary bg-surface p-3 rounded border border-primary/30 whitespace-pre-wrap">
                {prompt}
              </p>
            ) : (
              <p className="text-xs italic text-text-disabled bg-surface p-2 rounded border border-border">
                Prompt not recorded for this run. Open <span className="font-mono">{result.test_name}</span> in the
                test YAML to see what was asked, or re-run the test with v0.7.24+ to capture it.
              </p>
            )}
          </div>

          {/* Assistant Response — the most relevant signal for chatbot
              tests. Default-OPEN so users don't have to click. */}
          {hasResponse ? (
            <CollapsibleSection
              title="Assistant Response"
              icon={MessageSquare}
              defaultOpen={true}
            >
              <div className="prose prose-sm dark:prose-invert max-w-none p-3 bg-surface rounded-lg border border-success/30 max-h-96 overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {typeof (result.response || result.llm_response) === 'string'
                    ? (result.response || result.llm_response)
                    : JSON.stringify((result.response || result.llm_response), null, 2)}
                </ReactMarkdown>
              </div>
            </CollapsibleSection>
          ) : (
            <div>
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-1 flex items-center gap-1.5">
                <MessageSquare size={12} />
                Assistant Response
              </p>
              <p className="text-xs italic text-text-disabled bg-surface p-2 rounded border border-warning/30">
                Empty response.
                {toolCalls.length > 0
                  ? ` The assistant ran ${toolCalls.length} tool call${toolCalls.length === 1 ? '' : 's'} but never produced final text — see tool calls below.`
                  : ' The assistant produced no text and made no tool calls — likely a guardrail refusal or backend error.'}
              </p>
            </div>
          )}

          {/* Why this score — authoritative explainer (base × penalty =
              final) so the number is never a mystery. */}
          {breakdown && <ScoreBreakdown breakdown={breakdown} />}

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

          {/* (Assistant Response section moved above the tool calls
              so the "what did the model say" answer is the FIRST thing
              the user sees after the prompt.) */}

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
  const [confirmAction, confirmElement] = useConfirm()
  const { success: notifySuccess, error: notifyError, warning: notifyWarning, info: notifyInfo } = useNotification()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState('tests')
  const [testRuns, setTestRuns] = useState([])
  const [smokeReports, setSmokeReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [runsTotal, setRunsTotal] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadedCountRef = useRef(0)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetails, setRunDetails] = useState(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [showTrace, setShowTrace] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const [filterStatus, setFilterStatus] = useState('all') // all, pass, fail
  const [filterSearch, setFilterSearch] = useState('')
  // Server-side filters
  const [filterModel, setFilterModel] = useState('')
  const [filterProvider, setFilterProvider] = useState('')
  const [filterTestFile, setFilterTestFile] = useState('')
  const [filterOptions, setFilterOptions] = useState({ models: [], providers: [], test_files: [] })
  // Bulk selection
  const [selectMode, setSelectMode] = useState(false)
  const [selectedRuns, setSelectedRuns] = useState(new Set())
  // Empty-state copyable command
  const [copiedCmd, setCopiedCmd] = useState(false)
  const autoRefreshRef = useRef(null)
  const deepLinkProcessed = useRef(false)
  // run_id/report_id of a deep-linked run whose list item still needs to be
  // scrolled into view once it renders (cleared after the scroll happens)
  const pendingScrollRunId = useRef(null)

  const loadFilterOptions = useCallback(async () => {
    try {
      const res = await fetch('/api/results/filters')
      if (res.ok) {
        const data = await res.json()
        setFilterOptions(data)
      }
    } catch (error) {
      console.error('Failed to load filter options:', error)
    }
  }, [])

  const loadTestRuns = useCallback(async () => {
    try {
      // Refetch everything loaded so far so auto-refresh doesn't collapse
      // previously loaded pages back to the first one
      const params = new URLSearchParams({ limit: String(Math.max(100, loadedCountRef.current)) })
      if (filterModel) params.set('model', filterModel)
      if (filterProvider) params.set('provider', filterProvider)
      if (filterTestFile) params.set('test_file', filterTestFile)
      const res = await fetch(`/api/results/list?${params}`)
      if (res.ok) {
        const data = await res.json()
        const runs = data.runs || []
        setTestRuns(runs)
        loadedCountRef.current = runs.length
        setRunsTotal(data.total ?? runs.length)
      }
    } catch (error) {
      console.error('Failed to load test runs:', error)
    }
  }, [filterModel, filterProvider, filterTestFile])

  const loadMoreRuns = useCallback(async () => {
    setLoadingMore(true)
    try {
      const params = new URLSearchParams({
        limit: '100',
        offset: String(loadedCountRef.current),
      })
      if (filterModel) params.set('model', filterModel)
      if (filterProvider) params.set('provider', filterProvider)
      if (filterTestFile) params.set('test_file', filterTestFile)
      const res = await fetch(`/api/results/list?${params}`)
      if (res.ok) {
        const data = await res.json()
        const next = data.runs || []
        // New runs arriving between pages shift offset-based pagination —
        // dedupe by run_id so rows (and React keys) never repeat.
        setTestRuns(prev => {
          const seen = new Set(prev.map(r => r.run_id))
          return [...prev, ...next.filter(r => !seen.has(r.run_id))]
        })
        loadedCountRef.current += next.length
        setRunsTotal(data.total ?? loadedCountRef.current)
      }
    } catch (error) {
      console.error('Failed to load more runs:', error)
    } finally {
      setLoadingMore(false)
    }
  }, [filterModel, filterProvider, filterTestFile])

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
    await Promise.all([loadTestRuns(), loadSmokeReports(), loadFilterOptions()])
    if (showSpinner) setLoading(false)
  }, [loadTestRuns, loadSmokeReports, loadFilterOptions])

  // Initial load — run once
  const initialLoadDone = useRef(false)
  useEffect(() => {
    if (!initialLoadDone.current) {
      initialLoadDone.current = true
      loadAllReports()
    }
  }, [loadAllReports])

  // Reload only test runs when filters change (skip smoke/filters refetch)
  const filtersInitialized = useRef(false)
  useEffect(() => {
    if (!filtersInitialized.current) {
      filtersInitialized.current = true
      return  // skip first render — initial load handles it
    }
    loadedCountRef.current = 0  // filters changed — start from the first page
    loadTestRuns()
  }, [filterModel, filterProvider, filterTestFile]) // eslint-disable-line react-hooks/exhaustive-deps

  // Deep-link: load run from URL params after data loads
  useEffect(() => {
    if (deepLinkProcessed.current) return
    if (loading) return
    const runParam = searchParams.get('run')
    const typeParam = searchParams.get('type') || 'tests'
    if (runParam) {
      deepLinkProcessed.current = true
      pendingScrollRunId.current = runParam
      setActiveTab(typeParam)
      loadRunDetails(runParam, typeParam)
    }
  }, [loading, searchParams])

  // Scroll the deep-linked run's list item into view once it renders.
  // Used as a callback ref on each list item; inline arrows re-fire on every
  // render, so this also catches items that appear after the deep-link effect.
  const scrollPendingRunIntoView = (el, id) => {
    if (el && id && pendingScrollRunId.current === id) {
      pendingScrollRunId.current = null
      el.scrollIntoView?.({ block: 'center' })
    }
  }

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
    if (!(await confirmAction({ title: 'Delete report', message: 'Delete this report?' }))) return
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

  const toggleSelectMode = () => {
    setSelectMode(prev => !prev)
    setSelectedRuns(new Set())
  }

  const toggleSelectRun = (runId) => {
    setSelectedRuns(prev => {
      const next = new Set(prev)
      next.has(runId) ? next.delete(runId) : next.add(runId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedRuns.size === filteredTestRuns.length) {
      setSelectedRuns(new Set())
    } else {
      setSelectedRuns(new Set(filteredTestRuns.map(r => r.run_id)))
    }
  }

  const deleteSelected = async () => {
    if (selectedRuns.size === 0) return
    if (!(await confirmAction({ title: 'Delete runs', message: `Delete ${selectedRuns.size} run${selectedRuns.size > 1 ? 's' : ''}?` }))) return
    try {
      const res = await fetch('/api/results/runs/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: [...selectedRuns] }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        notifyError(`Delete failed: ${err.detail || res.statusText}`)
        return
      }
      if (selectedRuns.has(selectedRun?.id)) {
        setSelectedRun(null)
        setRunDetails(null)
      }
      setSelectedRuns(new Set())
      setSelectMode(false)
      // Re-fetch from the server (SC-108367 #1). The list endpoint is
      // capped at limit=100; if the user deletes the 100 visible rows
      // and we only filter locally, the next 100 stay hidden until they
      // reload. Re-fetch + refresh the filter counts so the page state
      // matches the DB.
      await Promise.all([loadTestRuns(), loadFilterOptions()])
    } catch (error) {
      console.error('Bulk delete failed:', error)
      notifyError(`Delete failed: ${error.message || error}`)
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
    const isSelected = selectedRuns.has(run.run_id)
    return (
      <div
        key={run.run_id}
        ref={el => scrollPendingRunIntoView(el, run.run_id)}
        className={`p-4 cursor-pointer transition-colors group ${
          selectMode && isSelected
            ? 'bg-primary/10 border-l-2 border-l-primary'
            : selectedRun?.id === run.run_id
            ? 'bg-primary/10 border-l-2 border-l-primary'
            : 'hover:bg-surface border-l-2 border-l-transparent'
        }`}
        onClick={() => selectMode ? toggleSelectRun(run.run_id) : selectRun(run.run_id, 'tests')}
      >
        <div className="flex items-start justify-between gap-2">
          {selectMode && (
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => toggleSelectRun(run.run_id)}
              onClick={(e) => e.stopPropagation()}
              className="mt-1 flex-shrink-0 accent-primary"
            />
          )}
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
          {!selectMode && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                deleteRun(run.run_id, 'tests')
              }}
              className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <Trash2 size={14} className="text-error" />
            </button>
          )}
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
            <span
              className={`text-sm font-semibold ${meta.failed === 0 ? 'text-success' : 'text-error'}`}
              title="Tests that passed all their evaluators"
            >
              {meta.passed}/{meta.total_tests} passed
            </span>
            <span
              className={`text-sm font-bold ${rateColor}`}
              title="Pass rate across all tests in this run"
            >
              {rate.toFixed(0)}%
            </span>
            {(() => {
              // chatbot/assistant provider doesn't report cost/tokens — show
              // "—" with a tooltip rather than a misleading "$0.00" / "0".
              // SC-108367 #2.
              const isChatbotProvider = meta.provider === 'assistant' || meta.provider === 'chatbot'
              const costNotTracked = isChatbotProvider && (!meta.total_cost || meta.total_cost === 0)
              const tokensNotTracked = isChatbotProvider && (!meta.total_tokens || meta.total_tokens === 0)
              return (
                <>
                  {costNotTracked ? (
                    <span
                      className="text-sm text-text-disabled font-mono flex items-center gap-1"
                      title="Cost not reported by the chatbot/assistant provider"
                    >
                      <DollarSign size={14} />— cost
                    </span>
                  ) : (
                    <span
                      className="text-sm text-text-secondary font-mono flex items-center gap-1"
                      title="Total LLM cost (sum of per-test costs)"
                    >
                      <DollarSign size={14} className="text-text-tertiary" />
                      {formatCost(meta.total_cost)}
                    </span>
                  )}
                  {tokensNotTracked ? (
                    <span
                      className="text-sm text-text-disabled font-mono flex items-center gap-1"
                      title="Token counts not reported by the chatbot/assistant provider"
                    >
                      <Hash size={14} />— tokens
                    </span>
                  ) : (
                    <span
                      className="text-sm text-text-secondary font-mono flex items-center gap-1"
                      title="Total tokens (input + output)"
                    >
                      <Hash size={14} className="text-text-tertiary" />
                      {formatTokens(meta.total_tokens)}
                    </span>
                  )}
                </>
              )
            })()}
            <span
              className="text-sm text-text-secondary font-mono flex items-center gap-1"
              title="Total wall-clock duration of the run"
            >
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
              <TestResultCard key={idx} result={result} providerHint={meta.provider} />
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
      {confirmElement}
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
              {runsTotal || testRuns.length}
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
              placeholder="Search..."
              className="input text-xs py-1.5 px-3 w-36"
            />
            {filterOptions.models.length > 1 && (
              <select
                value={filterModel}
                onChange={(e) => setFilterModel(e.target.value)}
                className="input text-xs py-1.5 px-2"
              >
                <option value="">All Models</option>
                {filterOptions.models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
            {filterOptions.providers.length > 1 && (
              <select
                value={filterProvider}
                onChange={(e) => setFilterProvider(e.target.value)}
                className="input text-xs py-1.5 px-2"
              >
                <option value="">All Providers</option>
                {filterOptions.providers.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            )}
            {filterOptions.test_files.length > 1 && (
              <select
                value={filterTestFile}
                onChange={(e) => setFilterTestFile(e.target.value)}
                className="input text-xs py-1.5 px-2"
              >
                <option value="">All Test Files</option>
                {filterOptions.test_files.map(f => <option key={f} value={f}>{f.split('/').pop()}</option>)}
              </select>
            )}
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
            <div className="flex items-center gap-1 ml-auto">
              <Link
                to="/performance"
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors bg-surface hover:bg-surface-hover text-text-secondary"
                title="Compare runs across models and configs on the Performance page"
              >
                Compare
              </Link>
            </div>
            {(filterModel || filterProvider || filterTestFile) && (
              <button
                onClick={() => { setFilterModel(''); setFilterProvider(''); setFilterTestFile('') }}
                className="text-xs text-text-tertiary hover:text-text-secondary"
              >
                Clear filters
              </button>
            )}
          </div>
      </div>

      {/* Content — list + detail panel for tests/smoke */}
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
                  <div className="mt-4 flex items-center gap-2 bg-surface border border-border rounded-lg px-3 py-2">
                    <code className="flex-1 text-left text-xs font-mono text-text-secondary overflow-x-auto whitespace-nowrap">
                      testmcpy run examples/ --model claude-haiku-4-5
                    </code>
                    <button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText('testmcpy run examples/ --model claude-haiku-4-5')
                          setCopiedCmd(true)
                          setTimeout(() => setCopiedCmd(false), 2000)
                        } catch (err) {
                          console.error('Copy failed:', err)
                        }
                      }}
                      className="p-1.5 rounded hover:bg-surface-hover text-text-tertiary hover:text-text-primary flex-shrink-0"
                      title="Copy command"
                      aria-label="Copy command"
                    >
                      {copiedCmd ? <Check size={14} className="text-success" /> : <Copy size={14} />}
                    </button>
                  </div>
                  <p className="text-text-disabled text-sm mt-3">
                    or open the <Link to="/tests" className="text-primary hover:underline">Tests page</Link> to create a suite
                  </p>
                </div>
              ) : (
                <div>
                  {/* Bulk-select toolbar */}
                  {selectMode ? (
                    <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-surface sticky top-0 z-10">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedRuns.size === filteredTestRuns.length && filteredTestRuns.length > 0}
                          ref={el => { if (el) el.indeterminate = selectedRuns.size > 0 && selectedRuns.size < filteredTestRuns.length }}
                          onChange={toggleSelectAll}
                          className="accent-primary"
                        />
                        <span className="text-xs text-text-secondary">
                          {selectedRuns.size > 0 ? `${selectedRuns.size} selected` : 'Select all'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedRuns.size > 0 && (
                          <button
                            onClick={deleteSelected}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-error text-white rounded hover:bg-error/90 transition-colors"
                          >
                            <Trash2 size={12} />
                            Delete {selectedRuns.size}
                          </button>
                        )}
                        <button
                          onClick={toggleSelectMode}
                          className="text-xs text-text-secondary hover:text-text-primary px-2 py-1 rounded hover:bg-surface-hover transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex justify-end px-3 py-1.5 border-b border-border">
                      <button
                        onClick={toggleSelectMode}
                        className="text-xs text-text-secondary hover:text-text-primary flex items-center gap-1 px-2 py-1 rounded hover:bg-surface-hover transition-colors"
                      >
                        <CheckSquare size={12} />
                        Select
                      </button>
                    </div>
                  )}
                  <div className="divide-y divide-border">
                    {filteredTestRuns.map(renderRunListItem)}
                  </div>
                  {testRuns.length < runsTotal && (
                    <div className="p-3 text-center border-t border-border">
                      <button
                        onClick={loadMoreRuns}
                        disabled={loadingMore}
                        className="text-xs text-text-secondary hover:text-text-primary px-3 py-1.5 rounded bg-surface hover:bg-surface-hover transition-colors disabled:opacity-50"
                      >
                        {loadingMore
                          ? 'Loading…'
                          : `Load more (${testRuns.length} of ${runsTotal})`}
                      </button>
                    </div>
                  )}
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
                      ref={el => scrollPendingRunIntoView(el, report.report_id)}
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
              <button onClick={() => { setSelectedRun(null); setRunDetails(null); setSearchParams({}, { replace: true }) }} className="md:hidden flex items-center gap-2 px-4 py-3 text-sm text-text-secondary hover:text-text-primary border-b border-border w-full">
                <ChevronRight size={16} className="rotate-180" />
                <span>Back to list</span>
              </button>
            )}
            {loadingDetails ? (
              <div className="p-4 space-y-2">
                <Skeleton width="40%" height="24px" className="mb-4" />
                {Array.from({ length: 6 }).map((_, idx) => (
                  <ListItemSkeleton key={idx} />
                ))}
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
