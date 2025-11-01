import React, { useState, useEffect, useRef } from 'react'
import { Send, Loader, Wrench, DollarSign, ChevronDown, ChevronRight, CheckCircle, FileText, Plus } from 'lucide-react'
import ReactJson from '@microlink/react-json-view'

// JSON viewer component with IDE-like collapsible tree
function JSONViewer({ data }) {
  const [collapsed, setCollapsed] = useState(true)

  // Parse JSON strings recursively
  const parseJsonStrings = (obj) => {
    if (obj === null || obj === undefined) return obj

    if (typeof obj === 'string') {
      // Try to parse strings that look like JSON
      if ((obj.trim().startsWith('{') && obj.trim().endsWith('}')) ||
          (obj.trim().startsWith('[') && obj.trim().endsWith(']'))) {
        try {
          return parseJsonStrings(JSON.parse(obj))
        } catch (e) {
          return obj
        }
      }
      return obj
    }

    if (Array.isArray(obj)) {
      return obj.map(parseJsonStrings)
    }

    if (typeof obj === 'object') {
      const parsed = {}
      for (const [key, value] of Object.entries(obj)) {
        parsed[key] = parseJsonStrings(value)
      }
      return parsed
    }

    return obj
  }

  const parsedData = parseJsonStrings(data)

  return (
    <div className="mt-2">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors mb-2"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <span>Tool Output</span>
      </button>
      {!collapsed && (
        <div className="bg-black/40 rounded-lg p-3 border border-white/10 overflow-x-auto">
          <ReactJson
            src={parsedData}
            theme="monokai"
            collapsed={false}
            displayDataTypes={false}
            displayObjectSize={true}
            enableClipboard={true}
            name={false}
            indentWidth={2}
            iconStyle="triangle"
            style={{
              backgroundColor: 'transparent',
              fontSize: '12px',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
            }}
          />
        </div>
      )}
    </div>
  )
}

