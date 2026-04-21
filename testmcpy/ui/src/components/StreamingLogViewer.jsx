import React, { useState, useEffect, useRef } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Brain,
  Wrench,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  MessageSquare,
  FileText,
  Zap,
  Hash,
  Clock,
  DollarSign,
  Server,
  Activity,
  Play,
  BarChart3,
} from 'lucide-react'

/**
 * Parse a flat array of log strings into structured log entries.
 * Each entry has a `type` and relevant fields.
 */
function parseLogs(logs) {
  const entries = []
  let currentTest = null
  let i = 0

  while (i < logs.length) {
    const line = logs[i]
    const trimmed = line.trim()

    // Skip empty lines and pure separator lines
    if (!trimmed || /^[=\-]{3,}$/.test(trimmed)) {
      i++
      continue
    }

    // --- Test header: "Running test: X" or emoji variant ---
    const testHeaderMatch = trimmed.match(/^(?:🧪\s*)?Running test(?:\s+\d+\/\d+)?:\s*(.+)$/i)
    if (testHeaderMatch) {
      currentTest = testHeaderMatch[1].trim()
      entries.push({ type: 'test_header', name: currentTest, raw: line })
      i++
      continue
    }

    // --- Prompt ---
    const promptMatch = trimmed.match(/^(?:📝\s*)?Prompt:\s*(.+)$/i)
    if (promptMatch) {
      entries.push({ type: 'prompt', text: promptMatch[1].replace(/\.{3}$/, ''), raw: line })
      i++
      continue
    }

    // --- Thinking: [ClaudeSDK] Thinking (X chars) ---
    const thinkingMatch = trimmed.match(/^\[(\w+)\]\s*Thinking\s*\((\d+)\s*chars?\)/i)
    if (thinkingMatch) {
      entries.push({ type: 'thinking', provider: thinkingMatch[1], chars: thinkingMatch[2], raw: line })
      i++
      continue
    }

    // --- LLM Text response ---
    const textMatch = trimmed.match(/^\[(\w+)\]\s*Text:\s*(.+)$/i)
    if (textMatch) {
      entries.push({ type: 'llm_text', provider: textMatch[1], text: textMatch[2], raw: line })
      i++
      continue
    }

    // --- Tool Call: [ClaudeSDK] Tool Call: X | Args: Y ---
    const toolCallMatch = trimmed.match(/^\[(\w+)\]\s*Tool Call:\s*([^\|]+?)(?:\s*\|\s*Args:\s*(.+))?$/i)
    if (toolCallMatch) {
      let args = toolCallMatch[3]?.trim() || ''
      entries.push({
        type: 'tool_call',
        provider: toolCallMatch[1],
        name: toolCallMatch[2].trim(),
        args,
        raw: line,
      })
      i++
      continue
    }

    // --- Tool call from test runner: "  1. toolname(" with args on next line ---
    const numberedToolMatch = trimmed.match(/^\d+\.\s+(\S+)\($/)
    if (numberedToolMatch) {
      let args = ''
      // Check next line for args
      if (i + 1 < logs.length) {
        const nextLine = logs[i + 1].trim()
        if (nextLine !== ')') {
          args = nextLine
        }
      }
      entries.push({
        type: 'tool_call',
        provider: '',
        name: numberedToolMatch[1],
        args,
        raw: line,
      })
      // Skip the args line and closing paren
      i++
      while (i < logs.length && logs[i].trim() !== ')') i++
      if (i < logs.length) i++ // skip the )
      continue
    }

    // --- Evaluator result ---
    const evalMatch = trimmed.match(/^(?:Evaluator\s+)?(\w[\w_]*)\s*:\s*(PASS|FAIL)(?:ED)?\s*(?:\(score:\s*([\d.]+)\))?/i)
    if (evalMatch) {
      entries.push({
        type: 'evaluator',
        name: evalMatch[1],
        passed: evalMatch[2].toUpperCase().startsWith('PASS'),
        score: evalMatch[3] || null,
        raw: line,
      })
      i++
      continue
    }

    // --- Evaluator from test runner format: "  evaluator_name: PASSED/FAILED (score: X)" ---
    const evalMatch2 = trimmed.match(/^(\w[\w_]*):\s*(PASSED|FAILED)\s*\(score:\s*([\d.]+)\)/i)
    if (evalMatch2) {
      entries.push({
        type: 'evaluator',
        name: evalMatch2[1],
        passed: evalMatch2[2].toUpperCase() === 'PASSED',
        score: evalMatch2[3],
        raw: line,
      })
      i++
      continue
    }

    // --- Test PASSED/FAILED result ---
    const resultMatch = trimmed.match(/^(✅\s*PASSED|❌\s*FAILED)\s*(?:in\s+([\d.]+)s)?/i)
    if (resultMatch) {
      const passed = resultMatch[1].includes('PASSED')
      entries.push({
        type: 'test_result',
        passed,
        time: resultMatch[2] || null,
        raw: line,
      })
      i++
      continue
    }

    // --- Token usage lines ---
    const tokenMatch = trimmed.match(/^(?:Token\s+(?:estimation|usage)|📊)\s*:?\s*(.+)$/i)
    if (tokenMatch) {
      entries.push({ type: 'tokens', text: tokenMatch[1], raw: line })
      i++
      continue
    }

    // --- Token detail lines (Input/Output/Cache/Total tokens) ---
    const tokenDetailMatch = trimmed.match(/^(Input|Output|Cache Creation|Cache Read|Total):\s*(.+)$/i)
    if (tokenDetailMatch) {
      entries.push({ type: 'token_detail', label: tokenDetailMatch[1], value: tokenDetailMatch[2], raw: line })
      i++
      continue
    }

    // --- Cost ---
    const costMatch = trimmed.match(/^(?:💰\s*)?(?:Total\s+)?[Cc]ost:\s*(.+)$/i)
    if (costMatch) {
      entries.push({ type: 'cost', text: costMatch[1], raw: line })
      i++
      continue
    }

    // --- Summary ---
    const summaryMatch = trimmed.match(/^(?:📊\s*)?SUMMARY:\s*(.+)$/i)
    if (summaryMatch) {
      entries.push({ type: 'summary', text: summaryMatch[1], raw: line })
      i++
      continue
    }

    // --- Tool calls count ---
    const toolCountMatch = trimmed.match(/^(?:🔧\s*)?Tool calls:\s*(\d+)/i)
    if (toolCountMatch) {
      entries.push({ type: 'tool_count', count: toolCountMatch[1], raw: line })
      i++
      continue
    }

    // --- Tool list item: "   - toolname" ---
    const toolListMatch = trimmed.match(/^-\s+(\S+)$/)
    if (toolListMatch && entries.length > 0 && entries[entries.length - 1].type === 'tool_count') {
      // Append to previous tool_count entry
      const last = entries[entries.length - 1]
      if (!last.tools) last.tools = []
      last.tools.push(toolListMatch[1])
      i++
      continue
    }

    // --- LLM Response text block ---
    const llmResponseMatch = trimmed.match(/^LLM Response:$/i)
    if (llmResponseMatch) {
      // Collect following indented lines
      let responseText = ''
      i++
      while (i < logs.length) {
        const nextLine = logs[i]
        if (nextLine.match(/^\s{2,}/) || nextLine.trim() === '') {
          responseText += (responseText ? '\n' : '') + nextLine.trim()
          i++
        } else {
          break
        }
      }
      if (responseText) {
        entries.push({ type: 'llm_response', text: responseText, raw: line })
      }
      continue
    }

    // --- Provider message: [ClaudeSDK] Message #N: Type ---
    const messageMatch = trimmed.match(/^\[(\w+)\]\s*Message #(\d+):\s*(.+)$/i)
    if (messageMatch) {
      entries.push({
        type: 'provider_message',
        provider: messageMatch[1],
        num: messageMatch[2],
        messageType: messageMatch[3],
        raw: line,
      })
      i++
      continue
    }

    // --- Provider status: [ClaudeSDK] Starting/MCP server/etc ---
    const providerStatusMatch = trimmed.match(/^\[(\w+)\]\s*(.+)$/i)
    if (providerStatusMatch) {
      entries.push({
        type: 'provider_status',
        provider: providerStatusMatch[1],
        text: providerStatusMatch[2],
        raw: line,
      })
      i++
      continue
    }

    // --- Status lines with emojis ---
    const statusMatch = trimmed.match(/^(🚀|🔌|📁|📋|🤖|⚙️|✅|⚠️|❌|💾|📝|⏱️|🧪)\s*(.+)$/u)
    if (statusMatch) {
      entries.push({ type: 'status', icon: statusMatch[1], text: statusMatch[2], raw: line })
      i++
      continue
    }

    // --- Error lines ---
    if (trimmed.includes('Error') || trimmed.includes('error') || trimmed.includes('FAILED') || trimmed.includes('Traceback')) {
      entries.push({ type: 'error', text: trimmed, raw: line })
      i++
      continue
    }

    // --- Generic log line ---
    entries.push({ type: 'generic', text: trimmed, raw: line })
    i++
  }

  return entries
}


// Collapsible section component
function CollapsibleSection({ icon, iconColor, label, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full text-left py-1 px-1.5 hover:bg-surface-hover rounded transition-colors group"
      >
        <span className={`flex-shrink-0 ${iconColor || 'text-text-tertiary'}`}>{icon}</span>
        <span className="text-text-disabled transition-transform duration-150" style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          <ChevronRight size={10} />
        </span>
        <span className="text-xs font-medium text-text-primary">{label}</span>
        {badge && <span className="ml-auto">{badge}</span>}
      </button>
      {open && (
        <div className="ml-6 mt-1 mb-1 animate-slide-down">
          {children}
        </div>
      )}
    </div>
  )
}


// Individual entry renderers
function TestHeaderEntry({ entry, isActive }) {
  return (
    <div className="flex items-center gap-2 py-2 px-2 mt-3 first:mt-0 rounded-lg bg-surface-elevated border border-border/50 animate-entry-in">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isActive ? 'bg-yellow-400 animate-pulse' : 'bg-text-disabled'}`} />
      <Play size={14} className="text-primary flex-shrink-0" />
      <span className="text-sm font-semibold text-text-primary truncate">{entry.name}</span>
    </div>
  )
}

function PromptEntry({ entry }) {
  return (
    <div className="ml-2 my-1.5 pl-3 border-l-2 border-primary/50 bg-primary/5 rounded-r-md py-2 pr-3 animate-entry-in">
      <div className="flex items-center gap-1.5 mb-1">
        <MessageSquare size={11} className="text-primary" />
        <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">Prompt</span>
      </div>
      <p className="text-xs text-text-secondary leading-relaxed">{entry.text}</p>
    </div>
  )
}

function ThinkingEntry({ entry }) {
  return (
    <div className="animate-entry-in">
      <CollapsibleSection
        icon={<Brain size={13} />}
        iconColor="text-purple-400"
        label="Thinking"
        badge={<span className="text-[10px] text-text-disabled">{entry.chars} chars</span>}
      >
        <div className="bg-purple-500/5 border border-purple-500/15 rounded-md px-2.5 py-2 text-[11px] text-text-tertiary font-mono leading-relaxed max-h-24 overflow-auto">
          Internal reasoning...
        </div>
      </CollapsibleSection>
    </div>
  )
}

function ToolCallEntry({ entry }) {
  const [showArgs, setShowArgs] = useState(false)
  const hasArgs = entry.args && entry.args !== '{}' && entry.args !== ''

  // Try to format args as JSON
  let formattedArgs = entry.args
  try {
    if (entry.args && entry.args.startsWith('{')) {
      formattedArgs = JSON.stringify(JSON.parse(entry.args), null, 2)
    }
  } catch {
    // keep as-is
  }

  return (
    <div className="ml-2 my-1 animate-entry-in">
      <div className="flex items-center gap-1.5 py-1 px-1.5 rounded hover:bg-surface-hover transition-colors">
        <Wrench size={12} className="text-cyan-400 flex-shrink-0" />
        <span className="text-xs font-mono font-semibold text-cyan-300">{entry.name}</span>
        {hasArgs && (
          <button
            onClick={() => setShowArgs(!showArgs)}
            className="text-[10px] text-text-disabled hover:text-text-tertiary ml-1 transition-colors"
          >
            {showArgs ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            <span className="ml-0.5">args</span>
          </button>
        )}
        {!hasArgs && (
          <span className="text-[10px] text-text-disabled">(no args)</span>
        )}
      </div>
      {showArgs && hasArgs && (
        <div className="ml-6 mt-1 mb-1">
          <pre className="bg-surface-elevated border border-border/50 rounded-md px-2.5 py-2 text-[11px] font-mono text-text-secondary overflow-x-auto max-h-32 overflow-y-auto">
            {formattedArgs}
          </pre>
        </div>
      )}
    </div>
  )
}

function LlmTextEntry({ entry }) {
  return (
    <div className="ml-2 my-1.5 animate-entry-in">
      <CollapsibleSection
        icon={<MessageSquare size={12} />}
        iconColor="text-blue-400"
        label="Response"
      >
        <div className="bg-surface-elevated border border-border/50 rounded-md px-2.5 py-2 text-xs text-text-secondary leading-relaxed max-h-40 overflow-auto">
          {entry.text}
        </div>
      </CollapsibleSection>
    </div>
  )
}

function LlmResponseEntry({ entry }) {
  return (
    <div className="ml-2 my-1.5 animate-entry-in">
      <CollapsibleSection
        icon={<MessageSquare size={12} />}
        iconColor="text-blue-400"
        label="LLM Response"
      >
        <div className="bg-surface-elevated border border-border/50 rounded-md px-2.5 py-2 text-xs text-text-secondary leading-relaxed whitespace-pre-wrap max-h-40 overflow-auto">
          {entry.text}
        </div>
      </CollapsibleSection>
    </div>
  )
}

function EvaluatorEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-2 py-1 px-1.5 animate-entry-in">
      {entry.passed ? (
        <CheckCircle2 size={13} className="text-green-400 flex-shrink-0" />
      ) : (
        <XCircle size={13} className="text-red-400 flex-shrink-0" />
      )}
      <span className="text-xs font-mono text-text-secondary">{entry.name}</span>
      {entry.score && (
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
          entry.passed ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'
        }`}>
          {entry.score}
        </span>
      )}
    </div>
  )
}

