import React, { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react'

const TestRunContext = createContext(null)

// Storage keys
const STORAGE_KEY = 'testmcpy_active_run'

// Display-cache TTL. The decision to reattach is server-authoritative
// (GET /api/runs on mount), so the snapshot only needs to be fresh enough
// to be worth rendering — not fresh enough to prove the run is alive.
const SNAPSHOT_TTL_MS = 24 * 60 * 60 * 1000

// Reconnect backoff: 1s, 2s, 4s, 8s, 16s — then give up and surface a
// manual Reattach affordance. The server keeps the run alive regardless.
const MAX_RECONNECT_ATTEMPTS = 5

export function TestRunProvider({ children }) {
  const [running, setRunning] = useState(false)
  const [runningTestName, setRunningTestName] = useState(null)
  const [testResults, setTestResults] = useState(null)
  const [streamingLogs, setStreamingLogs] = useState([])
  const [runningTests, setRunningTests] = useState({
    current: null,
    total: 0,
    completed: 0,
    status: 'idle'
  })
  const [testStatuses, setTestStatuses] = useState({})
  const [activeTestFile, setActiveTestFile] = useState(null)
  // Server-side run id of the in-flight run. Persisted so a browser
  // reload can reattach to the same run instead of orphaning it.
  // SC-108184.
  const [currentRunId, setCurrentRunId] = useState(null)
  // Transient state between the user clicking Stop and the server's
  // terminal `all_complete{status:"stopped"}` event landing. Lets the UI
  // show "Stopping…" + a disabled-but-visible button rather than flipping
  // straight to a stale "stopped" state. SC-108217.
  const [stopping, setStopping] = useState(false)
  // Per-file progress strip for directory batches. Set by the
  // `file_start` / `file_complete` events the server emits inside a
  // run_directory task. null when no batch is running.
  const [directoryRunProgress, setDirectoryRunProgress] = useState(null)
  // Combo progress strip for a benchmark run (model × provider × profile ×
  // repeat matrix). Set by the `combo_start` / `combo_complete` events the
  // server emits inside a run_benchmark task. null when no benchmark runs.
  const [benchmarkProgress, setBenchmarkProgress] = useState(null)
  // A historical run pinned into the Results tab. When non-null, the Results
  // tab renders this instead of the live `testResults`. Cleared automatically
  // at the start of any new run so live runs reclaim the tab.
  const [pinnedHistoryRun, setPinnedHistoryRun] = useState(null)
  // Health of the WebSocket pipe to the server-side run, independent of
  // the run itself (which survives disconnects server-side):
  // idle | live | reconnecting | disconnected.
  const [connectionState, setConnectionState] = useState('idle')
  const wsRef = useRef(null)
  // Reattach is wired up below but defined here so the mount effect can
  // refer to it via a ref (the ref is necessary because useCallback for
  // attachToRun needs `running` in its deps, and we don't want a stale
  // closure at mount time).
  const attachRef = useRef(null)
  // Mirrors currentRunId for use inside socket close handlers (state
  // would be stale in those closures).
  const runIdRef = useRef(null)
  // True once the run reached a terminal event (all_complete / error /
  // superseded) — an onclose after that is expected, not a connection
  // loss, so it must not trigger the reconnect loop.
  const terminalRef = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimerRef = useRef(null)

  // Load persisted state on mount. The snapshot is a DISPLAY cache only —
  // whether to reattach is decided by asking the server which runs are
  // actually alive, not by guessing from the snapshot's age (the old
  // 5-minute TTL silently orphaned runs the server was happily keeping
  // alive for 30+ minutes).
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (!saved) return
      const data = JSON.parse(saved)
      const savedTime = new Date(data.timestamp).getTime()
      if (Date.now() - savedTime > SNAPSHOT_TTL_MS) {
        localStorage.removeItem(STORAGE_KEY)
        return
      }
      setStreamingLogs(data.logs || [])
      setTestResults(data.results || null)
      setTestStatuses(data.statuses || {})
      setRunningTests(data.runningTests || { current: null, total: 0, completed: 0, status: 'idle' })
      setActiveTestFile(data.testFile || null)
      setCurrentRunId(data.currentRunId || null)
      setDirectoryRunProgress(data.directoryRunProgress || null)
      runIdRef.current = data.currentRunId || null

      if (!data.currentRunId || !data.running) return
      // Server-authoritative resume: attach only if the server still has
      // the run. If it doesn't (finished, GC'd, or the server restarted),
      // attach anyway — the server's history fallback replays the final
      // record (including `interrupted` + partial results for crashed
      // runs), which settles the UI instead of leaving a zombie spinner.
      queueMicrotask(async () => {
        let live = false
        try {
          const res = await fetch('/api/runs?active_only=true')
          if (res.ok) {
            const activeRuns = (await res.json()).runs || []
            live = activeRuns.some(r => r.run_id === data.currentRunId)
          }
        } catch (e) {
          console.warn('Could not query active runs for resume:', e)
        }
        if (live) {
          // Re-mark running so the spinner / Stop button reappear
          // immediately; the attach completes asynchronously.
          setRunning(true)
        }
        // Use the ref so we get the current attachToRun closure;
        // calling it inline at mount time would resolve to the
        // closure captured when the ref was empty.
        if (attachRef.current) attachRef.current(data.currentRunId)
      })
    } catch (e) {
      console.error('Failed to restore test run state:', e)
    }
  }, [])

  // Persist state changes
  const persistState = useCallback(() => {
    try {
      const data = {
        timestamp: new Date().toISOString(),
        logs: streamingLogs,
        results: testResults,
        statuses: testStatuses,
        runningTests,
        testFile: activeTestFile,
        running,
        currentRunId,
        directoryRunProgress,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.error('Failed to persist test run state:', e)
    }
  }, [
    streamingLogs,
    testResults,
    testStatuses,
    runningTests,
    activeTestFile,
    running,
    currentRunId,
    directoryRunProgress,
  ])

  // Persist on state changes
  useEffect(() => {
    persistState()
  }, [
    streamingLogs,
    testResults,
    testStatuses,
    runningTests,
    currentRunId,
    directoryRunProgress,
    persistState,
  ])

  // Shared SSE-style server-message handler used by all WS flows
  // (single-file run, single-test run, directory batch, reattach).
  //
  // Centralising the switch makes it cheap to add a new event type
  // server-side; pre-SC-108184 the switch was duplicated three times.
  // Each caller can pass options to tune behaviour for their flow:
  // - closeOnComplete: close the WS once `all_complete` arrives.
  //   All current callers (runTests, runSingleTest, runDirectory,
  //   attachToRun) pass true — the option is retained so a future
  //   caller can keep the socket open across multiple sequential
  //   runs without re-handshaking.
  const _handleServerMessage = useCallback((ws, data, options = {}) => {
    const { closeOnComplete = true } = options
    switch (data.type) {
      case 'run_started': {
        setCurrentRunId(data.run_id)
        runIdRef.current = data.run_id
        // Any successful (re)attach resets the backoff clock.
        reconnectAttemptsRef.current = 0
        setConnectionState('live')
        if (data.reattached) {
          setStreamingLogs(prev => [
            ...prev,
            data.source === 'history'
              ? `📜 Run ${data.run_id} already finished (${data.status}) — showing saved results`
              : `🔁 Reattached to run ${data.run_id} (server-side status: ${data.status})`,
          ])
        }
        break
      }
      case 'log':
      case 'log_replay': {
        setStreamingLogs(prev => [...prev, data.message])
        break
      }
      case 'test_start': {
        setRunningTests(prev => ({
          ...prev,
          current: data.test_name,
          completed: data.index ?? prev.completed,
          total: data.total ?? prev.total,
        }))
        setTestStatuses(prev => ({ ...prev, [data.test_name]: 'running' }))
        break
      }
      case 'test_complete': {
        const result = data.result
        setTestStatuses(prev => ({
          ...prev,
          [data.test_name]: result.passed ? 'passed' : 'failed',
        }))
        setTestResults(prev => {
          const prevResults = prev?.results || []
          // Replace any prior result with the same test_name (the
          // single-test rerun path uses this; for fresh runs it's a no-op).
          const existing = prevResults.filter(r => r.test_name !== data.test_name)
          const newResults = [...existing, result]
          return {
            summary: {
              total: newResults.length,
              passed: newResults.filter(r => r.passed).length,
              failed: newResults.filter(r => !r.passed).length,
              total_cost: newResults.reduce((sum, r) => sum + (r.cost || 0), 0),
              total_tokens: newResults.reduce(
                (sum, r) => sum + (r.token_usage?.total || 0),
                0,
              ),
            },
            results: newResults,
          }
        })
        break
      }
      case 'file_start': {
        setDirectoryRunProgress(prev => ({
          folder: prev?.folder ?? '',
          current: (data.index ?? 0) + 1,
          total: data.total ?? 0,
          name: data.name,
          test_path: data.test_path,
          // Preserve any partial summary built up so far.
          results: prev?.results ?? [],
        }))
        setStreamingLogs(prev => [...prev, `📂 File ${(data.index ?? 0) + 1}/${data.total}: ${data.name}`])
        break
      }
      case 'file_complete': {
        setDirectoryRunProgress(prev =>
          prev
            ? {
                ...prev,
                results: [...(prev.results || []), {
                  file: data.name,
                  test_path: data.test_path,
                  summary: data.summary,
                }],
              }
            : prev,
        )
        break
      }
      case 'file_error': {
        // Non-terminal per-file error inside a directory batch (SC-108217).
        // The batch keeps streaming; we just annotate the log + mark the
        // file as failed in the progress strip. Don't touch `running` /
        // `running tests.status` — files 2..N are still coming.
        setStreamingLogs(prev => [
          ...prev,
          `❌ File error: ${data.message}`,
          ...(data.traceback ? [data.traceback] : []),
        ])
        setDirectoryRunProgress(prev =>
          prev
            ? {
                ...prev,
                results: [
                  ...(prev.results || []),
                  {
                    file: prev.name,
                    test_path: data.test_path || prev.test_path,
                    summary: { total: 0, passed: 0, failed: 0 },
                    error: data.message,
                  },
                ],
              }
            : prev,
        )
        break
      }
      case 'combo_start': {
        // One cell of a benchmark matrix is starting (model × provider ×
        // profile × repeat). Drives the benchmark progress strip.
        setBenchmarkProgress(prev => ({
          ...(prev || { results: [] }),
          current: (data.index ?? 0) + 1,
          total: data.total,
          label: data.label,
          iteration: data.iteration,
        }))
        break
      }
      case 'combo_complete': {
        setBenchmarkProgress(prev =>
          prev
            ? {
                ...prev,
                results: [
                  ...(prev.results || []),
                  { label: data.label, summary: data.summary },
                ],
              }
            : prev,
        )
        break
      }
      case 'stopping': {
        // Server acked our stop request — show transient "Stopping…"
        // until `all_complete{status:"stopped"}` arrives.
        setStopping(true)
        setStreamingLogs(prev => [...prev, '🛑 Server is cancelling the run…'])
        break
      }
      case 'all_complete': {
        if (data.summary && data.results) {
          setTestResults({ summary: data.summary, results: data.results })
        }
        // Pin BOTH `completed` and `total` from the summary. For
        // single-file runs they were already aligned (the per-test
        // test_start events updated `total`), but for directory
        // batches `total` was initialised to files.length and then
        // overwritten per-file by test_start events, leaving
        // `completed` (= total tests across files) > `total` after
        // the batch finishes (Copilot review on PR #76).
        const wasStopped = data.status === 'stopped'
        const wasInterrupted = data.status === 'interrupted'
        setRunningTests(prev => ({
          ...prev,
          current: null,
          completed: data.summary?.total ?? prev.completed,
          total: data.summary?.total ?? prev.total,
          status: wasStopped ? 'stopped' : wasInterrupted ? 'error' : 'completed',
        }))
        terminalRef.current = true
        setConnectionState('idle')
        setRunning(false)
        setStopping(false)
        setDirectoryRunProgress(null)
        setStreamingLogs(prev => [
          ...prev,
          wasStopped
            ? '🛑 Run stopped'
            : wasInterrupted
              ? '⚠️ Run was interrupted (server restarted mid-run) — partial results below'
              : '✅ All tests complete!',
        ])
        if (closeOnComplete) {
          try { ws.close() } catch (e) { /* noop */ }
        }
        break
      }
      case 'superseded': {
        // Another browser tab attached to the same run; this WS will
        // stop receiving live updates. Surface that so the user knows
        // why the log stream froze. Terminal for THIS view — don't try
        // to reconnect and steal the run back.
        terminalRef.current = true
        setConnectionState('idle')
        setStreamingLogs(prev => [
          ...prev,
          `🔀 Another client attached to this run (token ${data.by_token}); this view is no longer live.`,
        ])
        setRunning(false)
        try { ws.close() } catch (e) { /* noop */ }
        break
      }
      case 'error': {
        terminalRef.current = true
        setConnectionState('idle')
        setStreamingLogs(prev => [...prev, `❌ ERROR: ${data.message}`])
        if (data.traceback) {
          setStreamingLogs(prev => [...prev, data.traceback])
        }
        setRunning(false)
        setRunningTests(prev => ({ ...prev, status: 'error' }))
        if (closeOnComplete) {
          try { ws.close() } catch (e) { /* noop */ }
        }
        break
      }
      default:
        // Unknown type — silently drop. Forward-compatible.
        break
    }
  }, [])

  // Schedule a reattach with exponential backoff. Returns true when a
  // reconnect (or the give-up banner) was arranged, false when there's
  // nothing to reattach to (no run_id) and the caller should fall back
  // to plain error handling.
  const scheduleReconnect = useCallback(() => {
    const runId = runIdRef.current
    if (!runId || terminalRef.current) return false
    const attempt = reconnectAttemptsRef.current
    if (attempt >= MAX_RECONNECT_ATTEMPTS) {
      setConnectionState('disconnected')
      setStreamingLogs(prev => [
        ...prev,
        '🔌 Disconnected — the run is still going on the server. Use Reattach to resume watching.',
      ])
      return true
    }
    const delayMs = 1000 * Math.pow(2, attempt)
    reconnectAttemptsRef.current = attempt + 1
    setConnectionState('reconnecting')
    setStreamingLogs(prev => [
      ...prev,
      `🔁 Connection lost — reconnecting in ${delayMs / 1000}s (attempt ${attempt + 1}/${MAX_RECONNECT_ATTEMPTS})…`,
    ])
    reconnectTimerRef.current = setTimeout(() => {
      if (attachRef.current) attachRef.current(runId)
    }, delayMs)
    return true
  }, [])

  // Shared onclose for every run/attach socket. A close after a terminal
  // event is normal teardown; a close mid-run means the PIPE died, not
  // the run — the server deliberately keeps the task alive — so we
  // reconnect instead of declaring the run failed (the old behaviour
  // flipped running=false and showed "Connection lost" while the server
  // kept burning tokens invisibly).
  const handleSocketClose = useCallback((ws) => {
    if (wsRef.current !== ws) return
    wsRef.current = null
    if (terminalRef.current) {
      setConnectionState('idle')
      return
    }
    if (scheduleReconnect()) return
    // No run_id yet (socket died during the handshake) — original
    // hard-error behaviour.
    setRunning(currentRunning => {
      if (currentRunning) {
        setStreamingLogs(prev => [...prev, '⚠️ Connection lost while test was running'])
        setRunningTests(prev => ({ ...prev, status: 'error', current: null }))
        return false
      }
      return currentRunning
    })
    setConnectionState('idle')
  }, [scheduleReconnect])

  // Cancel any pending reconnect timer (new run / explicit reattach
  // supersedes the scheduled one).
  const cancelPendingReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  // Run all tests for a file
  const runTests = useCallback(async (testFile, testPath, llmConfig, mcpProfile, testLocations = [], llmProfile = null) => {
    if (running) return

    cancelPendingReconnect()
    terminalRef.current = false
    reconnectAttemptsRef.current = 0
    runIdRef.current = null
    setRunning(true)
    setActiveTestFile(testFile)
    setTestResults(null)
    setPinnedHistoryRun(null)
    setStreamingLogs(['🚀 Starting test run...'])

    const tests = testLocations.length > 0 ? testLocations : [{ name: 'test' }]
    const totalTests = tests.length

    setRunningTests({
      current: 'Connecting...',
      total: totalTests,
      completed: 0,
      status: 'running'
    })

    // Reset all test statuses
    const initialStatuses = {}
    tests.forEach(t => initialStatuses[t.name] = 'idle')
    setTestStatuses(initialStatuses)

    // Create WebSocket connection
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStreamingLogs(prev => [...prev, '🔌 Connected to test runner'])
        ws.send(JSON.stringify({
          type: 'run_test',
          test_path: testPath,
          model: llmConfig.model,
          provider: llmConfig.provider,
          profile: mcpProfile,
          llm_profile: llmProfile,
        }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        _handleServerMessage(ws, data, { closeOnComplete: true })
      }

      ws.onerror = (error) => {
        // onerror is always followed by onclose — reconnect/error
        // handling lives there.
        console.error('WebSocket error:', error)
      }

      ws.onclose = () => handleSocketClose(ws)

    } catch (error) {
      console.error('Failed to run tests:', error)
      setStreamingLogs(prev => [...prev, `❌ Failed: ${error.message}`])
      setRunning(false)
      setRunningTests({
        current: null,
        total: 0,
        completed: 0,
        status: 'idle'
      })
    }
  }, [running, cancelPendingReconnect, handleSocketClose, _handleServerMessage])

  // Run a single test
  const runSingleTest = useCallback(async (testName, testFile, testPath, llmConfig, mcpProfile, llmProfile = null) => {
    if (running) return

    cancelPendingReconnect()
    terminalRef.current = false
    reconnectAttemptsRef.current = 0
    runIdRef.current = null
    setRunning(true)
    setRunningTestName(testName)
    setActiveTestFile(testFile)
    setPinnedHistoryRun(null)
    setTestStatuses(prev => ({ ...prev, [testName]: 'running' }))
    setStreamingLogs([`🚀 Running test: ${testName}`])

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStreamingLogs(prev => [...prev, '🔌 Connected to test runner'])
        ws.send(JSON.stringify({
          type: 'run_test',
          test_path: testPath,
          test_name: testName,
          model: llmConfig.model,
          provider: llmConfig.provider,
          profile: mcpProfile,
          llm_profile: llmProfile,
        }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        _handleServerMessage(ws, data, { closeOnComplete: true })
        // Single-test path also clears the per-test cursor when its
        // dedicated test finishes (the shared handler doesn't know
        // about single-test mode).
        if (data.type === 'all_complete' || data.type === 'error') {
          setRunningTestName(null)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onclose = () => handleSocketClose(ws)

    } catch (error) {
      console.error('Failed to run test:', error)
      setStreamingLogs(prev => [...prev, `❌ Failed: ${error.message}`])
      setTestStatuses(prev => ({ ...prev, [testName]: 'failed' }))
      setRunning(false)
      setRunningTestName(null)
    }
  }, [running, cancelPendingReconnect, handleSocketClose, _handleServerMessage])

  // Run an entire directory batch under one server-side run_id.
  // Pre-SC-108184 this was a sequential HTTP POST loop with no log
  // streaming — the Logs tab never opened for batch runs.
  const runDirectory = useCallback(async (
    folderName,
    files,
    llmConfig,
    mcpProfile,
    llmProfile = null,
  ) => {
    if (running) return

    cancelPendingReconnect()
    terminalRef.current = false
    reconnectAttemptsRef.current = 0
    runIdRef.current = null
    setRunning(true)
    setActiveTestFile(folderName)
    setTestResults(null)
    setPinnedHistoryRun(null)
    setStreamingLogs([`🚀 Starting directory run: ${folderName} (${files.length} file(s))`])
    setRunningTests({
      current: 'Connecting...',
      total: files.length,
      completed: 0,
      status: 'running',
    })
    setDirectoryRunProgress({
      folder: folderName,
      current: 0,
      total: files.length,
      results: [],
    })

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStreamingLogs(prev => [...prev, '🔌 Connected to test runner'])
        ws.send(JSON.stringify({
          type: 'run_directory',
          folder: folderName,
          files: files.map(f => ({
            test_path: f.path || f.test_path,
            name: f.filename || f.name,
          })),
          model: llmConfig.model,
          provider: llmConfig.provider,
          profile: mcpProfile,
          llm_profile: llmProfile,
        }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        _handleServerMessage(ws, data, { closeOnComplete: true })
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onclose = () => handleSocketClose(ws)
    } catch (error) {
      console.error('Failed to start directory run:', error)
      setStreamingLogs(prev => [...prev, `❌ Failed: ${error.message}`])
      setRunning(false)
      setRunningTests({ current: null, total: 0, completed: 0, status: 'idle' })
      setDirectoryRunProgress(null)
    }
  }, [running, cancelPendingReconnect, handleSocketClose, _handleServerMessage])

  // Run a benchmark: the model × provider × profile × repeat matrix over a
  // file/directory, streamed live. `payload` carries { files, models,
  // providers, profiles, repeat } plus ad-hoc connection/auth fields
  // (mcp_url, auth_type, jwt_*, workspace_hash, domain, assistant_* ) — no
  // saved profile required. Reuses the same per-test event stream as a run.
  const runBenchmark = useCallback(async (payload) => {
    if (running) return

    const label = payload.label || 'benchmark'
    cancelPendingReconnect()
    terminalRef.current = false
    reconnectAttemptsRef.current = 0
    runIdRef.current = null
    setRunning(true)
    setActiveTestFile(label)
    setTestResults(null)
    setPinnedHistoryRun(null)
    setDirectoryRunProgress(null)
    setBenchmarkProgress({ current: 0, total: 0, label: null, results: [] })
    setStreamingLogs([`🏁 Starting benchmark: ${label}`])
    setRunningTests({ current: 'Connecting...', total: 0, completed: 0, status: 'running' })

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStreamingLogs(prev => [...prev, '🔌 Connected to test runner'])
        ws.send(JSON.stringify({ type: 'run_benchmark', ...payload }))
      }
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        _handleServerMessage(ws, data, { closeOnComplete: true })
      }
      ws.onerror = (error) => console.error('WebSocket error:', error)
      ws.onclose = () => handleSocketClose(ws)
    } catch (error) {
      console.error('Failed to start benchmark:', error)
      setStreamingLogs(prev => [...prev, `❌ Failed: ${error.message}`])
      setRunning(false)
      setRunningTests({ current: null, total: 0, completed: 0, status: 'idle' })
      setBenchmarkProgress(null)
    }
  }, [running, cancelPendingReconnect, handleSocketClose, _handleServerMessage])

  // Reattach to a server-side run by id. The server replays buffered
  // logs as `log_replay` events, then streams live updates until the
  // run finishes or another client supersedes us.
  const attachToRun = useCallback(async (runId) => {
    if (!runId) return
    cancelPendingReconnect()
    terminalRef.current = false
    runIdRef.current = runId
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        // The server replays its full buffered backlog on attach — clear
        // the local log so the replay doesn't duplicate every line we
        // already had from localStorage / the dropped socket.
        setStreamingLogs([])
        ws.send(JSON.stringify({ type: 'attach', run_id: runId }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        _handleServerMessage(ws, data, { closeOnComplete: true })
      }

      ws.onerror = (error) => {
        // onclose follows and owns the reconnect/backoff decision.
        console.error('Reattach WebSocket error:', error)
      }

      ws.onclose = () => handleSocketClose(ws)
    } catch (error) {
      console.error('Failed to reattach:', error)
      setStreamingLogs(prev => [...prev, `⚠️ Could not reattach: ${error.message}`])
      setRunning(false)
      setConnectionState('disconnected')
    }
  }, [_handleServerMessage, cancelPendingReconnect, handleSocketClose])

  // Expose attachToRun via a ref so the mount-time restoration effect
  // can call the current closure even though it ran before the
  // useCallback was registered.
  useEffect(() => {
    attachRef.current = attachToRun
  }, [attachToRun])

  // Stop a running test.
  //
  // Pre-SC-108217 this sent `{type: "stop"}` AND immediately closed the
  // WebSocket. The server's stop handler called `handle.task.cancel()`
  // but the close raced with the cancellation — and worse, even when
  // cancellation worked the client was already gone, so the user never
  // saw the post-cancel log lines or the terminal event. They had no
  // proof the run actually stopped.
  //
  // New flow: send `stop`, set `stopping=true` so the UI shows
  // "Stopping…", DO NOT close the WS. The server emits a `stopping`
  // ack immediately and a terminal `all_complete{status:"stopped"}`
  // once the cancellation finalises. That terminal event closes the
  // WS via the shared handler. If the WS is gone (rare — happens only
  // if the network failed), fall back to a fire-and-forget POST to
  // `/api/runs/{run_id}/stop` so a reload-or-navigate user can still
  // kill a run they can't see.
  const stopTests = useCallback(() => {
    const ws = wsRef.current
    setStopping(true)
    setStreamingLogs(prev => [...prev, '🛑 Stop requested — waiting for server…'])
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'stop' }))
      } catch (e) {
        // Send failed — fall through to the REST fallback below.
      }
      return
    }
    // No live WS — try the REST cancel endpoint.
    if (currentRunId) {
      fetch(`/api/runs/${encodeURIComponent(currentRunId)}/stop`, { method: 'POST' })
        .catch(err => {
          setStreamingLogs(prev => [
            ...prev,
            `⚠️ Could not reach /api/runs to stop: ${err.message || err}`,
          ])
        })
    } else {
      // Nothing we can stop — clear the local state anyway so the user
      // isn't stuck with a stale "running" UI.
      setStopping(false)
      setRunning(false)
      setRunningTestName(null)
      setRunningTests(prev => ({ ...prev, current: null, status: 'stopped' }))
    }
  }, [currentRunId])

  // Clear logs
  const clearLogs = useCallback(() => {
    setStreamingLogs([])
  }, [])

  // Clear results
  const clearResults = useCallback(() => {
    cancelPendingReconnect()
    runIdRef.current = null
    setTestResults(null)
    setTestStatuses({})
    setStreamingLogs([])
    setRunningTests({ current: null, total: 0, completed: 0, status: 'idle' })
    setCurrentRunId(null)
    setDirectoryRunProgress(null)
    setConnectionState('idle')
    localStorage.removeItem(STORAGE_KEY)
  }, [cancelPendingReconnect])

  // Drop any pending reconnect timer on unmount.
  useEffect(() => cancelPendingReconnect, [cancelPendingReconnect])

  // Reset test statuses (for when file content changes)
  const resetTestStatuses = useCallback((testNames) => {
    const initialStatuses = {}
    testNames.forEach(name => initialStatuses[name] = 'idle')
    setTestStatuses(initialStatuses)
  }, [])

  const value = {
    // State
    running,
    runningTestName,
    testResults,
    streamingLogs,
    runningTests,
    testStatuses,
    activeTestFile,
    pinnedHistoryRun,
    currentRunId,
    directoryRunProgress,
    benchmarkProgress,
    stopping,
    connectionState,
    // Actions
    runTests,
    runSingleTest,
    runDirectory,
    runBenchmark,
    attachToRun,
    stopTests,
    clearLogs,
    clearResults,
    resetTestStatuses,
    setTestStatuses,
    setTestResults,
    setPinnedHistoryRun,
    setDirectoryRunProgress,
    // For "Run All LLMs" mode which manages its own state
    setRunning,
    setRunningTests,
  }

  return (
    <TestRunContext.Provider value={value}>
      {children}
    </TestRunContext.Provider>
  )
}

export function useTestRun() {
  const context = useContext(TestRunContext)
  if (!context) {
    throw new Error('useTestRun must be used within a TestRunProvider')
  }
  return context
}

export default TestRunContext