function ChatInterface() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState({})
  const [selectedProvider, setSelectedProvider] = useState('anthropic')
  const [selectedModel, setSelectedModel] = useState('claude-haiku-4-5')
  const messagesEndRef = useRef(null)
  const [showEvalDialog, setShowEvalDialog] = useState(false)
  const [selectedMessageIndex, setSelectedMessageIndex] = useState(null)
  const [evalResults, setEvalResults] = useState({})
  const [runningEval, setRunningEval] = useState(null)
  const [collapsedToolCalls, setCollapsedToolCalls] = useState({})
  const textareaRef = useRef(null)

  useEffect(() => {
    loadModels()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Reset textarea height when input is cleared
  useEffect(() => {
    if (input === '' && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input])

  const loadModels = async () => {
    try {
      const res = await fetch('/api/models')
      const data = await res.json()
      setModels(data)
    } catch (error) {
      console.error('Failed to load models:', error)
    }
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage = { role: 'user', content: input }
    setMessages([...messages, userMessage])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          model: selectedModel,
          provider: selectedProvider,
        }),
      })

      const data = await res.json()

      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        tool_calls: data.tool_calls || [],
        token_usage: data.token_usage,
        cost: data.cost,
        duration: data.duration,
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      console.error('Failed to send message:', error)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error.message}`,
          error: true,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Auto-expand textarea as user types (max 6 rows)
  const handleTextareaChange = (e) => {
    setInput(e.target.value)

    // Reset height to auto to get the correct scrollHeight
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'

      // Calculate number of rows based on content
      const lineHeight = 24 // approximate line height in pixels
      const maxHeight = lineHeight * 6 // max 6 rows
      const newHeight = Math.min(textarea.scrollHeight, maxHeight)

      textarea.style.height = `${newHeight}px`
    }
  }

  const runEval = async (messageIndex) => {
    const userMessage = messages[messageIndex - 1]
    const assistantMessage = messages[messageIndex]

    if (!userMessage || !assistantMessage || userMessage.role !== 'user' || assistantMessage.role !== 'assistant') {
      console.error('Invalid message pair for eval')
      return
    }

    setRunningEval(messageIndex)

    try {
      const res = await fetch('/api/eval/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: userMessage.content,
          response: assistantMessage.content,
          tool_calls: assistantMessage.tool_calls || [],
          model: selectedModel,
          provider: selectedProvider,
        }),
      })

      const data = await res.json()

      if (!res.ok) {
        console.error('Eval API error:', data)
        setEvalResults((prev) => ({
          ...prev,
          [messageIndex]: {
            passed: false,
            score: null,
            reason: `API Error: ${data.detail || 'Unknown error'}`,
            evaluations: []
          }
        }))
      } else {
        console.log('Eval results:', data)
        setEvalResults((prev) => ({ ...prev, [messageIndex]: data }))
      }
    } catch (error) {
      console.error('Failed to run eval:', error)
      setEvalResults((prev) => ({
        ...prev,
        [messageIndex]: {
          passed: false,
          score: null,
          reason: `Error: ${error.message}`,
          evaluations: []
        }
      }))
    } finally {
      setRunningEval(null)
    }
  }

  const createTestCase = async (messageIndex) => {
    const userMessage = messages[messageIndex - 1]
    const assistantMessage = messages[messageIndex]

    if (!userMessage || !assistantMessage) {
      console.error('Invalid message pair for test case')
      return
    }

    const testName = `test_${Date.now()}`

    // Build evaluators based on actual tool calls
    let evaluators = `      - name: execution_successful`

    if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
      const firstTool = assistantMessage.tool_calls[0]

      // Check specific tool was called
      evaluators += `
      - name: was_mcp_tool_called
        args:
          tool_name: "${firstTool.name}"`

      // Check tool call count if multiple tools
      if (assistantMessage.tool_calls.length > 1) {
        evaluators += `
      - name: tool_call_count
        args:
          expected_count: ${assistantMessage.tool_calls.length}`
      }

      // Add parameter validation for important parameters
      if (firstTool.arguments && Object.keys(firstTool.arguments).length > 0) {
        const params = Object.entries(firstTool.arguments)
          .slice(0, 3) // Limit to first 3 params to keep test manageable
          .map(([key, value]) => {
            // Properly escape and format values for YAML
            let yamlValue
            if (typeof value === 'string') {
              // Escape quotes and wrap in quotes
              yamlValue = `"${value.replace(/"/g, '\\"')}"`
            } else if (typeof value === 'boolean' || typeof value === 'number') {
              yamlValue = value
            } else if (value === null) {
              yamlValue = 'null'
            } else {
              // For objects/arrays, stringify and escape
              yamlValue = `"${JSON.stringify(value).replace(/"/g, '\\"')}"`
            }
            return `            ${key}: ${yamlValue}`
          })
          .join('\n')

        evaluators += `
      - name: tool_called_with_parameters
        args:
          tool_name: "${firstTool.name}"
          parameters:
${params}
          partial_match: true`
      }
    }

    // Add content check if response has meaningful content
    if (assistantMessage.content && assistantMessage.content.length > 10) {
      const snippet = assistantMessage.content.substring(0, 50).replace(/"/g, '\\"').replace(/\n/g, ' ')
      evaluators += `
      - name: final_answer_contains
        args:
          expected_content: "${snippet}"`
    }

    const testContent = `version: "1.0"
tests:
  - name: ${testName}
    prompt: "${userMessage.content.replace(/"/g, '\\"')}"
    evaluators:
${evaluators}
`

    console.log('Generated test content:', testContent)

    try {
      const res = await fetch('/api/tests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: `${testName}.yaml`,
          content: testContent,
        }),
      })

      if (res.ok) {
        const result = await res.json()
        console.log('Test created:', result)
        alert(`Test case created successfully: ${testName}.yaml`)
      } else {
        const error = await res.json().catch(() => ({ detail: 'Unknown error' }))
        console.error('Failed to create test:', error)
        alert(`Failed to create test case: ${error.detail}`)
      }
    } catch (error) {
      console.error('Failed to create test case:', error)
      alert(`Failed to create test case: ${error.message}`)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Chat Interface</h1>
            <p className="text-text-secondary mt-1 text-base">
              Interactive chat with LLM using MCP tools
            </p>
          </div>
          <div className="flex gap-3">
            <select
              value={selectedProvider}
              onChange={(e) => {
                setSelectedProvider(e.target.value)
                // Set default model for provider
                const providerModels = models[e.target.value]
                if (providerModels && providerModels.length > 0) {
                  setSelectedModel(providerModels[0].id)
                }
              }}
              className="input text-sm min-w-[140px]"
            >
              {Object.keys(models).map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="input text-sm min-w-[180px]"
            >
              {(models[selectedProvider] || []).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 bg-background-subtle">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 bg-surface-elevated rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                <Send size={28} className="text-text-tertiary" />
              </div>
              <p className="text-xl font-medium text-text-secondary mb-2">Start a conversation</p>
              <p className="text-sm text-text-tertiary max-w-md">
                Ask questions and the LLM will use MCP tools to help you accomplish your tasks
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto pb-4">
            {messages.map((message, idx) => (
              <div
                key={idx}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                } animate-fade-in`}
              >
                <div
                  className={`w-full max-w-2xl rounded-lg p-3 shadow-soft break-words ${
                    message.role === 'user'
                      ? 'bg-primary text-white'
                      : message.error
                      ? 'bg-error/10 border border-error/30'
                      : 'bg-surface border border-border'
                  }`}
                >
                  <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>

                  {/* Eval and Test Actions for Assistant Messages */}
                  {message.role === 'assistant' && !message.error && (
                    <div className="mt-4 pt-4 border-t border-white/10 flex gap-2">
                      <button
                        onClick={() => runEval(idx)}
                        disabled={runningEval === idx}
                        className="btn btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3"
                        title="Run evaluators on this response"
                      >
                        <CheckCircle size={14} />
                        <span>{runningEval === idx ? 'Running...' : 'Run Eval'}</span>
                      </button>
                      <button
                        onClick={() => createTestCase(idx)}
                        className="btn btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3"
                        title="Create test case from this interaction"
                      >
                        <FileText size={14} />
                        <span>Create Test</span>
                      </button>
                    </div>
                  )}

                  {/* Display Eval Results */}
                  {evalResults[idx] && (
                    <div className="mt-4 pt-4 border-t border-white/10">
                      <div className="flex items-center gap-2 mb-3">
                        <CheckCircle size={16} className={evalResults[idx].passed ? 'text-success' : 'text-error'} />
                        <span className="font-semibold text-sm">
                          Eval: {evalResults[idx].passed ? 'PASSED' : 'FAILED'}
                        </span>
                        <span className="text-xs text-white/60">
                          Score: {evalResults[idx].score?.toFixed(2) || 'N/A'}
                        </span>
                      </div>
                      {evalResults[idx].reason && (
                        <p className="text-xs text-white/70 leading-relaxed mb-3">
                          {evalResults[idx].reason}
                        </p>
                      )}

                      {/* Tool Calls Summary */}
                      {message.tool_calls && message.tool_calls.length > 0 && (
                        <div className="mb-3 bg-black/30 rounded-lg p-3 border border-white/10">
                          <div className="text-xs text-white/60 mb-2 flex items-center gap-2">
                            <Wrench size={12} />
                            <span className="font-medium">Tool Calls ({message.tool_calls.length})</span>
                          </div>
                          <div className="space-y-2">
                            {message.tool_calls.map((call, callIdx) => (
                              <div key={callIdx} className="bg-black/20 rounded p-2">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-mono text-[11px] text-primary-light font-semibold">
                                    {call.name}
                                  </span>
                                  {call.is_error && (
                                    <span className="text-[10px] text-error">✗ Error</span>
                                  )}
                                </div>
                                {call.arguments && Object.keys(call.arguments).length > 0 && (
                                  <div className="mt-1">
                                    <div className="text-[10px] text-white/50 mb-1">Parameters:</div>
                                    <div className="space-y-1">
                                      {Object.entries(call.arguments).map(([key, value]) => (
                                        <div key={key} className="flex items-start gap-2 text-[11px]">
                                          <span className="text-white/60 font-medium min-w-[80px]">{key}:</span>
                                          <span className="text-white/80 font-mono flex-1 break-all">
                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Individual evaluator results */}
                      {evalResults[idx].evaluations && evalResults[idx].evaluations.length > 0 && (
                        <div className="space-y-2 mt-3">
                          {evalResults[idx].evaluations.map((evalItem, evalIdx) => (
                            <div key={evalIdx} className="bg-black/20 rounded-lg p-2.5 border border-white/10">
                              <div className="flex items-start gap-2">
                                <CheckCircle size={14} className={evalItem.passed ? 'text-success mt-0.5' : 'text-error mt-0.5'} />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <span className="text-xs font-medium text-white/90">{evalItem.evaluator}</span>
                                    <span className="text-[10px] text-white/50">
                                      {evalItem.passed ? '✓' : '✗'} Score: {evalItem.score?.toFixed(2)}
                                    </span>
                                  </div>
                                  {evalItem.reason && (
                                    <p className="text-[11px] text-white/70 leading-relaxed">
                                      {evalItem.reason}
                                    </p>
                                  )}
                                  {/* Show error details if present */}
                                  {evalItem.details && evalItem.details.errors && (
                                    <div className="mt-2 bg-error/10 border border-error/30 rounded p-2">
                                      <div className="text-[10px] font-semibold text-error-light mb-1">Error Details:</div>
                                      {evalItem.details.errors.map((err, errIdx) => (
                                        <div key={errIdx} className="text-[10px] text-white/80 mb-1">
                                          <span className="font-medium">Tool {err.tool}:</span> {err.error}
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tool calls - collapsed by default */}
                  {message.tool_calls && message.tool_calls.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-white/10">
                      <button
                        onClick={() => setCollapsedToolCalls(prev => ({ ...prev, [idx]: !prev[idx] }))}
                        className="flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
                      >
                        {collapsedToolCalls[idx] ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                        <Wrench size={14} />
                        <span>Used {message.tool_calls.length} tool(s)</span>
                      </button>
                      {!collapsedToolCalls[idx] && (
                        <div className="mt-3 space-y-3">
                          {message.tool_calls.map((call, callIdx) => (
                          <div
                            key={callIdx}
                            className="bg-black/20 rounded-lg p-3 border border-white/10"
                          >
                            <div className="flex items-baseline gap-2 mb-2">
                              <span className="font-mono font-semibold text-primary-light text-sm">
                                {call.name}
                              </span>
                              <span className="text-xs text-white/40">
                                ({Object.keys(call.arguments || {}).length} params)
                              </span>
                            </div>

                            {/* Arguments */}
                            {call.arguments && Object.keys(call.arguments).length > 0 && (
                              <div className="mb-2">
                                <div className="text-xs text-white/60 mb-1">Arguments:</div>
                                <div className="bg-black/30 rounded p-2">
                                  <ReactJson
                                    src={call.arguments}
                                    theme="monokai"
                                    collapsed={false}
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
                            {call.result && (
                              <JSONViewer data={call.result} />
                            )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Metadata - inline */}
                  {message.token_usage && (
                    <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-4 text-[10px] opacity-70">
                      <span className="flex items-center gap-1">
                        <span className="font-medium">{message.token_usage.total?.toLocaleString()}</span> tokens
                      </span>
                      {message.cost > 0 && (
                        <span className="flex items-center gap-1">
                          <DollarSign size={12} />
                          <span className="font-medium">{message.cost.toFixed(4)}</span>
                        </span>
                      )}
                      <span><span className="font-medium">{message.duration.toFixed(2)}</span>s</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start animate-fade-in">
                <div className="bg-surface border border-border rounded-xl p-5 shadow-soft">
                  <div className="flex items-center gap-3">
                    <Loader className="animate-spin text-primary" size={20} />
                    <span className="text-text-secondary text-sm">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border bg-surface-elevated shadow-strong">
        <div className="max-w-4xl mx-auto flex gap-4">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleTextareaChange}
            onKeyPress={handleKeyPress}
            placeholder="Type your message... (Shift+Enter for new line)"
            className="input flex-1 resize-none text-base overflow-y-auto"
            rows={1}
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="btn btn-primary h-fit self-end px-6"
          >
            <Send size={20} />
            <span>Send</span>
          </button>
        </div>
      </div>
    </div>
  )
}

export default ChatInterface
