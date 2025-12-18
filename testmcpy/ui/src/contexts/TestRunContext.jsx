import React, { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react'

const TestRunContext = createContext(null)

// Storage keys
const STORAGE_KEY = 'testmcpy_active_run'

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
  const wsRef = useRef(null)

  // Load persisted state on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const data = JSON.parse(saved)
        // Only restore if it's recent (within last 5 minutes)
        const savedTime = new Date(data.timestamp).getTime()
        const now = Date.now()
        if (now - savedTime < 5 * 60 * 1000) {
          setStreamingLogs(data.logs || [])
          setTestResults(data.results || null)
          setTestStatuses(data.statuses || {})
          setRunningTests(data.runningTests || { current: null, total: 0, completed: 0, status: 'idle' })
          setActiveTestFile(data.testFile || null)
          // Don't restore 'running' state since WS is disconnected
          if (data.running && data.runningTests?.status === 'running') {
            // Add a message that the run was interrupted
            setStreamingLogs(prev => [...prev, '⚠️ Previous run was interrupted by page reload'])
          }
        } else {
          // Clear old data
          localStorage.removeItem(STORAGE_KEY)
        }
      }
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
        running
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.error('Failed to persist test run state:', e)
    }
  }, [streamingLogs, testResults, testStatuses, runningTests, activeTestFile, running])

  // Persist on state changes
  useEffect(() => {
    persistState()
  }, [streamingLogs, testResults, testStatuses, runningTests, persistState])

  // Run all tests for a file
  const runTests = useCallback(async (testFile, testPath, llmConfig, mcpProfile, testLocations = []) => {
    if (running) return

    setRunning(true)
    setActiveTestFile(testFile)
    setTestResults(null)
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
        }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        switch (data.type) {
          case 'log':
            setStreamingLogs(prev => [...prev, data.message])
            break

          case 'test_start':
            setRunningTests(prev => ({
              ...prev,
              current: data.test_name,
              completed: data.index,
              total: data.total,
            }))
            setTestStatuses(prev => ({ ...prev, [data.test_name]: 'running' }))
            break

          case 'test_complete':
            const result = data.result
            setTestStatuses(prev => ({
              ...prev,
              [data.test_name]: result.passed ? 'passed' : 'failed'
            }))
            setTestResults(prev => {
              const prevResults = prev?.results || []
              const newResults = [...prevResults, result]
              return {
                summary: {
                  total: newResults.length,
                  passed: newResults.filter(r => r.passed).length,
                  failed: newResults.filter(r => !r.passed).length,
                  total_cost: newResults.reduce((sum, r) => sum + (r.cost || 0), 0),
                  total_tokens: newResults.reduce((sum, r) => sum + (r.token_usage?.total || 0), 0),
                },
                results: newResults
              }
            })
            break

          case 'all_complete':
            setTestResults({
              summary: data.summary,
              results: data.results
            })
            setRunningTests(prev => ({
              ...prev,
              current: null,
              completed: data.summary.total,
              status: 'completed'
            }))
            setRunning(false)
            setStreamingLogs(prev => [...prev, '✅ All tests complete!'])
            ws.close()
            break

          case 'error':
            setStreamingLogs(prev => [...prev, `❌ ERROR: ${data.message}`])
            if (data.traceback) {
              setStreamingLogs(prev => [...prev, data.traceback])
            }
            setRunning(false)
            setRunningTests(prev => ({ ...prev, status: 'error' }))
            ws.close()
            break
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setStreamingLogs(prev => [...prev, `❌ WebSocket error: ${error.message || 'Connection failed'}`])
        setRunning(false)
        setRunningTests(prev => ({ ...prev, status: 'error' }))
      }

      ws.onclose = (event) => {
        // Check if this was an unexpected close (test was still running)
        // Note: We use a closure check here since `running` state may be stale
        if (wsRef.current === ws) {
          // This WebSocket was still the active one
          setRunning(currentRunning => {
            if (currentRunning) {
              // Unexpected disconnect while test was running
              setStreamingLogs(prev => [...prev, '⚠️ Connection lost while test was running'])
              setRunningTests(prev => ({ ...prev, status: 'error', current: null }))
              return false
            }
            return currentRunning
          })
        }
        setStreamingLogs(prev => [...prev, '🔌 Disconnected'])
        wsRef.current = null
      }

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
  }, [running])

  // Run a single test
  const runSingleTest = useCallback(async (testName, testFile, testPath, llmConfig, mcpProfile) => {
    if (running) return

    setRunning(true)
    setRunningTestName(testName)
    setActiveTestFile(testFile)
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
        }))
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        switch (data.type) {
          case 'log':
            setStreamingLogs(prev => [...prev, data.message])
            break
          case 'test_start':
            setStreamingLogs(prev => [...prev, `🧪 Starting: ${data.test_name}`])
            break
          case 'test_complete':
            const result = data.result
            setTestStatuses(prev => ({
              ...prev,
              [testName]: result.passed ? 'passed' : 'failed'
            }))
            setTestResults(prev => {
              if (!prev) return { results: [result], summary: { total: 1, passed: result.passed ? 1 : 0, failed: result.passed ? 0 : 1 } }
              const existingResults = prev.results.filter(r => r.test_name !== testName)
              const newResults = [...existingResults, result]
              return {
                results: newResults,
                summary: {
                  total: newResults.length,
                  passed: newResults.filter(r => r.passed).length,
                  failed: newResults.filter(r => !r.passed).length,
                  total_cost: newResults.reduce((sum, r) => sum + (r.cost || 0), 0)
                }
              }
            })
            break
          case 'all_complete':
            setStreamingLogs(prev => [...prev, `✅ Test complete`])
            setRunning(false)
            setRunningTestName(null)
            ws.close()
            break
          case 'error':
            setStreamingLogs(prev => [...prev, `❌ ERROR: ${data.message}`])
            setTestStatuses(prev => ({ ...prev, [testName]: 'failed' }))
            setRunning(false)
            setRunningTestName(null)
            ws.close()
            break
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setStreamingLogs(prev => [...prev, `❌ WebSocket error`])
        setTestStatuses(prev => ({ ...prev, [testName]: 'failed' }))
        setRunning(false)
        setRunningTestName(null)
      }

      ws.onclose = () => {
        wsRef.current = null
      }

    } catch (error) {
      console.error('Failed to run test:', error)
      setStreamingLogs(prev => [...prev, `❌ Failed: ${error.message}`])
      setTestStatuses(prev => ({ ...prev, [testName]: 'failed' }))
      setRunning(false)
      setRunningTestName(null)
    }
  }, [running])

  // Clear logs
  const clearLogs = useCallback(() => {
    setStreamingLogs([])
  }, [])

  // Clear results
  const clearResults = useCallback(() => {
    setTestResults(null)
    setTestStatuses({})
    setStreamingLogs([])
    setRunningTests({ current: null, total: 0, completed: 0, status: 'idle' })
    localStorage.removeItem(STORAGE_KEY)
  }, [])

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
    // Actions
    runTests,
    runSingleTest,
    clearLogs,
    clearResults,
    resetTestStatuses,
    setTestStatuses,
    setTestResults,
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
