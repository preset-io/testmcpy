import React, { useState } from 'react'
import {
  CheckCircle2,
  Loader2,
  Brain,
  ChevronRight,
  ChevronDown,
  AlertCircle,
  Wrench,
} from 'lucide-react'
import ReactJson from '@microlink/react-json-view'
import { useEditorTheme } from '../hooks/useEditorTheme'

// Extract the most relevant argument as a one-line preview
function getArgPreview(name, args) {
  if (!args || typeof args !== 'object') return null
  const keys = Object.keys(args)
  if (keys.length === 0) return null

  // Known tool argument mappings
  const previewKey =
    name === 'Read' || name === 'read_file' ? 'file_path' :
    name === 'Write' || name === 'write_file' ? 'file_path' :
    name === 'Edit' ? 'file_path' :
    name === 'Glob' ? 'pattern' :
    name === 'Grep' || name === 'grep' ? 'pattern' :
    name === 'Bash' || name === 'bash' ? 'command' :
    null

  if (previewKey && args[previewKey]) {
    return String(args[previewKey])
  }

  // Fallback: first string argument
  for (const key of keys) {
    if (typeof args[key] === 'string' && args[key].length > 0) {
      return args[key]
    }
  }

  return `${keys.length} arg${keys.length !== 1 ? 's' : ''}`
}

// Parse JSON strings recursively for display
function parseJsonStrings(obj) {
  if (obj === null || obj === undefined) return obj
  if (typeof obj === 'string') {
    if ((obj.trim().startsWith('{') && obj.trim().endsWith('}')) ||
        (obj.trim().startsWith('[') && obj.trim().endsWith(']'))) {
      try {
        return parseJsonStrings(JSON.parse(obj))
      } catch {
        return obj
      }
    }
    return obj
  }
  if (Array.isArray(obj)) return obj.map(parseJsonStrings)
  if (typeof obj === 'object') {
    const parsed = {}
    for (const [key, value] of Object.entries(obj)) {
      parsed[key] = parseJsonStrings(value)
    }
    return parsed
  }
  return obj
}

function TimelineRow({ icon, iconColor, label, preview, expanded, onToggle, children, pulse }) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 w-full text-left min-h-[28px] hover:bg-surface-hover rounded-md px-1.5 py-1 transition-colors group cursor-pointer"
      >
        <span className={`flex-shrink-0 ${iconColor} ${pulse ? 'animate-pulse' : ''}`}>
          {icon}
        </span>
        <span className="flex-shrink-0 text-text-disabled transition-transform duration-150" style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          <ChevronRight size={10} />
        </span>
        <span className="flex items-baseline gap-1.5 min-w-0 flex-1 overflow-hidden">
          <strong className="flex-shrink-0 text-xs text-text-primary">{label}</strong>
          {preview && (
            <span className="text-[11px] text-text-tertiary font-mono truncate">
              {preview}
            </span>
          )}
        </span>
      </button>
      {expanded && children && (
        <div className="ml-5 mt-1 mb-2">
          {children}
        </div>
      )}
    </div>
  )
}