function TestResultEntry({ entry }) {
  return (
    <div className={`ml-2 my-2 flex items-center gap-2 py-1.5 px-3 rounded-lg animate-entry-in ${
      entry.passed
        ? 'bg-green-500/10 border border-green-500/20'
        : 'bg-red-500/10 border border-red-500/20'
    }`}>
      {entry.passed ? (
        <CheckCircle2 size={15} className="text-green-400 flex-shrink-0" />
      ) : (
        <XCircle size={15} className="text-red-400 flex-shrink-0" />
      )}
      <span className={`text-xs font-bold ${entry.passed ? 'text-green-400' : 'text-red-400'}`}>
        {entry.passed ? 'PASSED' : 'FAILED'}
      </span>
      {entry.time && (
        <span className="text-[10px] text-text-tertiary flex items-center gap-1 ml-auto">
          <Clock size={10} />
          {entry.time}s
        </span>
      )}
    </div>
  )
}

function ToolCountEntry({ entry }) {
  return (
    <div className="ml-2 my-1 animate-entry-in">
      <div className="flex items-center gap-1.5 py-1 px-1.5">
        <Wrench size={12} className="text-cyan-400" />
        <span className="text-xs text-text-secondary">
          <span className="font-semibold">{entry.count}</span> tool call{entry.count !== '1' ? 's' : ''}
        </span>
      </div>
      {entry.tools && entry.tools.length > 0 && (
        <div className="ml-6 flex flex-wrap gap-1 mt-0.5">
          {entry.tools.map((t, idx) => (
            <span key={idx} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/15">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function TokenDetailEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-2 py-0.5 px-1.5 animate-entry-in">
      <Hash size={10} className="text-text-disabled flex-shrink-0" />
      <span className="text-[11px] text-text-disabled">
        <span className="text-text-tertiary">{entry.label}:</span> {entry.value}
      </span>
    </div>
  )
}

function CostEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-1.5 py-0.5 px-1.5 animate-entry-in">
      <DollarSign size={11} className="text-purple-400 flex-shrink-0" />
      <span className="text-[11px] text-purple-300 font-mono">{entry.text}</span>
    </div>
  )
}

function SummaryEntry({ entry }) {
  return (
    <div className="mt-3 py-2 px-3 rounded-lg bg-surface-elevated border border-border/50 flex items-center gap-2 animate-entry-in">
      <BarChart3 size={14} className="text-primary flex-shrink-0" />
      <span className="text-xs font-semibold text-text-primary">Summary:</span>
      <span className="text-xs text-text-secondary">{entry.text}</span>
    </div>
  )
}

function StatusEntry({ entry }) {
  const iconMap = {
    '🚀': <Zap size={12} className="text-yellow-400" />,
    '🔌': <Server size={12} className="text-blue-400" />,
    '📁': <FileText size={12} className="text-blue-400" />,
    '📋': <FileText size={12} className="text-blue-400" />,
    '🤖': <Activity size={12} className="text-indigo-400" />,
    '⚙️': <Loader2 size={12} className="text-text-tertiary" />,
    '✅': <CheckCircle2 size={12} className="text-green-400" />,
    '⚠️': <AlertTriangle size={12} className="text-yellow-400" />,
    '❌': <XCircle size={12} className="text-red-400" />,
    '💾': <FileText size={12} className="text-green-400" />,
    '📝': <FileText size={12} className="text-blue-400" />,
    '⏱️': <Clock size={12} className="text-yellow-400" />,
    '🧪': <Play size={12} className="text-yellow-400" />,
  }

  return (
    <div className="my-0.5 flex items-center gap-1.5 py-0.5 px-1.5 animate-entry-in">
      {iconMap[entry.icon] || <span className="text-xs">{entry.icon}</span>}
      <span className="text-[11px] text-text-secondary">{entry.text}</span>
    </div>
  )
}

function ProviderStatusEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-1.5 py-0.5 px-1.5 animate-entry-in">
      <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-surface-elevated text-text-disabled border border-border/30">
        {entry.provider}
      </span>
      <span className="text-[11px] text-text-disabled">{entry.text}</span>
    </div>
  )
}

function ProviderMessageEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-1.5 py-0.5 px-1.5 animate-entry-in">
      <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-surface-elevated text-text-disabled border border-border/30">
        {entry.provider}
      </span>
      <span className="text-[11px] text-text-disabled">
        Message #{entry.num}: <span className="text-text-tertiary">{entry.messageType}</span>
      </span>
    </div>
  )
}

