import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Send, Loader, Wrench, DollarSign, ChevronDown, ChevronRight, CheckCircle, FileText, Plus, Server, Trash2, Brain } from 'lucide-react'
import ReactJson from '@microlink/react-json-view'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useKeyboardShortcuts, useAnnounce } from '../hooks/useKeyboardShortcuts'

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

function ChatInterface({ selectedProfiles = [], selectedLlmProfile, llmProfiles = [] }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const [showEvalDialog, setShowEvalDialog] = useState(false)
  const [selectedMessageIndex, setSelectedMessageIndex] = useState(null)
  const [evalResults, setEvalResults] = useState({})
  const [runningEval, setRunningEval] = useState(null)
  const [collapsedToolCalls, setCollapsedToolCalls] = useState({})
  const [collapsedThinking, setCollapsedThinking] = useState({})
  const textareaRef = useRef(null)
  const [historySize, setHistorySize] = useState(10)  // Number of messages to keep in history

  // For Chat, only use the first selected profile (single MCP at a time)
  const activeProfile = selectedProfiles.length > 0 ? selectedProfiles[0] : null
  const hasMultipleSelected = selectedProfiles.length > 1

  // Get model and provider from LLM profile
  const getLlmConfig = () => {
    if (!selectedLlmProfile || llmProfiles.length === 0) {
      return { model: 'claude-sonnet-4-5', provider: 'anthropic' }
    }

    const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
    if (!profile) {
      return { model: 'claude-sonnet-4-5', provider: 'anthropic' }
    }

    const defaultProvider = profile.providers?.find(p => p.default) || profile.providers?.[0]
    return {
      model: defaultProvider?.model || 'claude-sonnet-4-5',
      provider: defaultProvider?.provider || 'anthropic'
    }
  }

  useEffect(() => {
    loadChatHistory()
    checkForPrefillTool()
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


  const loadChatHistory = () => {
    try {
      const saved = localStorage.getItem('chatHistory')
      if (saved) {
        setMessages(JSON.parse(saved))
      }
    } catch (error) {
      console.error('Failed to load chat history:', error)
    }
  }

  const checkForPrefillTool = () => {
    try {
      const prefillData = localStorage.getItem('prefillTool')
      if (prefillData) {
        const tool = JSON.parse(prefillData)
        // Generate a sample prompt for this tool
        const samplePrompt = generateSamplePrompt(tool)
        setInput(samplePrompt)
        // Clear the prefill data
        localStorage.removeItem('prefillTool')
        // Focus the input
        setTimeout(() => {
          textareaRef.current?.focus()
        }, 100)
      }
    } catch (error) {
      console.error('Failed to load prefill tool:', error)
    }
  }

  const generateSamplePrompt = (tool) => {
    // Generate a natural language prompt based on the tool's description and parameters
    const params = tool.schema?.properties || {}
    const requiredParams = tool.schema?.required || []

    if (Object.keys(params).length === 0) {
      return `Can you help me use the ${tool.name} tool?`
    }

    // Create a sample prompt with placeholder values
    let prompt = `I'd like to use the ${tool.name} tool. `

    const paramDescriptions = []
    for (const [paramName, paramInfo] of Object.entries(params)) {
      const isRequired = requiredParams.includes(paramName)
      const type = paramInfo.type || 'any'

      if (isRequired) {
        let exampleValue = ''
        if (type === 'string') {
          exampleValue = paramInfo.enum ? paramInfo.enum[0] : 'example_value'
        } else if (type === 'number' || type === 'integer') {
          exampleValue = '123'
        } else if (type === 'boolean') {
          exampleValue = 'true'
        } else if (type === 'array') {
          exampleValue = '["item1", "item2"]'
        }

        paramDescriptions.push(`${paramName}: ${exampleValue}`)
      }
    }

    if (paramDescriptions.length > 0) {
      prompt += `Here are the parameters:\n${paramDescriptions.join('\n')}`
    }

    return prompt
  }

  const saveChatHistory = (messagesToSave) => {
    try {
      localStorage.setItem('chatHistory', JSON.stringify(messagesToSave))
    } catch (error) {
      console.error('Failed to save chat history:', error)
    }
  }

  const clearChatHistory = () => {
    setMessages([])
    localStorage.removeItem('chatHistory')
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage = { role: 'user', content: input }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setLoading(true)

    try {
      // Build history for API - last N messages (excluding current one we just added)
      const historyForAPI = messages.slice(-historySize).map(msg => ({
        role: msg.role,
        content: msg.content
      }))

      const llmConfig = getLlmConfig()
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          model: llmConfig.model,
          provider: llmConfig.provider,
          llm_profile: selectedLlmProfile,
          profiles: activeProfile ? [activeProfile] : null,
          history: historyForAPI.length > 0 ? historyForAPI : null,
        }),
      })

      const data = await res.json()

      const assistantMessage = {
        role: 'assistant',
        content: data.response || '',
        tool_calls: data.tool_calls || [],
        thinking: data.thinking || null,
        token_usage: data.token_usage,
        cost: data.cost,
        duration: data.duration,
        model: data.model || null,
        provider: data.provider || null,
      }

      const finalMessages = [...updatedMessages, assistantMessage]
      setMessages(finalMessages)
      saveChatHistory(finalMessages)
    } catch (error) {
      console.error('Failed to send message:', error)
      const errorMessages = [
        ...updatedMessages,
        {
          role: 'assistant',
          content: `Error: ${error.message}`,
          error: true,
        },
      ]
      setMessages(errorMessages)
      saveChatHistory(errorMessages)
    } finally {
      setLoading(false)
    }
  }

  // Screen reader announcements
  const announce = useAnnounce()

  // Announce new messages for screen readers
  useEffect(() => {
    if (messages.length > 0) {
      const lastMessage = messages[messages.length - 1]
      if (lastMessage.role === 'assistant' && lastMessage.content) {
        const preview = lastMessage.content.substring(0, 100)
        announce(`New response: ${preview}${lastMessage.content.length > 100 ? '...' : ''}`)
      }
    }
  }, [messages, announce])

  // Keyboard shortcut handlers
  const handleSendShortcut = useCallback((e) => {
    e.preventDefault()
    sendMessage()
  }, [input, loading])

  const handleClearShortcut = useCallback((e) => {
    e.preventDefault()
    if (messages.length > 0 && window.confirm('Clear chat history?')) {
      clearChatHistory()
      announce('Chat history cleared')
    }
  }, [messages, announce])

  // Register keyboard shortcuts
  useKeyboardShortcuts({
    'ctrl+enter': handleSendShortcut,
    'ctrl+shift+c': handleClearShortcut,
  }, !loading)

  const handleKeyPress = (e) => {
    // Enter without shift sends message
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
    // Cmd/Ctrl + Enter also sends message
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
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
      // Use model/provider from the message if available, otherwise get current config
      const model = assistantMessage.model || getLlmConfig().model
      const provider = assistantMessage.provider || getLlmConfig().provider

      const res = await fetch('/api/eval/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: userMessage.content,
          response: assistantMessage.content,
          tool_calls: assistantMessage.tool_calls || [],
          model: model,
          provider: provider,
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

    // Helper to strip MCP prefix from tool names
    const stripMcpPrefix = (name) => {
      if (name && name.includes('__')) {
        return name.split('__').pop()
      }
      return name
    }

    // Build evaluators based on actual tool calls
    let evaluators = `      - name: execution_successful`

    if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
      const firstTool = assistantMessage.tool_calls[0]
      const toolName = stripMcpPrefix(firstTool.name)

      // Check specific tool was called
      evaluators += `
      - name: was_mcp_tool_called
        args:
          tool_name: "${toolName}"`

      // Check tool call count if multiple tools
      if (assistantMessage.tool_calls.length > 1) {
        evaluators += `
      - name: tool_call_count
        args:
          expected_count: ${assistantMessage.tool_calls.length}`
      }

      // Add parameter validation only for simple primitive parameters
      // Skip empty objects, complex nested structures that cause matching issues
      if (firstTool.arguments && Object.keys(firstTool.arguments).length > 0) {
        const validParams = Object.entries(firstTool.arguments)
          .filter(([key, value]) => {
            // Only include string, number, boolean with actual values
            if (typeof value === 'string' && value.length > 0 && value !== '{}') return true
            if (typeof value === 'number') return true
            if (typeof value === 'boolean') return true
            return false
          })
          .slice(0, 3) // Limit to first 3 params

        if (validParams.length > 0) {
          const params = validParams
            .map(([key, value]) => {
              let yamlValue
              if (typeof value === 'string') {
                yamlValue = `"${value.replace(/"/g, '\\"')}"`
              } else {
                yamlValue = value
              }
              return `            ${key}: ${yamlValue}`
            })
            .join('\n')

          evaluators += `
      - name: tool_called_with_parameters
        args:
          tool_name: "${toolName}"
          parameters:
${params}
          partial_match: true`
        }
      }
    }

    // Note: We don't auto-add final_answer_contains because exact text matching is too brittle.
    // Users can manually add content-based evaluators if needed.
    // Tool-based tests are validated by execution_successful and was_mcp_tool_called.

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
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold">Chat Interface</h1>
            <p className="text-text-secondary mt-1 text-base">
              Interactive chat with LLM using MCP tools
              {messages.length > 0 && (
                <span className="ml-2 text-xs bg-primary/10 text-primary px-2 py-0.5 rounded border border-primary/20">
                  {messages.length} message{messages.length !== 1 ? 's' : ''} in history
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-3">
            {messages.length > 0 && (
              <button
                onClick={clearChatHistory}
                className="btn btn-secondary text-sm flex items-center gap-2"
                title="Clear chat history"
              >
                <Trash2 size={16} />
                <span>Clear History</span>
              </button>
            )}
          </div>
        </div>

      </div>

      {/* Active MCP Banner */}
      {activeProfile && (
        <div className="px-4 pt-4 bg-surface-elevated border-b border-border">
          {hasMultipleSelected ? (
            <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 flex items-start gap-3 mb-4">
              <div className="text-warning-light mt-0.5">⚠️</div>
              <div className="flex-1 text-sm">
                <p className="text-warning-light font-semibold mb-1">Multiple MCP Servers Selected</p>
                <p className="text-text-secondary">
                  Chat uses <strong className="text-text-primary">{activeProfile.split(':')[1] || activeProfile}</strong> only.
                  Use the Tests page to work with multiple servers simultaneously.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-info/10 border border-info/30 rounded-lg p-3 flex items-center gap-3 mb-4">
              <div className="text-info-light">ℹ️</div>
              <div className="text-sm text-text-secondary">
                Using tools from <strong className="text-info-light">{activeProfile.split(':')[1] || activeProfile}</strong>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 bg-background-subtle" role="log" aria-live="polite" aria-label="Chat messages">
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
                  {message.role === 'assistant' ? (
                    <>
                      {/* Model Indicator Pill */}
                      {message.model && (
                        <div className="mb-3 flex items-center gap-2">
                          {/* Provider/Model Pill */}
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
                            message.provider === 'anthropic' || message.provider === 'claude-sdk' || message.provider === 'claude-cli'
                              ? 'bg-orange-500/10 text-orange-400 border-orange-500/30'
                              : message.provider === 'openai' || message.provider === 'codex-cli'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                          }`}>
                            {message.provider === 'anthropic' || message.provider === 'claude-sdk' || message.provider === 'claude-cli' ? (
                              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M17.59 6.91L12 12.5L6.41 6.91L5 8.33L12 15.33L19 8.33L17.59 6.91Z"/>
                              </svg>
                            ) : message.provider === 'openai' || message.provider === 'codex-cli' ? (
                              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/>
                              </svg>
                            ) : (
                              <span className="w-3 h-3 rounded-full bg-current opacity-50"></span>
                            )}
                            <span>{message.model}</span>
                          </span>
                          {/* CLI/API/SDK Badge */}
                          {message.provider && (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
                              message.provider === 'claude-cli' || message.provider === 'codex-cli'
                                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                : message.provider === 'claude-sdk'
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : 'bg-slate-500/20 text-slate-300 border border-slate-500/30'
                            }`}>
                              {message.provider === 'claude-cli' ? (
                                <>
                                  <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="4 17 10 11 4 5"></polyline>
                                    <line x1="12" y1="19" x2="20" y2="19"></line>
                                  </svg>
                                  Claude CLI
                                </>
                              ) : message.provider === 'codex-cli' ? (
                                <>
                                  <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="4 17 10 11 4 5"></polyline>
                                    <line x1="12" y1="19" x2="20" y2="19"></line>
                                  </svg>
                                  Codex CLI
                                </>
                              ) : message.provider === 'claude-sdk' ? (
                                <>
                                  <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                    <line x1="3" y1="9" x2="21" y2="9"></line>
                                    <line x1="9" y1="21" x2="9" y2="9"></line>
                                  </svg>
                                  SDK
                                </>
                              ) : (
                                <>
                                  <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                                  </svg>
                                  API
                                </>
                              )}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Extended Thinking Section */}
                      {message.thinking && (
                        <div className="mb-3">
                          <button
                            onClick={() => setCollapsedThinking(prev => ({ ...prev, [idx]: !prev[idx] }))}
                            className="flex items-center gap-2 text-xs font-medium text-purple-400 hover:text-purple-300 transition-colors mb-2"
                          >
                            {collapsedThinking[idx] ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                            <Brain size={14} />
                            <span>Thinking</span>
                            <span className="text-white/40 font-normal">({message.thinking.length.toLocaleString()} chars)</span>
                          </button>
                          {!collapsedThinking[idx] && (
                            <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-3 text-sm text-white/80 max-h-64 overflow-y-auto">
                              <div className="whitespace-pre-wrap font-mono text-xs leading-relaxed">
                                {message.thinking}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {message.tool_calls && message.tool_calls.length > 0 && (
                        <div className="mb-3 p-2 bg-primary/10 border border-primary/30 rounded-lg text-xs text-white/70">
                          <span className="font-semibold text-primary-light">Note:</span> The LLM's interpretation may be inaccurate.
                          For actual tool results, see "Raw Tool Output" in the tool calls section below.
                        </div>
                      )}
                      <div className="prose prose-invert prose-sm max-w-none leading-relaxed prose-p:my-2 prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10 prose-code:text-primary-light prose-a:text-primary-light prose-a:no-underline hover:prose-a:underline prose-strong:text-white prose-headings:text-white">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            // Custom code block styling
                            code({node, inline, className, children, ...props}) {
                              return inline ? (
                                <code className="bg-black/50 px-1.5 py-0.5 rounded text-primary-light" {...props}>
                                  {children}
                                </code>
                              ) : (
                                <code className={className} {...props}>
                                  {children}
                                </code>
                              )
                            },
                            // Custom link styling to open in new tab
                            a({node, children, href, ...props}) {
                              return (
                                <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                                  {children}
                                </a>
                              )
                            }
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    </>
                  ) : (
                    <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
                  )}

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
                                    <span className="text-xs font-medium text-white/90">{evalItem.evaluator || evalItem.name || 'Unknown Evaluator'}</span>
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

                            {/* Arguments - shown as collapsible object */}
                            {call.arguments && Object.keys(call.arguments).length > 0 && (
                              <div className="mb-2">
                                <div className="text-xs text-white/60 mb-1">Arguments:</div>
                                <div className="bg-black/30 rounded p-2">
                                  <ReactJson
                                    src={call.arguments}
                                    theme="monokai"
                                    collapsed={1}
                                    displayDataTypes={false}
                                    displayObjectSize={true}
                                    enableClipboard={true}
                                    name="request"
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

                            {/* Result - shown as collapsible object (same as arguments) */}
                            {call.result && (
                              <div className="mt-3">
                                <div className="text-xs text-white/60 mb-2 font-semibold">Raw Tool Output:</div>
                                <div className="bg-black/40 rounded-lg p-3 border border-white/10 overflow-x-auto">
                                  <ReactJson
                                    src={(() => {
                                      // Parse JSON strings recursively
                                      const parseJsonStrings = (obj) => {
                                        if (obj === null || obj === undefined) return obj
                                        if (typeof obj === 'string') {
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
                                      return parseJsonStrings(call.result)
                                    })()}
                                    theme="monokai"
                                    collapsed={1}
                                    displayDataTypes={false}
                                    displayObjectSize={true}
                                    enableClipboard={true}
                                    name="response"
                                    indentWidth={2}
                                    iconStyle="triangle"
                                    style={{
                                      backgroundColor: 'transparent',
                                      fontSize: '12px',
                                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
                                    }}
                                  />
                                </div>
                              </div>
                            )}

                            {/* Error display */}
                            {call.error && (
                              <div className="mt-3 p-3 bg-error/10 border border-error/30 rounded-lg">
                                <div className="text-xs font-semibold text-error mb-1">Error:</div>
                                <div className="text-xs text-white/80 font-mono">{call.error}</div>
                              </div>
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
      <div className="p-3 border-t border-border bg-surface-elevated shadow-strong" role="form" aria-label="Chat input">
        <div className="max-w-4xl mx-auto flex gap-4">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyPress={handleKeyPress}
              placeholder="Type your message..."
              className="input w-full resize-none text-base overflow-y-auto pr-24"
              rows={1}
              disabled={loading}
              aria-label="Message input"
              aria-describedby="keyboard-hint"
            />
            <span id="keyboard-hint" className="absolute right-3 bottom-2 text-xs text-text-disabled pointer-events-none">
              {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+Enter
            </span>
          </div>
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="btn btn-primary h-fit self-end px-6"
            aria-label={loading ? 'Sending message...' : 'Send message'}
          >
            {loading ? <Loader size={20} className="animate-spin" /> : <Send size={20} />}
            <span>{loading ? 'Sending...' : 'Send'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

export default ChatInterface
