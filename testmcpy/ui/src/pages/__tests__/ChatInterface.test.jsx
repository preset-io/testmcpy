import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { NotificationProvider } from '../../components/NotificationProvider'
import {
  CHAT_CLEAR_TOKEN_KEY,
  CHAT_STORAGE_KEY,
  LEGACY_CHAT_STORAGE_KEY,
  loadChatConversation,
  saveChatConversation,
} from '../../utils/chatPersistence'
import ChatInterface, { turnStartStatus } from '../ChatInterface'

vi.mock('@microlink/react-json-view', () => ({ default: () => null }))
vi.mock('react-markdown', () => ({ default: ({ children }) => children }))
vi.mock('remark-gfm', () => ({ default: () => null }))
vi.mock('../../hooks/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => {},
  useAnnounce: () => vi.fn(),
}))
vi.mock('../../hooks/useEditorTheme', () => ({
  useEditorTheme: () => ({ jsonTheme: 'rjv-default' }),
}))
vi.mock('../../components/ToolCallTimeline', () => ({ default: () => null }))

const llmProfiles = [
  {
    profile_id: 'profile-a',
    name: 'Profile A',
    providers: [{ default: true, provider: 'anthropic', model: 'claude-a' }],
  },
  {
    profile_id: 'profile-b',
    name: 'Profile B',
    providers: [{ default: true, provider: 'openai', model: 'gpt-b' }],
  },
]

function renderChat(props = {}) {
  return render(
    <BrowserRouter>
      <NotificationProvider>
        <ChatInterface llmProfiles={llmProfiles} {...props} />
      </NotificationProvider>
    </BrowserRouter>,
  )
}

function encodeSse(events) {
  return new TextEncoder().encode(
    events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''),
  )
}

function sseResponse({
  content = 'assistant answer',
  model = 'gpt-b',
  provider = 'openai',
  events,
} = {}) {
  const payload = events || [
    { type: 'token', data: content },
    {
      type: 'complete',
      data: {
        token_usage: { prompt: 2, completion: 3, total: 5 },
        cost: 0,
        duration: 0.01,
        model,
        provider,
        total_turns: 1,
      },
    },
  ]
  const bytes = encodeSse(payload)
  let readCount = 0

  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn(async () => {
          if (readCount === 0) {
            readCount += 1
            return { done: false, value: bytes }
          }
          return { done: true, value: undefined }
        }),
      }),
    },
  }
}

function abortableSseResponse(signal, content = 'partial answer') {
  const firstChunk = encodeSse([{ type: 'token', data: content }])
  let readCount = 0

  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn(() => {
          if (readCount === 0) {
            readCount += 1
            return Promise.resolve({ done: false, value: firstChunk })
          }

          return new Promise((resolve, reject) => {
            const rejectAsAborted = () => {
              const error = new Error('The operation was aborted')
              error.name = 'AbortError'
              reject(error)
            }
            if (signal.aborted) {
              rejectAsAborted()
            } else {
              signal.addEventListener('abort', rejectAsAborted, { once: true })
            }
          })
        }),
      }),
    },
  }
}

function chatRequests() {
  return global.fetch.mock.calls.filter(([url]) => url === '/api/chat/stream')
}

function requestBody(index = 0) {
  return JSON.parse(chatRequests()[index][1].body)
}

function createTestStorage() {
  const values = new Map()
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => values.set(key, String(value)),
  }
}