function ToolCallDetail({ call }) {
  const { jsonTheme } = useEditorTheme()
  const hasArgs = call.arguments && Object.keys(call.arguments).length > 0
  const hasResult = call.result !== undefined && call.result !== null

  // Check if result is simple text (string < 300 chars)
  const isSimpleResult = typeof call.result === 'string' && call.result.length < 300

  return (
    <div className="space-y-2 text-xs">
      {/* Arguments */}
      {hasArgs && (
        <div>
          <div className="text-[10px] text-text-disabled mb-1 uppercase tracking-wider font-medium">Input</div>
          <div className="bg-background-subtle rounded-md p-2 border border-border">
            <ReactJson
              src={call.arguments}
              theme={jsonTheme}
              collapsed={1}
              displayDataTypes={false}
              displayObjectSize={false}
              enableClipboard={true}
              name={false}
              indentWidth={2}
              iconStyle="triangle"
              style={{
                backgroundColor: 'transparent',
                fontSize: '11px',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
              }}
            />
          </div>
        </div>
      )}

      {/* Result */}
      {hasResult && (
        <div>
          <div className="text-[10px] text-text-disabled mb-1 uppercase tracking-wider font-medium">Output</div>
          {isSimpleResult ? (
            <div className="bg-background-subtle rounded-md p-2 border border-border font-mono text-[11px] text-text-secondary whitespace-pre-wrap break-all">
              {call.result}
            </div>
          ) : (
            <div className="bg-background-subtle rounded-md p-2 border border-border overflow-x-auto">
              <ReactJson
                src={parseJsonStrings(call.result)}
                theme={jsonTheme}
                collapsed={2}
                displayDataTypes={false}
                displayObjectSize={true}
                enableClipboard={true}
                name={false}
                indentWidth={2}
                iconStyle="triangle"
                style={{
                  backgroundColor: 'transparent',
                  fontSize: '11px',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {call.error && (
        <div className="bg-error/10 border border-error/30 rounded-md p-2">
          <div className="text-[10px] font-semibold text-error mb-0.5">Error</div>
          <div className="text-[11px] text-text-secondary font-mono">{call.error}</div>
        </div>
      )}
    </div>
  )
}

function ThinkingDetail({ text }) {
  return (
    <div className="bg-purple-50 dark:bg-purple-900/15 border border-purple-200 dark:border-purple-500/20 rounded-md p-2.5 max-h-52 overflow-y-auto">
      <div className="whitespace-pre-wrap font-mono text-[11px] text-text-secondary leading-relaxed">
        {text}
      </div>
    </div>
  )
}

export default function ToolCallTimeline({ toolCalls = [], thinking, streaming }) {
  const [expanded, setExpanded] = useState({})

  if (!toolCalls.length && !thinking) return null

  const toggle = (key) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
  }

  // Build timeline items in order: thinking first if it exists, then tool calls
  // For multi-turn, interleave thinking between turns if needed
  const items = []

  if (thinking) {
    const thinkingPreview = thinking.split('\n')[0]?.slice(0, 80) || ''
    items.push({
      key: 'thinking',
      type: 'thinking',
      text: thinking,
      preview: thinkingPreview,
    })
  }

  toolCalls.forEach((call, idx) => {
    items.push({
      key: `tool-${idx}`,
      type: 'tool',
      call,
      idx,
    })
  })

  return (
    <div className="mt-2 pl-1 border-l-2 border-border ml-1">
      <div className="flex flex-col gap-0">
        {items.map((item) => {
          if (item.type === 'thinking') {
            return (
              <TimelineRow
                key={item.key}
                icon={<Brain size={14} />}
                iconColor="text-purple-400"
                label="Thinking"
                preview={item.preview}
                expanded={expanded[item.key]}
                onToggle={() => toggle(item.key)}
                pulse={streaming && !toolCalls.length}
              >
                <ThinkingDetail text={item.text} />
              </TimelineRow>
            )
          }

          const call = item.call
          const isComplete = call.result !== undefined || call.error
          const isInProgress = !isComplete && streaming
          const preview = getArgPreview(call.name, call.arguments)

          return (
            <TimelineRow
              key={item.key}
              icon={
                call.is_error || call.error
                  ? <AlertCircle size={14} />
                  : isInProgress
                    ? <Loader2 size={14} className="animate-spin" />
                    : <CheckCircle2 size={14} />
              }
              iconColor={
                call.is_error || call.error
                  ? 'text-error'
                  : isInProgress
                    ? 'text-primary-light'
                    : 'text-success'
              }
              label={call.name}
              preview={preview}
              expanded={expanded[item.key]}
              onToggle={() => toggle(item.key)}
              pulse={isInProgress}
            >
              <ToolCallDetail call={call} />
            </TimelineRow>
          )
        })}
      </div>
    </div>
  )
}
