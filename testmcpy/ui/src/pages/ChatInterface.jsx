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

  useEffect(() => {
    loadModels()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

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
    const testContent = `version: "1.0"
tests:
  - name: ${testName}
    prompt: "${userMessage.content.replace(/"/g, '\\"')}"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "${assistantMessage.tool_calls?.[0]?.name || 'any'}"
      - name: final_answer_contains
        args:
          expected_content: "${assistantMessage.content.substring(0, 50).replace(/"/g, '\\"')}"
`

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
        alert('Test case created successfully!')
      } else {
        const error = await res.json()
        alert(`Failed to create test case: ${error.detail}`)
      }
    } catch (error) {
      console.error('Failed to create test case:', error)
      alert('Failed to create test case')
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-8 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Chat Interface</h1>
            <p className="text-text-secondary mt-2 text-base">
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
      <div className="flex-1 overflow-auto p-8 bg-background-subtle">
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
          <div className="space-y-6 max-w-4xl mx-auto pb-4">
            {messages.map((message, idx) => (
              <div
                key={idx}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                } animate-fade-in`}
              >
                <div
                  className={`max-w-[85%] rounded-xl p-5 shadow-soft ${
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

                  {/* Tool calls */}
                  {message.tool_calls && message.tool_calls.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/10 space-y-3">
                      <div className="flex items-center gap-2 text-sm opacity-80">
                        <Wrench size={16} />
                        <span className="font-medium">Used {message.tool_calls.length} tool(s)</span>
                      </div>
                      <div className="space-y-3">
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
                    </div>
                  )}

                  {/* Metadata */}
                  {message.token_usage && (
                    <div className="mt-4 pt-4 border-t border-white/10 flex items-center gap-5 text-xs opacity-70">
                      <span className="flex items-center gap-1.5">
                        <span className="font-medium">{message.token_usage.total?.toLocaleString()}</span> tokens
                      </span>
                      {message.cost > 0 && (
                        <span className="flex items-center gap-1">
                          <DollarSign size={14} />
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
      <div className="p-6 border-t border-border bg-surface-elevated shadow-strong">
        <div className="max-w-4xl mx-auto flex gap-4">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message... (Shift+Enter for new line)"
            className="input flex-1 resize-none text-base"
            rows={3}
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