function ErrorEntry({ entry }) {
  return (
    <div className="ml-2 my-1 py-1.5 px-2.5 rounded-md bg-red-500/10 border border-red-500/20 animate-entry-in">
      <div className="flex items-start gap-1.5">
        <XCircle size={12} className="text-red-400 flex-shrink-0 mt-0.5" />
        <span className="text-xs text-red-300 font-mono leading-relaxed break-all">{entry.text}</span>
      </div>
    </div>
  )
}

function GenericEntry({ entry }) {
  return (
    <div className="my-0.5 py-0.5 px-1.5 animate-entry-in">
      <span className="text-[11px] text-text-disabled font-mono">{entry.text}</span>
    </div>
  )
}

function TokensEntry({ entry }) {
  return (
    <div className="ml-2 my-0.5 flex items-center gap-1.5 py-0.5 px-1.5 animate-entry-in">
      <Hash size={11} className="text-text-disabled flex-shrink-0" />
      <span className="text-[11px] text-text-disabled">{entry.text}</span>
    </div>
  )
}


/**
 * StreamingLogViewer - Renders parsed, structured, animated test runner logs.
 */
export default function StreamingLogViewer({ logs, running }) {
  const containerRef = useRef(null)
  const bottomRef = useRef(null)
  const entries = parseLogs(logs)

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  // Track which test is currently active (last test_header without a following test_result)
  let activeTestName = null
  if (running) {
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].type === 'test_result') break
      if (entries[i].type === 'test_header') {
        activeTestName = entries[i].name
        break
      }
    }
  }

  return (
    <div ref={containerRef} className="h-full overflow-auto px-3 py-2 bg-surface">
      {entries.length === 0 ? (
        <div className="text-text-tertiary text-center py-4 text-xs">
          Waiting for test execution...
        </div>
      ) : (
        <div className="space-y-0">
          {entries.map((entry, idx) => {
            const key = `${idx}-${entry.type}`
            switch (entry.type) {
              case 'test_header':
                return <TestHeaderEntry key={key} entry={entry} isActive={running && entry.name === activeTestName} />
              case 'prompt':
                return <PromptEntry key={key} entry={entry} />
              case 'thinking':
                return <ThinkingEntry key={key} entry={entry} />
              case 'tool_call':
                return <ToolCallEntry key={key} entry={entry} />
              case 'llm_text':
                return <LlmTextEntry key={key} entry={entry} />
              case 'llm_response':
                return <LlmResponseEntry key={key} entry={entry} />
              case 'evaluator':
                return <EvaluatorEntry key={key} entry={entry} />
              case 'test_result':
                return <TestResultEntry key={key} entry={entry} />
              case 'tool_count':
                return <ToolCountEntry key={key} entry={entry} />
              case 'token_detail':
                return <TokenDetailEntry key={key} entry={entry} />
              case 'tokens':
                return <TokensEntry key={key} entry={entry} />
              case 'cost':
                return <CostEntry key={key} entry={entry} />
              case 'summary':
                return <SummaryEntry key={key} entry={entry} />
              case 'status':
                return <StatusEntry key={key} entry={entry} />
              case 'provider_status':
                return <ProviderStatusEntry key={key} entry={entry} />
              case 'provider_message':
                return <ProviderMessageEntry key={key} entry={entry} />
              case 'error':
                return <ErrorEntry key={key} entry={entry} />
              default:
                return <GenericEntry key={key} entry={entry} />
            }
          })}
          {running && (
            <div className="flex items-center gap-2 py-2 px-1.5 animate-pulse">
              <Loader2 size={12} className="animate-spin text-primary" />
              <span className="text-[11px] text-text-tertiary">Running...</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