beforeEach(() => {
  vi.stubGlobal('localStorage', createTestStorage())
  global.fetch = vi.fn(async () => sseResponse())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ChatInterface conversation persistence', () => {
  it('lets the server resolve its configured default when no LLM profile is selected', async () => {
    renderChat()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Message input'), 'use the configured default')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('assistant answer')).toBeInTheDocument()

    expect(requestBody()).toMatchObject({
      message: 'use the configured default',
      model: null,
      provider: null,
      history: null,
    })
    expect(requestBody()).not.toHaveProperty('llm_profile')
  })

  it('restores the full transcript after remount and sends it to a newly selected model', async () => {
    const priorMessages = Array.from({ length: 12 }, (_, index) => ({
      id: `saved-${index}`,
      role: index % 2 === 0 ? 'user' : 'assistant',
      content: `saved message ${index + 1}`,
      ...(index % 2 === 1 ? { model: 'claude-a', provider: 'anthropic' } : {}),
    }))
    saveChatConversation({ messages: priorMessages, systemPrompt: 'Be concise.' })

    const firstMount = renderChat({
      selectedProfiles: ['mcp-profile:Server A'],
      selectedLlmProfile: 'profile-a',
    })
    expect(screen.getByText('saved message 1')).toBeInTheDocument()
    expect(screen.getByText('saved message 12')).toBeInTheDocument()
    expect(screen.getByText('12 context messages')).toBeInTheDocument()

    firstMount.unmount()

    renderChat({
      selectedProfiles: ['mcp-profile:Server A'],
      selectedLlmProfile: 'profile-b',
    })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Message input'), 'continue after switching models')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('assistant answer')).toBeInTheDocument()

    expect(chatRequests()).toHaveLength(1)
    expect(requestBody()).toEqual({
      message: 'continue after switching models',
      model: 'gpt-b',
      provider: 'openai',
      llm_profile: 'profile-b',
      profiles: ['mcp-profile:Server A'],
      history: [
        { role: 'system', content: 'Be concise.' },
        ...priorMessages.map(({ role, content }) => ({ role, content })),
      ],
    })
    expect(requestBody().history).toHaveLength(13)
  })

  it('persists the system prompt across remount and clears every source of context', async () => {
    const firstMount = renderChat({ selectedLlmProfile: 'profile-a' })
    const user = userEvent.setup()

    await user.click(screen.getByTitle('System prompt'))
    const systemPromptInput = screen.getByPlaceholderText(
      "Enter a system prompt to guide the LLM's behavior...",
    )
    await user.type(systemPromptInput, 'Answer as a terse debugger.')

    await waitFor(() => {
      expect(loadChatConversation().systemPrompt).toBe('Answer as a terse debugger.')
    })
    firstMount.unmount()

    renderChat({ selectedLlmProfile: 'profile-b' })
    await user.click(screen.getByTitle('System prompt'))
    expect(screen.getByPlaceholderText(
      "Enter a system prompt to guide the LLM's behavior...",
    )).toHaveValue('Answer as a terse debugger.')

    await user.click(screen.getByTitle('Clear the saved conversation'))
    const dialog = screen.getByRole('dialog', { name: 'Clear conversation' })
    await user.click(within(dialog).getByRole('button', { name: 'Clear' }))

    expect(screen.getByPlaceholderText(
      "Enter a system prompt to guide the LLM's behavior...",
    )).toHaveValue('')
    expect(screen.getByText('Chat with your MCP tools')).toBeInTheDocument()
    expect(window.localStorage.getItem(CHAT_STORAGE_KEY)).toBeNull()
    expect(window.localStorage.getItem(LEGACY_CHAT_STORAGE_KEY)).toBeNull()

    await user.type(screen.getByLabelText('Message input'), 'start fresh')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('assistant answer')).toBeInTheDocument()
    expect(requestBody().history).toBeNull()
  })

  it('stops an in-flight response, persists it as cancelled, and excludes it from the next call', async () => {
    global.fetch = vi
      .fn()
      .mockImplementationOnce(async (_url, options) => abortableSseResponse(options.signal))
      .mockImplementationOnce(async () => sseResponse({ content: 'fresh answer' }))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    const input = screen.getByLabelText('Message input')

    await user.type(input, 'first question')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('partial answer')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Stop generating response' }))
    expect(await screen.findByText(/\[Cancelled\]/)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
    })

    const cancelled = loadChatConversation().messages.at(-1)
    expect(cancelled).toMatchObject({ role: 'assistant', cancelled: true, streaming: false })

    await user.type(input, 'second question')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('fresh answer')).toBeInTheDocument()

    expect(chatRequests()).toHaveLength(2)
    expect(requestBody(1).history).toEqual([
      { role: 'user', content: 'first question' },
    ])
  })

  it('clears an in-flight response without allowing abort callbacks to restore it', async () => {
    global.fetch = vi.fn(async (_url, options) => abortableSseResponse(options.signal))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Message input'), 'discard this turn')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('partial answer')).toBeInTheDocument()

    const requestSignal = chatRequests()[0][1].signal
    await user.click(screen.getByRole('button', { name: 'Clear saved conversation' }))
    const dialog = screen.getByRole('dialog', { name: 'Clear conversation' })
    await user.click(within(dialog).getByRole('button', { name: 'Clear' }))

    expect(requestSignal.aborted).toBe(true)
    expect(screen.getByText('Chat with your MCP tools')).toBeInTheDocument()
    expect(screen.queryByText(/\[Cancelled\]/)).not.toBeInTheDocument()
    await waitFor(() => {
      expect(window.localStorage.getItem(CHAT_STORAGE_KEY)).toBeNull()
    })
  })

  it('honors a real cross-tab clear event during streaming without resurrecting context', async () => {
    global.fetch = vi
      .fn()
      .mockImplementationOnce(async (_url, options) => abortableSseResponse(options.signal))
      .mockImplementationOnce(async () => sseResponse({ content: 'fresh cross-tab answer' }))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    const input = screen.getByLabelText('Message input')
    await user.type(input, 'clear this from another tab')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('partial answer')).toBeInTheDocument()

    const requestSignal = chatRequests()[0][1].signal
    const crossTabClearToken = 'clear-from-another-tab'
    window.localStorage.setItem(CHAT_CLEAR_TOKEN_KEY, crossTabClearToken)
    window.localStorage.removeItem(CHAT_STORAGE_KEY)

    // Force a synchronous stale flush before the storage event arrives. It is
    // expected synchronization and must not be presented as a save failure.
    fireEvent(window, new Event('pagehide'))
    expect(screen.queryByText(
      'This browser could not save the conversation. Keep this tab open to avoid losing context.',
    )).not.toBeInTheDocument()

    fireEvent(window, new StorageEvent('storage', {
      key: CHAT_CLEAR_TOKEN_KEY,
      oldValue: null,
      newValue: crossTabClearToken,
      url: window.location.href,
    }))

    expect(requestSignal.aborted).toBe(true)
    expect(screen.getByText('Chat with your MCP tools')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('partial answer')).not.toBeInTheDocument()
      expect(screen.queryByText(/\[Cancelled\]/)).not.toBeInTheDocument()
      expect(loadChatConversation()).toMatchObject({
        messages: [],
        systemPrompt: '',
        clearToken: crossTabClearToken,
      })
    })

    await user.type(input, 'start after the other tab cleared')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('fresh cross-tab answer')).toBeInTheDocument()
    expect(requestBody(1).history).toBeNull()
  })

  it('marks a stream without a complete event as interrupted and filters it from follow-up history', async () => {
    global.fetch = vi
      .fn()
      .mockImplementationOnce(async () => sseResponse({
        events: [{ type: 'token', data: 'unfinished answer' }],
      }))
      .mockImplementationOnce(async () => sseResponse({ content: 'recovered answer' }))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    const input = screen.getByLabelText('Message input')

    await user.type(input, 'question before interruption')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText(/\[Response interrupted\]/)).toBeInTheDocument()

    await user.type(input, 'retry after interruption')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('recovered answer')).toBeInTheDocument()
    expect(requestBody(1).history).toEqual([
      { role: 'user', content: 'question before interruption' },
    ])
  })

  it('filters an SSE error response from follow-up history', async () => {
    global.fetch = vi
      .fn()
      .mockImplementationOnce(async () => sseResponse({
        events: [{ type: 'error', data: 'provider unavailable' }],
      }))
      .mockImplementationOnce(async () => sseResponse({ content: 'provider recovered' }))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    const input = screen.getByLabelText('Message input')

    await user.type(input, 'question before error')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('Error: provider unavailable')).toBeInTheDocument()

    await user.type(input, 'retry after error')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('provider recovered')).toBeInTheDocument()
    expect(requestBody(1).history).toEqual([
      { role: 'user', content: 'question before error' },
    ])
  })

  it('discloses when older saved context does not fit the selected model', async () => {
    global.fetch = vi.fn(async () => sseResponse({
      events: [
        {
          type: 'context_trimmed',
          data: {
            omitted_messages: 3,
            original_messages: 20,
            sent_messages: 17,
            context_window: 128000,
            model: 'gpt-b',
          },
        },
        { type: 'token', data: 'answer with recent context' },
        {
          type: 'complete',
          data: {
            token_usage: null,
            cost: 0,
            duration: 0.01,
            model: 'gpt-b',
            provider: 'openai',
            total_turns: 1,
          },
        },
      ],
    }))

    renderChat({ selectedLlmProfile: 'profile-b' })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Message input'), 'continue long chat')
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('answer with recent context')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(
      "3 older context messages were omitted to fit this model's context window. The full conversation remains saved in this browser.",
    )
    await waitFor(() => {
      expect(loadChatConversation().messages.at(-1).context_trimmed).toMatchObject({
        omitted_messages: 3,
        sent_messages: 17,
      })
    })
  })

  it('sends exactly once for Enter with modifier keys', async () => {
    renderChat({ selectedLlmProfile: 'profile-b' })
    const input = screen.getByLabelText('Message input')
    fireEvent.change(input, { target: { value: 'one request only' } })
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', ctrlKey: true })

    expect(await screen.findByText('assistant answer')).toBeInTheDocument()
    expect(chatRequests()).toHaveLength(1)
    expect(requestBody().message).toBe('one request only')
  })
})

describe('turnStartStatus (turn progress label)', () => {
  it('shows a denominator when the backend caps turns (manual loop)', () => {
    // Non-SDK manual loop sends max_turns: 10.
    expect(turnStartStatus({ turn: 3, max_turns: 10 })).toBe('Turn 3/10 — Thinking...')
  })

  it('shows a bare "Turn n" when no cap is sent (SDK path)', () => {
    // SDK-backed runs omit max_turns → no denominator (the PR #118 fix).
    expect(turnStartStatus({ turn: 12 })).toBe('Turn 12 — Thinking...')
    expect(turnStartStatus({ turn: 12, max_turns: undefined })).toBe('Turn 12 — Thinking...')
  })
})
