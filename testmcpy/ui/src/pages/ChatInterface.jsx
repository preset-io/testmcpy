import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useConfirm } from '../components/ConfirmDialog'
import { useNotification } from '../components/NotificationProvider'
import { Send, Loader, Wrench, DollarSign, ChevronDown, ChevronRight, CheckCircle, FileText, Trash2, RefreshCw, Download, Edit3, Settings2, Square } from 'lucide-react'
import ReactJson from '@microlink/react-json-view'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useKeyboardShortcuts, useAnnounce } from '../hooks/useKeyboardShortcuts'
import { useEditorTheme } from '../hooks/useEditorTheme'
import ToolCallTimeline from '../components/ToolCallTimeline'
import {
  CHAT_CLEAR_TOKEN_KEY,
  buildChatHistory,
  clearChatConversation,
  createChatMessageId,
  loadChatConversation,
  saveChatConversation,
} from '../utils/chatPersistence'

// JSON viewer component with IDE-like collapsible tree
function JSONViewer({ data }) {
  const { jsonTheme } = useEditorTheme()
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
        <div className="bg-background-subtle rounded-lg p-3 border border-border overflow-x-auto">
          <ReactJson
            src={parsedData}
            theme={jsonTheme}
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

function contextTrimmedMessage(notice) {
  const omitted = Number.isFinite(notice?.omitted_messages) ? notice.omitted_messages : 0
  const details = []
  if (omitted > 0) {
    details.push(`${omitted} older context message${omitted === 1 ? ' was' : 's were'} omitted`)
  }
  if (notice?.system_truncated) {
    details.push('the system prompt was shortened')
  }
  const summary = details.length > 0 ? details.join(' and ') : 'Some saved context was omitted'
  const sentence = summary.charAt(0).toUpperCase() + summary.slice(1)
  return `${sentence} to fit this model's context window. The full conversation remains saved in this browser.`
}

function ChatInterface({ selectedProfiles = [], selectedLlmProfile, llmProfiles = [] }) {
  const [confirmAction, confirmElement] = useConfirm()
  const { success: notifySuccess, error: notifyError, warning: notifyWarning } = useNotification()
  const initialConversationRef = useRef(null)
  if (initialConversationRef.current === null) {
    initialConversationRef.current = loadChatConversation()
  }
  const [messages, setMessages] = useState(initialConversationRef.current.messages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingStatus, setStreamingStatus] = useState('')
  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const shouldAutoScrollRef = useRef(true)
  const [evalResults, setEvalResults] = useState({})
  const [runningEval, setRunningEval] = useState(null)
  const textareaRef = useRef(null)
  const abortControllerRef = useRef(null)
  const activeRequestIdRef = useRef(0)
  const activeEvalRequestIdRef = useRef(0)
  const sendingRef = useRef(false)
  const [editingMessageIdx, setEditingMessageIdx] = useState(null)
  const [editingText, setEditingText] = useState('')
  const [systemPrompt, setSystemPrompt] = useState(initialConversationRef.current.systemPrompt)
  const [showSystemPrompt, setShowSystemPrompt] = useState(false)
  const [expandedToolCalls, setExpandedToolCalls] = useState({})
  const messagesRef = useRef(messages)
  const systemPromptRef = useRef(systemPrompt)
  const persistenceWarningShownRef = useRef(false)
  const persistenceGenerationRef = useRef(0)
  const persistenceClearTokenRef = useRef(initialConversationRef.current.clearToken)
  const initialLastMessage = initialConversationRef.current.messages[
    initialConversationRef.current.messages.length - 1
  ]
  const lastAnnouncedMessageIdRef = useRef(
    initialLastMessage?.id || null,
  )

  // For Chat, only use the first selected profile (single MCP at a time)
  const activeProfile = selectedProfiles.length > 0 ? selectedProfiles[0] : null
  const hasMultipleSelected = selectedProfiles.length > 1
  const contextMessageCount = messages.reduce((count, message) => {
    if (message.role === 'user' && message.content?.trim()) return count + 1
    const hasCompletedToolCall = message.tool_calls?.some(call => call && (
      call.completed === true
      || call.result != null
      || Boolean(call.error)
      || call.is_error === true
    ))
    if (
      message.role === 'assistant'
      && !message.error
      && !message.cancelled
      && !message.interrupted
      && !message.streaming
      && (message.content?.trim() || hasCompletedToolCall)
    ) return count + 1
    return count
  }, 0)

  // Get model and provider from LLM profile
  const getLlmConfig = () => {
    if (!selectedLlmProfile || llmProfiles.length === 0) {
      return { model: null, provider: null }
    }

    const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
    if (!profile) {
      return { model: null, provider: null }
    }

    const defaultProvider = profile.providers?.find(p => p.default) || profile.providers?.[0]
    return {
      model: defaultProvider?.model || null,
      provider: defaultProvider?.provider || null
    }
  }

  const persistConversation = useCallback((messagesToSave, promptToSave) => {
    const result = saveChatConversation({
      messages: messagesToSave,
      systemPrompt: promptToSave,
      clearToken: persistenceClearTokenRef.current,
    })

    // A newer clear token is an expected cross-tab synchronization event, not
    // a browser storage failure. The storage listener below owns resetting
    // this tab and aborting any in-flight work.
    if (result.stale) return result

    if (!persistenceWarningShownRef.current && (!result.ok || result.compacted)) {
      persistenceWarningShownRef.current = true
      notifyWarning(
        result.compacted
          ? 'The conversation was saved without large tool traces because browser storage is full.'
          : 'This browser could not save the conversation. Keep this tab open to avoid losing context.',
      )
    }
    return result
  }, [notifyWarning])

  const saveChatHistory = useCallback((messagesToSave) => {
    return persistConversation(messagesToSave, systemPromptRef.current)
  }, [persistConversation])

  useEffect(() => {
    checkForPrefillTool()

    const initial = initialConversationRef.current
    if (initial.error) {
      const clearResult = clearChatConversation()
      if (clearResult.ok) persistenceClearTokenRef.current = clearResult.clearToken
      notifyWarning('Saved chat data was invalid and could not be restored. A new conversation was started.')
    } else if (initial.migrated) {
      persistConversation(initial.messages, initial.systemPrompt)
    }
  }, [notifyWarning, persistConversation])

  // Keep the canonical conversation durable while streaming without writing
  // localStorage for every token. Semantic changes are saved after a short
  // debounce, and route changes/browser unloads synchronously flush the refs.
  useEffect(() => {
    messagesRef.current = messages
    systemPromptRef.current = systemPrompt
    const persistenceGeneration = persistenceGenerationRef.current
    const timer = window.setTimeout(() => {
      if (persistenceGenerationRef.current === persistenceGeneration) {
        persistConversation(messages, systemPrompt)
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [messages, systemPrompt, persistConversation])

  useEffect(() => {
    const flushConversation = () => {
      persistConversation(messagesRef.current, systemPromptRef.current)
    }
    window.addEventListener('pagehide', flushConversation)
    return () => {
      window.removeEventListener('pagehide', flushConversation)
      flushConversation()
      abortControllerRef.current?.abort()
    }
  }, [persistConversation])

  // A clear action in another tab must not be undone when this tab later
  // unloads and flushes stale refs back into storage.
  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key !== CHAT_CLEAR_TOKEN_KEY || event.newValue === null) return

      const stored = loadChatConversation()
      if (stored.clearToken === persistenceClearTokenRef.current) return

      activeRequestIdRef.current += 1
      activeEvalRequestIdRef.current += 1
      persistenceGenerationRef.current += 1
      abortControllerRef.current?.abort()
      abortControllerRef.current = null
      sendingRef.current = false
      messagesRef.current = []
      systemPromptRef.current = ''
      persistenceClearTokenRef.current = stored.clearToken
      setLoading(false)
      setStreamingStatus('')
      setMessages([])
      setSystemPrompt('')
      setInput('')
      setEditingMessageIdx(null)
      setEditingText('')
      setEvalResults({})
      setRunningEval(null)
      setExpandedToolCalls({})
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      scrollToBottom(loading ? 'auto' : 'smooth')
    }
  }, [messages, loading])

  // Reset textarea height when input is cleared
  useEffect(() => {
    if (input === '' && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input])

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

  const clearChatHistory = () => {
    // Invalidate before aborting so queued stream callbacks cannot repopulate
    // the conversation after the user has explicitly cleared it.
    activeRequestIdRef.current += 1
    activeEvalRequestIdRef.current += 1
    persistenceGenerationRef.current += 1
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    sendingRef.current = false
    setLoading(false)
    setStreamingStatus('')
    setMessages([])
    messagesRef.current = []
    setSystemPrompt('')
    systemPromptRef.current = ''
    setInput('')
    setEditingMessageIdx(null)
    setEditingText('')
    setEvalResults({})
    setRunningEval(null)
    setExpandedToolCalls({})
    const clearResult = clearChatConversation()
    if (clearResult.ok) persistenceClearTokenRef.current = clearResult.clearToken
    if (!clearResult.ok) {
      notifyError('The conversation was cleared on screen, but browser storage could not be updated.')
    }
  }

  // Regenerate: resend the last user message
  const regenerateLastResponse = () => {
    if (loading || messages.length < 2) return
    // Find last user message
    let lastUserIdx = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { lastUserIdx = i; break }
    }
    if (lastUserIdx < 0) return
    const lastUserMsg = messages[lastUserIdx].content
    // Remove messages from last user message onward
    const trimmed = messages.slice(0, lastUserIdx)
    setMessages(trimmed)
    activeEvalRequestIdRef.current += 1
    setEvalResults({})
    setRunningEval(null)
    saveChatHistory(trimmed)
    void sendMessage({ text: lastUserMsg, baseMessages: trimmed })
  }

  // Edit a user message: trim conversation and re-send
  const editAndResend = (idx) => {
    if (loading) return
    const editedMessage = editingText.trim()
    if (!editedMessage) return
    const trimmed = messages.slice(0, idx)
    setMessages(trimmed)
    activeEvalRequestIdRef.current += 1
    setEvalResults({})
    setRunningEval(null)
    saveChatHistory(trimmed)
    setEditingMessageIdx(null)
    setEditingText('')
    void sendMessage({ text: editedMessage, baseMessages: trimmed })
  }

  // Export conversation as markdown
  const exportAsMarkdown = () => {
    const lines = messages.map(m => {
      const role = m.role === 'user' ? '**User**' : '**Assistant**'
      let text = `### ${role}\n\n${m.content || ''}\n`
      if (m.tool_calls && m.tool_calls.length > 0) {
        text += `\n_Tool calls: ${m.tool_calls.map(tc => tc.name).join(', ')}_\n`
      }
      return text
    })
    if (systemPrompt) {
      lines.unshift(`### System Prompt\n\n${systemPrompt}\n\n---\n`)
    }
    const md = lines.join('\n---\n\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat_export_${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scrollToBottom = (behavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior })
  }

  const handleMessagesScroll = () => {
    const container = messagesContainerRef.current
    if (!container) return
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    shouldAutoScrollRef.current = distanceFromBottom < 120
  }

  const sendMessage = async ({ text = input, baseMessages = messages } = {}) => {
    const messageText = text.trim()
    if (!messageText || sendingRef.current) return
    sendingRef.current = true
    const requestId = activeRequestIdRef.current + 1
    activeRequestIdRef.current = requestId

    const userMessage = { id: createChatMessageId(), role: 'user', content: messageText }
    const updatedMessages = [...baseMessages, userMessage]
    setMessages(updatedMessages)
    messagesRef.current = updatedMessages
    // Save the user's turn before starting network work so a route change or
    // reload cannot lose the latest request.
    saveChatHistory(updatedMessages)
    setInput('')
    shouldAutoScrollRef.current = true
    setLoading(true)
    setStreamingStatus('Connecting...')

    // Create a placeholder assistant message
    const assistantMessage = {
      id: createChatMessageId(),
      role: 'assistant',
      content: '',
      tool_calls: [],
      thinking: null,
      token_usage: null,
      cost: 0,
      duration: 0,
      model: null,
      provider: null,
      streaming: true,
      currentTurn: 0,
      totalTurns: 0,
    }
    const messagesWithPlaceholder = [...updatedMessages, assistantMessage]
    setMessages(messagesWithPlaceholder)
    messagesRef.current = messagesWithPlaceholder

    // Track the assistant message index for updates
    const assistantIdx = updatedMessages.length

    const updateAssistantMessage = (patch, { persist = false } = {}) => {
      if (activeRequestIdRef.current !== requestId) return
      const currentMessages = messagesRef.current
      const current = currentMessages[assistantIdx]
      if (!current) return
      const nextMessage = typeof patch === 'function' ? patch(current) : { ...current, ...patch }
      const updated = [...currentMessages]
      updated[assistantIdx] = nextMessage
      messagesRef.current = updated
      setMessages(updated)
      if (persist) saveChatHistory(updated)
    }

    const abortController = new AbortController()
    abortControllerRef.current = abortController
    // Keep terminal state visible to both the stream loop and AbortError
    // handling. Declaring these inside `try` would make Stop fail after a
    // completed/error event because `catch` is a sibling block in JavaScript.
    let sawComplete = false
    let sawError = false

    try {
      // Reconstruct the complete, successful transcript on every request.
      // This is independent of the selected model, so switching profiles or
      // restarting the server does not reset the conversation.
      const historyForAPI = buildChatHistory(baseMessages, systemPrompt)

      const llmConfig = getLlmConfig()
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          model: llmConfig.model,
          provider: llmConfig.provider,
          llm_profile: selectedLlmProfile,
          profiles: activeProfile ? [activeProfile] : null,
          history: historyForAPI.length > 0 ? historyForAPI : null,
        }),
        signal: abortController.signal,
      })

      if (!res.ok) {
        const errorText = await res.text()
        let detail = errorText
        try {
          const parsed = JSON.parse(errorText)
          detail = parsed.detail || parsed.message || errorText
        } catch {
          // Keep the plain-text server response.
        }
        throw new Error(detail || `Request failed with HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // Accumulate state for the assistant message
      let accContent = ''
      let accThinking = ''
      let accToolCalls = []
      let currentTurn = 0
      let totalTurns = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // keep incomplete line in buffer

        for (const line of lines) {
          if (activeRequestIdRef.current !== requestId) break
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6)
          if (!jsonStr.trim()) continue

          let event
          try {
            event = JSON.parse(jsonStr)
          } catch (e) {
            console.warn('Failed to parse SSE event:', jsonStr)
            continue
          }

          const { type, data } = event

          if (type === 'status') {
            setStreamingStatus(data)
          } else if (type === 'context_trimmed') {
            updateAssistantMessage({ context_trimmed: data })
            setStreamingStatus('Using the most recent context that fits this model...')
          } else if (type === 'turn_start') {
            currentTurn = data.turn
            updateAssistantMessage({ currentTurn: data.turn })
            // Show the denominator only when the backend caps turns (non-SDK
            // manual loop). SDK-backed runs are open-ended, so show "Turn n".
            setStreamingStatus(
              data.max_turns
                ? `Turn ${data.turn}/${data.max_turns} — Thinking...`
                : `Turn ${data.turn} — Thinking...`
            )
          } else if (type === 'thinking') {
            accThinking += data
            updateAssistantMessage({ thinking: accThinking })
          } else if (type === 'token') {
            accContent += data
            updateAssistantMessage({ content: accContent })
            if (currentTurn > 1) {
              setStreamingStatus(`Turn ${currentTurn} — Streaming response...`)
            } else {
              setStreamingStatus('')
            }
          } else if (type === 'tool_call') {
            const turn = data.turn || currentTurn || 1
            accToolCalls = [...accToolCalls, { id: data.id, name: data.name, arguments: data.arguments, result: null, error: null, is_error: false, completed: false, turn }]
            updateAssistantMessage({ tool_calls: accToolCalls })
            setStreamingStatus(`Turn ${turn} — Executing: ${data.name}...`)
          } else if (type === 'tool_result') {
            const turn = data.turn || currentTurn || 1
            // Update the matching tool call with its result (match by unique tool ID)
            accToolCalls = accToolCalls.map(tc =>
              tc.id && data.id && tc.id === data.id
                ? { ...tc, result: data.result, error: data.error, is_error: data.is_error, completed: true }
                : (!tc.id && tc.name === data.name && tc.result === null && tc.turn === turn)
                  ? { ...tc, result: data.result, error: data.error, is_error: data.is_error, completed: true }
                  : tc
            )
            updateAssistantMessage({ tool_calls: accToolCalls })
            setStreamingStatus('')
          } else if (type === 'turn_complete') {
            totalTurns = data.turn
            updateAssistantMessage({ totalTurns: data.turn })
            if (data.tool_count > 0) {
              setStreamingStatus(`Turn ${data.turn} complete (${data.tool_count} tool${data.tool_count !== 1 ? 's' : ''})`)
            }
          } else if (type === 'complete') {
            sawComplete = true
            updateAssistantMessage(current => ({
                ...current,
                token_usage: data.token_usage,
                cost: data.cost || 0,
                duration: data.duration || 0,
                model: data.model,
                provider: data.provider,
                totalTurns: data.total_turns || totalTurns || 1,
                streaming: false,
              }))
          } else if (type === 'error') {
            sawError = true
            const errorMessage = typeof data === 'string'
              ? data
              : data?.detail || data?.message || JSON.stringify(data)
            updateAssistantMessage(current => ({
                ...current,
                content: `Error: ${errorMessage}`,
                error: true,
                streaming: false,
              }))
          }
        }

        if (sawComplete || sawError) {
          await reader.cancel?.()
          break
        }
      }

      if (!sawComplete && !sawError) {
        updateAssistantMessage(current => ({
          ...current,
          content: current.content
            ? `${current.content}\n\n[Response interrupted]`
            : 'Error: The response ended before completion.',
          interrupted: true,
          error: true,
          streaming: false,
        }), { persist: true })
      } else {
        updateAssistantMessage({ streaming: false }, { persist: true })
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        if (!sawComplete && !sawError) {
          updateAssistantMessage(current => ({
            ...current,
            content: `${current.content}\n\n[Cancelled]`.trim(),
            cancelled: true,
            streaming: false,
          }), { persist: true })
        }
      } else {
        console.error('Failed to send message:', error)
        updateAssistantMessage({
          content: `Error: ${error.message}`,
          error: true,
          streaming: false,
        }, { persist: true })
      }
    } finally {
      if (activeRequestIdRef.current === requestId) {
        sendingRef.current = false
        setLoading(false)
        setStreamingStatus('')
        abortControllerRef.current = null
      }
    }
  }

  // Screen reader announcements
  const announce = useAnnounce()

  // Announce new messages for screen readers
  useEffect(() => {
    if (messages.length > 0) {
      const lastMessage = messages[messages.length - 1]
      if (
        lastMessage.role === 'assistant'
        && lastMessage.content
        && !lastMessage.streaming
        && lastAnnouncedMessageIdRef.current !== lastMessage.id
      ) {
        const preview = lastMessage.content.substring(0, 100)
        announce(`New response: ${preview}${lastMessage.content.length > 100 ? '...' : ''}`)
        lastAnnouncedMessageIdRef.current = lastMessage.id
      }
    }
  }, [messages, announce])

  const requestClearChat = useCallback(async () => {
    if (messages.length === 0 && !systemPrompt.trim()) return
    const confirmed = await confirmAction({
      title: 'Clear conversation',
      message: loading
        ? 'Stop the current response and clear all messages and the saved system prompt? This cannot be undone.'
        : 'Clear all messages and the saved system prompt? This cannot be undone.',
      confirmLabel: 'Clear',
    })
    if (confirmed) {
      clearChatHistory()
      announce('Conversation cleared')
    }
  }, [messages, systemPrompt, loading, announce, confirmAction])

  const handleClearShortcut = useCallback((e) => {
    e.preventDefault()
    void requestClearChat()
  }, [requestClearChat])

  // Register keyboard shortcuts
  useKeyboardShortcuts({
    'ctrl+shift+c': handleClearShortcut,
  })

  const handleKeyDown = (e) => {
    if (e.nativeEvent?.isComposing || e.isComposing) return
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage()
    }
  }

  const stopGeneration = () => {
    abortControllerRef.current?.abort()
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

    const evalRequestId = activeEvalRequestIdRef.current + 1
    activeEvalRequestIdRef.current = evalRequestId
    const assistantMessageId = assistantMessage.id
    setRunningEval(messageIndex)

    const isCurrentEval = () => (
      activeEvalRequestIdRef.current === evalRequestId
      && messagesRef.current[messageIndex]?.id === assistantMessageId
    )

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

      if (!isCurrentEval()) return

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
      if (!isCurrentEval()) return
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
      if (activeEvalRequestIdRef.current === evalRequestId) {
        setRunningEval(null)
      }
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
        notifySuccess(`Test case created: ${testName}.yaml`)
      } else {
        const error = await res.json().catch(() => ({ detail: 'Unknown error' }))
        console.error('Failed to create test:', error)
        notifyError(`Failed to create test case: ${error.detail}`)
      }
    } catch (error) {
      console.error('Failed to create test case:', error)
      notifyError(`Failed to create test case: ${error.message}`)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {confirmElement}
      {/* Header */}
      <div className="p-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h1 className="text-xl md:text-2xl font-semibold text-text-primary">Chat Interface</h1>
            <p className="text-text-secondary mt-1 text-base">
              Interactive chat with LLM using MCP tools
              {messages.length > 0 && (
                <span className="ml-2 text-xs bg-primary/10 text-primary px-2 py-0.5 rounded border border-primary/20">
                  {contextMessageCount} context message{contextMessageCount !== 1 ? 's' : ''}
                </span>
              )}
            </p>
            <p className="text-text-tertiary mt-1 text-xs">
              Saved in this browser until you clear it; context continues across model changes and reloads.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setShowSystemPrompt(!showSystemPrompt)}
              className={`btn ${showSystemPrompt ? 'btn-primary' : 'btn-secondary'} text-sm flex items-center gap-2`}
              title="System prompt"
              aria-label="Configure system prompt"
            >
              <Settings2 size={16} />
              <span className="hidden sm:inline">System</span>
            </button>
            {messages.length >= 2 && (
              <button
                onClick={regenerateLastResponse}
                disabled={loading}
                className="btn btn-secondary text-sm flex items-center gap-2"
                title="Regenerate last response"
                aria-label="Regenerate last response"
              >
                <RefreshCw size={16} />
                <span className="hidden sm:inline">Regenerate</span>
              </button>
            )}
            {(messages.length > 0 || systemPrompt.trim()) && (
              <>
                <button
                  onClick={exportAsMarkdown}
                  className="btn btn-secondary text-sm flex items-center gap-2"
                  title="Export as Markdown"
                  aria-label="Export conversation as Markdown"
                >
                  <Download size={16} />
                  <span className="hidden sm:inline">Export</span>
                </button>
                <button
                  onClick={() => void requestClearChat()}
                  className="btn btn-secondary text-sm flex items-center gap-2"
                  title="Clear the saved conversation"
                  aria-label="Clear saved conversation"
                >
                  <Trash2 size={16} />
                  <span className="hidden sm:inline">Clear</span>
                </button>
              </>
            )}
          </div>
        </div>

      </div>

      {/* System Prompt */}
      {showSystemPrompt && (
        <div className="px-4 py-3 border-b border-border bg-surface">
          <label htmlFor="chat-system-prompt" className="block text-xs font-semibold text-text-secondary mb-1">System Prompt</label>
          <textarea
            id="chat-system-prompt"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Enter a system prompt to guide the LLM's behavior..."
            className="input w-full text-sm"
            rows={3}
          />
          <p className="mt-1 text-[11px] text-text-tertiary">Saved with this conversation and cleared with it.</p>
        </div>
      )}

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
      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        className="flex-1 overflow-auto p-4 bg-background-subtle"
        role="log"
        aria-live="off"
        aria-label="Chat messages"
      >
        {messages.length === 0 && !loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-text-secondary mb-2">Chat with your MCP tools</h2>
              <p className="text-text-tertiary text-sm">Send a message to start a conversation with your configured MCP servers</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {["List all available tools", "What can you help me with?", "Run a health check", "Show available resources"].map(examplePrompt => (
                <button
                  key={examplePrompt}
                  onClick={() => setInput(examplePrompt)}
                  className="px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg hover:bg-surface-hover text-text-secondary cursor-pointer"
                >
                  {examplePrompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto pb-4">
            {messages.map((message, idx) => (
              <div
                key={message.id || idx}
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
                            message.provider === 'anthropic' || message.provider === 'claude-sdk'
                              ? 'bg-orange-500/10 text-orange-400 border-orange-500/30'
                              : message.provider === 'openai' || message.provider === 'codex-cli'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                          }`}>
                            {message.provider === 'anthropic' || message.provider === 'claude-sdk' ? (
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
                          {/* Provider Badge */}
                          {message.provider && (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
                              message.provider === 'codex-cli'
                                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                : message.provider === 'claude-sdk'
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : 'bg-slate-500/20 text-slate-300 border border-slate-500/30'
                            }`}>
                              {message.provider === 'codex-cli' ? (
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
                                  Agent SDK
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

                      {message.context_trimmed && (
                        <div className="mb-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-text-secondary" role="note">
                          {contextTrimmedMessage(message.context_trimmed)}
                        </div>
                      )}

                      {/* Tool Call & Thinking Timeline (compact, Agor-style) */}
                      {(message.thinking || (message.tool_calls && message.tool_calls.length > 0)) && (
                        <ToolCallTimeline
                          toolCalls={message.tool_calls || []}
                          thinking={message.thinking}
                          streaming={message.streaming}
                        />
                      )}
                      {message.streaming && !message.content && idx === messages.length - 1 ? (
                        <div className="flex gap-1 items-center p-3">
                          <div className="w-2 h-2 rounded-full bg-text-disabled animate-bounce [animation-delay:-0.3s]" />
                          <div className="w-2 h-2 rounded-full bg-text-disabled animate-bounce [animation-delay:-0.15s]" />
                          <div className="w-2 h-2 rounded-full bg-text-disabled animate-bounce" />
                        </div>
                      ) : (
                        <div className="prose dark:prose-invert prose-sm max-w-none leading-relaxed prose-p:my-2 prose-pre:bg-background-subtle prose-pre:border prose-pre:border-border prose-code:text-primary-light prose-a:text-primary-light prose-a:no-underline hover:prose-a:underline prose-strong:text-text-primary prose-headings:text-text-primary">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              // Custom code block styling
                              code({node, inline, className, children, ...props}) {
                                return inline ? (
                                  <code className="bg-background-subtle px-1.5 py-0.5 rounded text-primary-light" {...props}>
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
                            {message.content || ''}
                          </ReactMarkdown>
                          {message.streaming && message.content && (
                            <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-0.5 align-text-bottom" />
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    editingMessageIdx === idx ? (
                      <div className="space-y-2">
                        <textarea
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                          className="w-full bg-white/10 rounded p-2 text-sm resize-none"
                          rows={3}
                          autoFocus
                        />
                        <div className="flex gap-2">
                          <button onClick={() => editAndResend(idx)} className="text-xs bg-white/20 hover:bg-white/30 px-2 py-1 rounded">Send</button>
                          <button onClick={() => setEditingMessageIdx(null)} className="text-xs bg-white/10 hover:bg-white/20 px-2 py-1 rounded">Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap leading-relaxed group/msg">
                        {message.content}
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditingMessageIdx(idx); setEditingText(message.content) }}
                          className="ml-2 inline-flex opacity-0 group-hover/msg:opacity-100 focus:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/20"
                          title="Edit message"
                          aria-label="Edit this message and resend"
                        >
                          <Edit3 size={12} />
                        </button>
                      </div>
                    )
                  )}

                  {/* Eval and Test Actions for Assistant Messages — hidden while streaming */}
                  {message.role === 'assistant' && !message.error && !message.streaming && (
                    <div className="mt-4 pt-4 border-t border-border flex gap-2">
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
                    <div className="mt-4 pt-4 border-t border-border">
                      <div className="flex items-center gap-2 mb-3">
                        <CheckCircle size={16} className={evalResults[idx].passed ? 'text-success' : 'text-error'} />
                        <span className="font-semibold text-sm">
                          Eval: {evalResults[idx].passed ? 'PASSED' : 'FAILED'}
                        </span>
                        <span className="text-xs text-text-tertiary">
                          Score: {evalResults[idx].score?.toFixed(2) || 'N/A'}
                        </span>
                      </div>
                      {evalResults[idx].reason && (
                        <p className="text-xs text-text-secondary leading-relaxed mb-3">
                          {evalResults[idx].reason}
                        </p>
                      )}

                      {/* Tool Calls Summary */}
                      {message.tool_calls && message.tool_calls.length > 0 && (
                        <div className="mb-3 bg-background-subtle rounded-lg p-3 border border-border">
                          <div className="text-xs text-text-tertiary mb-2 flex items-center gap-2">
                            <Wrench size={12} />
                            <span className="font-medium">Tool Calls ({message.tool_calls.length})</span>
                            {message.tool_calls.length > 3 && (
                              <button
                                onClick={() => setExpandedToolCalls(prev => ({ ...prev, [idx]: !prev[idx] }))}
                                className="ml-auto text-[10px] text-primary-light hover:underline"
                              >
                                {expandedToolCalls[idx] ? 'Hide' : 'Show all'}
                              </button>
                            )}
                          </div>
                          <div className="space-y-2">
                            {(message.tool_calls.length > 3 && !expandedToolCalls[idx]
                              ? message.tool_calls.slice(0, 3)
                              : message.tool_calls
                            ).map((call, callIdx) => (
                              <div key={callIdx} className="bg-surface-hover rounded p-2">
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
                                    <div className="text-[10px] text-text-disabled mb-1">Parameters:</div>
                                    <div className="space-y-1">
                                      {Object.entries(call.arguments).map(([key, value]) => (
                                        <div key={key} className="flex items-start gap-2 text-[11px]">
                                          <span className="text-text-tertiary font-medium min-w-[80px]">{key}:</span>
                                          <span className="text-text-secondary font-mono flex-1 break-all">
                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                            {message.tool_calls.length > 3 && !expandedToolCalls[idx] && (
                              <div className="text-[10px] text-text-tertiary text-center py-1">
                                +{message.tool_calls.length - 3} more tool call{message.tool_calls.length - 3 !== 1 ? 's' : ''}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Individual evaluator results */}
                      {evalResults[idx].evaluations && evalResults[idx].evaluations.length > 0 && (
                        <div className="space-y-2 mt-3">
                          {evalResults[idx].evaluations.map((evalItem, evalIdx) => (
                            <div key={evalIdx} className="bg-surface-hover rounded-lg p-2.5 border border-border">
                              <div className="flex items-start gap-2">
                                <CheckCircle size={14} className={evalItem.passed ? 'text-success mt-0.5' : 'text-error mt-0.5'} />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <span className="text-xs font-medium text-text-primary">{evalItem.evaluator || evalItem.name || 'Unknown Evaluator'}</span>
                                    <span className="text-[10px] text-text-disabled">
                                      {evalItem.passed ? '✓' : '✗'} Score: {evalItem.score?.toFixed(2)}
                                    </span>
                                  </div>
                                  {evalItem.reason && (
                                    <p className="text-[11px] text-text-secondary leading-relaxed">
                                      {evalItem.reason}
                                    </p>
                                  )}
                                  {/* Show error details if present */}
                                  {evalItem.details && evalItem.details.errors && (
                                    <div className="mt-2 bg-error/10 border border-error/30 rounded p-2">
                                      <div className="text-[10px] font-semibold text-error-light mb-1">Error Details:</div>
                                      {evalItem.details.errors.map((err, errIdx) => (
                                        <div key={errIdx} className="text-[10px] text-text-secondary mb-1">
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


                  {/* Metadata - inline */}
                  {message.token_usage && (
                    <div className="mt-3 pt-3 border-t border-border flex items-center gap-4 text-[10px] opacity-70">
                      {message.totalTurns > 1 && (
                        <span className="flex items-center gap-1">
                          <span className="font-medium">{message.totalTurns}</span> turns
                        </span>
                      )}
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
            {loading && streamingStatus && (
              <div className="flex justify-start animate-fade-in">
                <div className="bg-surface border border-border rounded-xl p-5 shadow-soft">
                  <div className="flex items-center gap-3">
                    <Loader className="animate-spin text-primary" size={20} />
                    <span className="text-text-secondary text-sm">{streamingStatus}</span>
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
        <div className="max-w-4xl mx-auto flex gap-2 md:gap-4">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              className="input w-full resize-none text-base overflow-y-auto pr-24"
              rows={1}
              disabled={loading}
              aria-label="Message input"
              aria-describedby="keyboard-hint"
            />
            <span id="keyboard-hint" className="hidden sm:block absolute right-3 bottom-2 text-xs text-text-disabled pointer-events-none">
              Enter to send · Shift+Enter for new line
            </span>
          </div>
          <button
            onClick={loading ? stopGeneration : () => void sendMessage()}
            disabled={!loading && !input.trim()}
            className={`btn h-fit self-end px-6 ${loading ? 'btn-secondary' : 'btn-primary'}`}
            aria-label={loading ? 'Stop generating response' : 'Send message'}
          >
            {loading ? <Square size={18} /> : <Send size={20} />}
            <span className="hidden sm:inline">{loading ? 'Stop' : 'Send'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

export default ChatInterface
