import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Plus,
  Play,
  Trash2,
  Edit,
  Save,
  X,
  FileText,
  CheckCircle,
  XCircle,
  Folder,
  ChevronRight,
  ChevronDown,
  Loader2,
  Terminal,
  History,
  TrendingUp,
  Clock,
  DollarSign,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import TestStatusIndicator from '../components/TestStatusIndicator'
import TestResultPanel from '../components/TestResultPanel'
import { useKeyboardShortcuts, useAnnounce } from '../hooks/useKeyboardShortcuts'
import { useTestRun } from '../contexts/TestRunContext'

// Parse YAML content to find test locations (line numbers)
function parseTestLocations(content) {
  const lines = content.split('\n')
  const tests = []
  let inTestsArray = false
  let testsIndent = 0
  let testItemIndent = null // The indentation level of test items (first "- name:" found)

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Detect start of tests array
    if (trimmed === 'tests:') {
      inTestsArray = true
      testsIndent = line.indexOf('tests:')
      testItemIndent = null // Reset for each tests: block
      continue
    }

    if (inTestsArray) {
      // Check for test item (starts with "- name:")
      const match = line.match(/^(\s*)- name:\s*["']?([^"'\n]+)["']?/)
      if (match) {
        const indent = match[1].length

        // First time we see "- name:", record that indentation as the test level
        if (testItemIndent === null && indent > testsIndent) {
          testItemIndent = indent
        }

        // Only capture names at the test indentation level (not evaluators which are deeper)
        if (indent === testItemIndent) {
          tests.push({
            name: match[2].trim(),
            lineNumber: i + 1, // Monaco uses 1-based line numbers
          })
        }
      }

      // Check if we've left the tests array (another top-level key)
      if (trimmed && !trimmed.startsWith('-') && !trimmed.startsWith('#') && trimmed.includes(':') && !line.startsWith(' ')) {
        inTestsArray = false
      }
    }
  }

  return tests
}

function TestManager({ selectedProfiles = [] }) {
  // Get test run state from context (persists across navigation)
  const {
    running,
    runningTestName,
    testResults,
    streamingLogs,
    runningTests,
    testStatuses,
    activeTestFile,
    runTests: contextRunTests,
    runSingleTest: contextRunSingleTest,
    clearLogs,
    clearResults,
    resetTestStatuses,
    setTestStatuses,
    setTestResults,
    setRunning,
    setRunningTests,
  } = useTestRun()

  // Local UI state (doesn't need to persist)
  const [testData, setTestData] = useState({ folders: {}, files: [] })
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [editMode, setEditMode] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [showNewFileDialog, setShowNewFileDialog] = useState(false)
  const [testLocations, setTestLocations] = useState([])
  const editorRef = useRef(null)
  const monacoRef = useRef(null)
  const testLocationsRef = useRef([]) // Ref to avoid stale closure in click handler
  const logsEndRef = useRef(null)
  const [testProfiles, setTestProfiles] = useState([])
  const [selectedTestProfile, setSelectedTestProfile] = useState(null)
  const [mcpProfiles, setMcpProfiles] = useState([])
  const [selectedMcpProfile, setSelectedMcpProfile] = useState(null)
  const [llmProfiles, setLlmProfiles] = useState([])
  const [selectedLlmProfile, setSelectedLlmProfile] = useState(null)
  const [selectedLlmProvider, setSelectedLlmProvider] = useState(null) // specific provider within profile
  const [runAllLlmsMode, setRunAllLlmsMode] = useState(false)
  const [allLlmsResults, setAllLlmsResults] = useState(null) // results from running all LLMs
  const [resultsHistory, setResultsHistory] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [selectedHistoryRun, setSelectedHistoryRun] = useState(null)
  const [bottomPanelTab, setBottomPanelTab] = useState('logs') // 'logs' or 'results'

  useEffect(() => {
    loadTestFiles()
    loadTestProfiles()
    loadMcpProfiles()
    loadLlmProfiles()
  }, [])

  // Screen reader announcements
  const announce = useAnnounce()

  // Keyboard shortcut handlers
  const handleRunTestsShortcut = useCallback((e) => {
    if (selectedFile && !running) {
      e.preventDefault()
      runTests()
      announce('Running tests')
    }
  }, [selectedFile, running])

  const handleSaveShortcut = useCallback((e) => {
    if (editMode && selectedFile) {
      e.preventDefault()
      saveTestFile()
      announce('File saved')
    }
  }, [editMode, selectedFile])

  const handleEscapeShortcut = useCallback((e) => {
    if (showNewFileDialog) {
      e.preventDefault()
      setShowNewFileDialog(false)
      setNewFileName('')
    } else if (editMode) {
      e.preventDefault()
      setEditMode(false)
      setFileContent(selectedFile?.content || '')
    }
  }, [showNewFileDialog, editMode, selectedFile])

  // Register keyboard shortcuts
  useKeyboardShortcuts({
    'ctrl+shift+t': handleRunTestsShortcut,
    'ctrl+s': handleSaveShortcut,
    'escape': handleEscapeShortcut,
  }, true)

  // Load previously selected test file after test data is loaded
  useEffect(() => {
    if (testData.files || testData.folders) {
      const savedPath = localStorage.getItem('selectedTestFile')
      if (savedPath) {
        loadTestFile(savedPath)
      }
    }
  }, [testData])

  const loadTestProfiles = async () => {
    try {
      const res = await fetch('/api/test/profiles')
      const data = await res.json()
      setTestProfiles(data.profiles || [])

      // Check localStorage for saved test profile
      const savedProfile = localStorage.getItem('selectedTestProfile')
      if (savedProfile) {
        setSelectedTestProfile(savedProfile)
      } else if (data.default) {
        setSelectedTestProfile(data.default)
        localStorage.setItem('selectedTestProfile', data.default)
      }
    } catch (error) {
      console.error('Failed to load test profiles:', error)
    }
  }

  const handleTestProfileChange = (profileId) => {
    setSelectedTestProfile(profileId)
    localStorage.setItem('selectedTestProfile', profileId)
  }

  const loadMcpProfiles = async () => {
    try {
      const res = await fetch('/api/mcp/profiles')
      const data = await res.json()
      setMcpProfiles(data.profiles || [])

      // Check localStorage for saved MCP profile
      const savedProfile = localStorage.getItem('selectedMCPProfileForTests')
      if (savedProfile) {
        setSelectedMcpProfile(savedProfile)
      } else if (data.default_selection) {
        setSelectedMcpProfile(data.default_selection)
        localStorage.setItem('selectedMCPProfileForTests', data.default_selection)
      }
    } catch (error) {
      console.error('Failed to load MCP profiles:', error)
    }
  }

  const loadLlmProfiles = async () => {
    try {
      const res = await fetch('/api/llm/profiles')
      const data = await res.json()
      setLlmProfiles(data.profiles || [])

      // Check localStorage for saved LLM profile and provider
      // First check test-specific settings, then fall back to global settings
      const savedProfile = localStorage.getItem('selectedLLMProfileForTests') || localStorage.getItem('selectedLLMProfile')
      const savedProvider = localStorage.getItem('selectedLLMProviderForTests') || localStorage.getItem('selectedLLMProvider')

      if (savedProfile) {
        setSelectedLlmProfile(savedProfile)
        if (savedProvider) {
          setSelectedLlmProvider(savedProvider)
        } else {
          // Set provider from the profile's default
          const profileData = data.profiles?.find(p => p.profile_id === savedProfile)
          if (profileData?.providers?.length > 0) {
            const defaultProv = profileData.providers.find(p => p.default) || profileData.providers[0]
            const provKey = `${defaultProv.provider}:${defaultProv.model}`
            setSelectedLlmProvider(provKey)
          }
        }
      } else if (data.default) {
        setSelectedLlmProfile(data.default)
        // Set default provider from the profile
        const defaultProfileData = data.profiles?.find(p => p.profile_id === data.default)
        if (defaultProfileData?.providers?.length > 0) {
          const defaultProv = defaultProfileData.providers.find(p => p.default) || defaultProfileData.providers[0]
          const provKey = `${defaultProv.provider}:${defaultProv.model}`
          setSelectedLlmProvider(provKey)
        }
      }
    } catch (error) {
      console.error('Failed to load LLM profiles:', error)
    }
  }

  const handleMcpProfileChange = (profileSelection) => {
    setSelectedMcpProfile(profileSelection)
    localStorage.setItem('selectedMCPProfileForTests', profileSelection)
  }

  const handleLlmProfileChange = (profileId) => {
    setSelectedLlmProfile(profileId)
    localStorage.setItem('selectedLLMProfileForTests', profileId)
    // Reset provider selection when profile changes
    const profile = llmProfiles.find(p => p.profile_id === profileId)
    if (profile?.providers?.length > 0) {
      const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
      const provKey = `${defaultProv.provider}:${defaultProv.model}`
      setSelectedLlmProvider(provKey)
      localStorage.setItem('selectedLLMProviderForTests', provKey)
    }
  }

  const handleLlmProviderChange = (providerKey) => {
    setSelectedLlmProvider(providerKey)
    localStorage.setItem('selectedLLMProviderForTests', providerKey)
  }

  // Load results history for current file
  const loadResultsHistory = async (testFile) => {
    if (!testFile) return
    try {
      const res = await fetch(`/api/results/history/${encodeURIComponent(testFile)}`)
      const data = await res.json()
      setResultsHistory(data.history || [])
    } catch (error) {
      console.error('Failed to load results history:', error)
      setResultsHistory([])
    }
  }

  // Load history when file changes
  useEffect(() => {
    if (selectedFile?.relative_path || selectedFile?.filename) {
      const testFile = selectedFile.relative_path || selectedFile.filename
      loadResultsHistory(testFile)
    }
  }, [selectedFile])

  // Get all providers across all profiles for "Run All" mode
  const getAllProviders = () => {
    const providers = []
    llmProfiles.forEach(profile => {
      profile.providers?.forEach(prov => {
        providers.push({
          profileId: profile.profile_id,
          profileName: profile.name,
          provider: prov.provider,
          model: prov.model,
          name: prov.name,
          key: `${prov.provider}:${prov.model}`
        })
      })
    })
    return providers
  }

  // Get model and provider from selected LLM provider
  const getLlmConfig = () => {
    if (selectedLlmProvider) {
      const [provider, model] = selectedLlmProvider.split(':')
      return { model, provider }
    }
    if (!selectedLlmProfile || llmProfiles.length === 0) {
      return { model: 'claude-sonnet-4-20250514', provider: 'anthropic' }
    }
    const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
    if (!profile || !profile.providers || profile.providers.length === 0) {
      return { model: 'claude-sonnet-4-20250514', provider: 'anthropic' }
    }
    const defaultProvider = profile.providers.find(p => p.default) || profile.providers[0]
    return {
      model: defaultProvider.model || 'claude-sonnet-4-20250514',
      provider: defaultProvider.provider || 'anthropic'
    }
  }

  // Parse test locations when file content changes
  useEffect(() => {
    if (fileContent) {
      const locations = parseTestLocations(fileContent)
      setTestLocations(locations)
      testLocationsRef.current = locations // Keep ref in sync
      // Reset test statuses when content changes (only if not running)
      if (!running) {
        resetTestStatuses(locations.map(t => t.name))
      }
    } else {
      setTestLocations([])
      testLocationsRef.current = []
      if (!running) {
        resetTestStatuses([])
      }
    }
  }, [fileContent, running, resetTestStatuses])

  // Update editor decorations when test statuses change
  const updateEditorDecorations = useCallback(() => {
    if (!editorRef.current || !monacoRef.current) return

    // Use ref to get the latest test locations (avoids stale closure issues)
    const currentTestLocations = testLocationsRef.current
    if (currentTestLocations.length === 0) return

    const editor = editorRef.current
    const monaco = monacoRef.current
    const decorations = []


    currentTestLocations.forEach(test => {
      const status = testStatuses[test.name] || 'idle'
      let className = ''
      let glyphClassName = ''

      switch (status) {
        case 'running':
          className = 'test-line-running'
          glyphClassName = 'test-glyph-running'
          break
        case 'passed':
          className = 'test-line-passed'
          glyphClassName = 'test-glyph-passed'
          break
        case 'failed':
          className = 'test-line-failed'
          glyphClassName = 'test-glyph-failed'
          break
        default:
          className = 'test-line-idle'
          glyphClassName = 'test-glyph-idle'
      }

      decorations.push({
        range: new monaco.Range(test.lineNumber, 1, test.lineNumber, 1),
        options: {
          isWholeLine: true,
          className: className,
          glyphMarginClassName: glyphClassName,
          glyphMarginHoverMessage: { value: `Run test: ${test.name}` },
        }
      })
    })

    // Store decoration IDs for later removal
    const ids = editor.deltaDecorations(
      editor._testDecorationIds || [],
      decorations
    )
    editor._testDecorationIds = ids
  }, [testStatuses])  // Only depends on testStatuses since we use testLocationsRef.current

  // Update decorations when statuses or locations change
  useEffect(() => {
    // Small delay to ensure editor is fully rendered
    const timer = setTimeout(() => {
      updateEditorDecorations()
      // Force editor layout refresh to ensure glyphs render
      if (editorRef.current) {
        editorRef.current.layout()
      }
    }, 50)
    return () => clearTimeout(timer)
  }, [testStatuses, testLocations, updateEditorDecorations])

  // Handle editor mount
  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco

    // Add custom CSS for test decorations - using !important to ensure visibility
    const styleId = 'test-decorations-style'
    if (!document.getElementById(styleId)) {
      const styleEl = document.createElement('style')
      styleEl.id = styleId
      styleEl.textContent = `
        .test-line-idle { background: transparent !important; }
        .test-line-running { background: rgba(234, 179, 8, 0.15) !important; }
        .test-line-passed { background: rgba(34, 197, 94, 0.15) !important; }
        .test-line-failed { background: rgba(239, 68, 68, 0.15) !important; }

        .test-glyph-idle {
          cursor: pointer !important;
        }
        .test-glyph-idle::before {
          content: '▶' !important;
          color: #6b7280 !important;
          font-size: 12px !important;
          cursor: pointer !important;
          display: block !important;
          text-align: center !important;
          line-height: 19px !important;
        }
        .test-glyph-idle:hover::before {
          color: #22c55e !important;
        }
        .test-glyph-running::before {
          content: '●' !important;
          color: #eab308 !important;
          font-size: 14px !important;
          display: block !important;
          text-align: center !important;
          line-height: 19px !important;
          animation: pulse 1s ease-in-out infinite !important;
        }
        .test-glyph-passed::before {
          content: '✓' !important;
          color: #22c55e !important;
          font-size: 14px !important;
          font-weight: bold !important;
          display: block !important;
          text-align: center !important;
          line-height: 19px !important;
        }
        .test-glyph-failed::before {
          content: '✗' !important;
          color: #ef4444 !important;
          font-size: 14px !important;
          font-weight: bold !important;
          display: block !important;
          text-align: center !important;
          line-height: 19px !important;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `
      document.head.appendChild(styleEl)
    }

    // Handle click on glyph margin to run individual test
    editor.onMouseDown((e) => {
      if (e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN) {
        const lineNumber = e.target.position.lineNumber
        // Use ref to avoid stale closure
        const test = testLocationsRef.current.find(t => t.lineNumber === lineNumber)
        if (test) {
          runSingleTest(test.name)
        }
      }
    })

    // Initial decoration update - multiple attempts to ensure it works
    // This handles the case where fileContent/testLocations aren't populated yet on mount
    const attemptDecorations = (attempts = 0) => {
      if (attempts > 8) return
      const delay = attempts === 0 ? 200 : 150 * attempts  // Longer initial delay
      setTimeout(() => {
        updateEditorDecorations()
        editor.layout()
        // If no decorations were applied and testLocations might still be loading, try again
        if (!editor._testDecorationIds || editor._testDecorationIds.length === 0) {
          attemptDecorations(attempts + 1)
        }
      }, delay)
    }
    attemptDecorations()
  }

  // Run a single test by name (uses context for state management)
  const runSingleTest = async (testName) => {
    if (!selectedFile || running) return
    const llmConfig = getLlmConfig()
    const testFile = selectedFile.relative_path || selectedFile.filename
    contextRunSingleTest(testName, testFile, selectedFile.path, llmConfig, selectedMcpProfile)
  }

  const loadTestFiles = async () => {
    try {
      const res = await fetch('/api/tests')
      const data = await res.json()
      setTestData(data)
      // Auto-expand all folders
      if (data.folders) {
        setExpandedFolders(new Set(Object.keys(data.folders)))
      }
    } catch (error) {
      console.error('Failed to load test files:', error)
    }
  }

  const toggleFolder = (folderName) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev)
      if (newSet.has(folderName)) {
        newSet.delete(folderName)
      } else {
        newSet.add(folderName)
      }
      return newSet
    })
  }

  const loadTestFile = async (relativePath) => {
    try {
      const res = await fetch(`/api/tests/${relativePath}`)
      if (!res.ok) {
        // File not found or other error - clear selection
        console.warn(`Test file not found: ${relativePath}`)
        localStorage.removeItem('selectedTestFile')
        setSelectedFile(null)
        setFileContent('')
        return
      }
      const data = await res.json()
      setSelectedFile({...data, relative_path: relativePath})
      setFileContent(data.content)
      setEditMode(false)
      setTestResults(null)
      // Save to localStorage so it persists on reload
      localStorage.setItem('selectedTestFile', relativePath)
    } catch (error) {
      console.error('Failed to load test file:', error)
      // Clear saved selection if file no longer exists
      localStorage.removeItem('selectedTestFile')
      setSelectedFile(null)
      setFileContent('')
    }
  }

  const saveTestFile = async () => {
    if (!selectedFile) return

    try {
      const pathToUse = selectedFile.relative_path || selectedFile.filename

      const response = await fetch(`/api/tests/${pathToUse}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: fileContent }),
      })

      const responseText = await response.text()

      if (!response.ok) {
        let errorDetail = responseText
        try {
          const errorData = JSON.parse(responseText)
          errorDetail = errorData.detail || responseText
        } catch (e) {}
        throw new Error(`HTTP ${response.status}: ${errorDetail}`)
      }

      // Update the selected file's content to match what was saved
      setSelectedFile(prev => ({ ...prev, content: fileContent }))
      setEditMode(false)
      loadTestFiles()
      alert('File saved successfully')
    } catch (error) {
      console.error('Failed to save test file:', error)
      alert(`Failed to save file: ${error.message}`)
    }
  }

  const createTestFile = async () => {
    if (!newFileName.trim()) return

    const defaultContent = `version: "1.0"
tests:
  - name: example_test
    prompt: "Your test prompt here"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "your_tool_name"
`

    try {
      await fetch('/api/tests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: newFileName.endsWith('.yaml')
            ? newFileName
            : `${newFileName}.yaml`,
          content: defaultContent,
        }),
      })
      setShowNewFileDialog(false)
      setNewFileName('')
      loadTestFiles()
    } catch (error) {
      console.error('Failed to create test file:', error)
      alert('Failed to create file')
    }
  }

  const deleteTestFile = async (relativePath) => {
    if (!confirm(`Delete ${relativePath}?`)) return

    try {
      await fetch(`/api/tests/${relativePath}`, { method: 'DELETE' })
      const currentPath = selectedFile?.relative_path || selectedFile?.filename
      if (currentPath === relativePath) {
        setSelectedFile(null)
        setFileContent('')
        // Clear saved selection if deleting the selected file
        localStorage.removeItem('selectedTestFile')
      }
      loadTestFiles()
    } catch (error) {
      console.error('Failed to delete test file:', error)
      alert('Failed to delete file')
    }
  }

  const runTests = async () => {
    if (!selectedFile) return
    const llmConfig = getLlmConfig()
    const testFile = selectedFile.relative_path || selectedFile.filename
    contextRunTests(testFile, selectedFile.path, llmConfig, selectedMcpProfile, testLocations)
    setBottomPanelTab('logs') // Show logs while running
  }

  // Switch to results tab when tests complete
  useEffect(() => {
    if (runningTests.status === 'completed' && testResults) {
      setBottomPanelTab('results')
      // Refresh history after test completes
      if (selectedFile) {
        const testFile = selectedFile.relative_path || selectedFile.filename
        loadResultsHistory(testFile)
      }
    }
  }, [runningTests.status, testResults, selectedFile])

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [streamingLogs])

  // Run tests with ALL LLM providers
  const runTestsWithAllLlms = async () => {
    if (!selectedFile) return

    const allProviders = getAllProviders()
    if (allProviders.length === 0) {
      alert('No LLM providers configured')
      return
    }

    setRunning(true)
    setRunAllLlmsMode(true)
    setAllLlmsResults({})
    setTestResults(null)

    const results = {}
    let completedCount = 0

    for (const prov of allProviders) {
      setRunningTests({
        current: `${prov.name || prov.model} (${prov.provider})`,
        total: allProviders.length,
        completed: completedCount,
        status: 'running'
      })

      try {
        const res = await fetch('/api/tests/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            test_path: selectedFile.path,
            model: prov.model,
            provider: prov.provider,
            profile: selectedMcpProfile,
          }),
        })

        if (res.ok) {
          const data = await res.json()
          results[prov.key] = {
            provider: prov,
            success: true,
            data: data,
            summary: data.summary
          }
        } else {
          const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
          results[prov.key] = {
            provider: prov,
            success: false,
            error: errorData.detail || `HTTP ${res.status}`
          }
        }
      } catch (error) {
        results[prov.key] = {
          provider: prov,
          success: false,
          error: error.message
        }
      }

      completedCount++
      setAllLlmsResults({ ...results })
    }

    setRunning(false)
    setRunAllLlmsMode(false)
    setRunningTests({
      current: null,
      total: 0,
      completed: 0,
      status: 'idle'
    })
  }

  return (
    <div className="h-full flex flex-col">
      {/* Profile Selectors */}
      <div className="px-6 py-3 border-b border-border bg-surface-elevated">
        <div className="grid grid-cols-4 gap-4">
          {/* MCP Profile Selector */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">
              MCP Profile
            </label>
            <select
              value={selectedMcpProfile || ''}
              onChange={(e) => handleMcpProfileChange(e.target.value)}
              className="input text-sm"
            >
              {!selectedMcpProfile && <option value="">Select MCP...</option>}
              {mcpProfiles.map(profile => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} ({profile.mcps.length} server{profile.mcps.length !== 1 ? 's' : ''})
                </option>
              ))}
            </select>
          </div>

          {/* LLM Profile Selector */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">
              LLM Profile
            </label>
            <select
              value={selectedLlmProfile || ''}
              onChange={(e) => handleLlmProfileChange(e.target.value)}
              className="input text-sm"
            >
              {!selectedLlmProfile && <option value="">Select LLM...</option>}
              {llmProfiles.map(profile => {
                const defaultProvider = profile.providers?.find(p => p.default) || profile.providers?.[0]
                return (
                  <option key={profile.profile_id} value={profile.profile_id}>
                    {profile.name} {defaultProvider ? `(${defaultProvider.model})` : ''}
                  </option>
                )
              })}
            </select>
          </div>

          {/* LLM Provider Selector (within selected profile) */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">
              LLM Provider
            </label>
            <select
              value={selectedLlmProvider || ''}
              onChange={(e) => handleLlmProviderChange(e.target.value)}
              className="input text-sm"
              disabled={!selectedLlmProfile}
            >
              {!selectedLlmProvider && <option value="">Select provider...</option>}
              {selectedLlmProfile && llmProfiles.find(p => p.profile_id === selectedLlmProfile)?.providers?.map(prov => {
                const provKey = `${prov.provider}:${prov.model}`
                return (
                  <option key={provKey} value={provKey}>
                    {prov.name || prov.model} ({prov.provider})
                  </option>
                )
              })}
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* File List Sidebar */}
        <div className="w-80 flex-shrink-0 border-r border-border flex flex-col bg-surface-elevated overflow-hidden">
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-text-primary">Test Files</h2>
              <button
                onClick={() => setShowNewFileDialog(true)}
                className="p-2 hover:bg-surface-hover rounded-lg transition-all duration-200 text-text-secondary hover:text-text-primary"
                title="Create new test file"
              >
                <Plus size={20} />
              </button>
            </div>

          {showNewFileDialog && (
            <div className="space-y-3 p-4 bg-surface rounded-lg border border-border animate-fade-in">
              <input
                type="text"
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                placeholder="test_name.yaml"
                className="input w-full text-sm"
                autoFocus
              />
              <div className="flex gap-2">
                <button
                  onClick={createTestFile}
                  className="btn btn-primary text-sm flex-1"
                >
                  <Plus size={16} />
                  <span>Create</span>
                </button>
                <button
                  onClick={() => {
                    setShowNewFileDialog(false)
                    setNewFileName('')
                  }}
                  className="btn btn-secondary text-sm px-3"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {/* Root files */}
          {testData.files && testData.files.map((file) => (
            <div
              key={file.relative_path}
              className={`p-4 border-b border-border cursor-pointer transition-all duration-200 group ${
                (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                  ? 'bg-surface border-l-2 border-l-primary'
                  : 'hover:bg-surface border-l-2 border-l-transparent'
              }`}
              onClick={() => loadTestFile(file.relative_path)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <FileText size={18} className={`flex-shrink-0 ${
                    (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                      ? 'text-primary'
                      : 'text-text-tertiary group-hover:text-text-secondary'
                  }`} />
                  <span className={`font-medium truncate ${
                    (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                      ? 'text-text-primary'
                      : 'text-text-secondary'
                  }`}>
                    {file.filename}
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteTestFile(file.relative_path)
                  }}
                  className="p-1.5 hover:bg-error/20 rounded transition-all duration-200 opacity-0 group-hover:opacity-100"
                  title="Delete file"
                >
                  <Trash2 size={14} className="text-error" />
                </button>
              </div>
              <div className="text-xs text-text-tertiary mt-2 ml-7">
                {file.test_count} test{file.test_count !== 1 ? 's' : ''}
              </div>
            </div>
          ))}

          {/* Folders */}
          {testData.folders && Object.entries(testData.folders).sort().map(([folderName, files]) => (
            <div key={folderName} className="border-b border-border">
              {/* Folder Header */}
              <div
                className="p-4 cursor-pointer hover:bg-surface-hover transition-all duration-200 flex items-center gap-2"
                onClick={() => toggleFolder(folderName)}
              >
                {expandedFolders.has(folderName) ? (
                  <ChevronDown size={16} className="text-text-tertiary" />
                ) : (
                  <ChevronRight size={16} className="text-text-tertiary" />
                )}
                <Folder size={18} className="text-primary" />
                <span className="font-medium text-text-primary">{folderName}</span>
                <span className="text-xs text-text-tertiary ml-auto">{files.length} file{files.length !== 1 ? 's' : ''}</span>
              </div>

              {/* Folder Files */}
              {expandedFolders.has(folderName) && files.map((file) => (
                <div
                  key={file.relative_path}
                  className={`pl-12 pr-4 py-3 border-t border-border cursor-pointer transition-all duration-200 group ${
                    (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                      ? 'bg-surface border-l-2 border-l-primary'
                      : 'hover:bg-surface border-l-2 border-l-transparent'
                  }`}
                  onClick={() => loadTestFile(file.relative_path)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <FileText size={16} className={`flex-shrink-0 ${
                        (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                          ? 'text-primary'
                          : 'text-text-tertiary group-hover:text-text-secondary'
                      }`} />
                      <span className={`text-sm truncate ${
                        (selectedFile?.relative_path || selectedFile?.filename) === file.relative_path
                          ? 'text-text-primary font-medium'
                          : 'text-text-secondary'
                      }`}>
                        {file.filename}
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteTestFile(file.relative_path)
                      }}
                      className="p-1.5 hover:bg-error/20 rounded transition-all duration-200 opacity-0 group-hover:opacity-100"
                      title="Delete file"
                    >
                      <Trash2 size={12} className="text-error" />
                    </button>
                  </div>
                  <div className="text-xs text-text-tertiary mt-1 ml-5">
                    {file.test_count} test{file.test_count !== 1 ? 's' : ''}
                  </div>
                </div>
              ))}
            </div>
          ))}

          {/* Empty State */}
          {(!testData.files || testData.files.length === 0) && (!testData.folders || Object.keys(testData.folders).length === 0) && (
            <div className="p-8 text-center">
              <FileText size={40} className="mx-auto mb-3 text-text-disabled opacity-50" />
              <p className="text-text-tertiary">No test files found</p>
              <p className="text-text-disabled text-xs mt-1">Create one to get started</p>
            </div>
          )}
        </div>
        </div>  {/* End sidebar */}

        {/* Editor & Results - inside main flex container, sibling to sidebar */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {selectedFile ? (
          <>
            {/* Editor Header - fixed height, won't shrink */}
            <div className="flex-shrink-0 border-b border-border bg-surface-elevated">
              {/* Top row: File info and edit controls */}
              <div className="px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-primary/10">
                    <FileText size={18} className="text-primary" />
                  </div>
                  <div>
                    <h2 className="font-semibold text-text-primary">{selectedFile.filename}</h2>
                    {selectedFile.relative_path && selectedFile.relative_path.includes('/') && (
                      <p className="text-xs text-text-tertiary mt-0.5">
                        {selectedFile.relative_path.split('/').slice(0, -1).join('/')}
                      </p>
                    )}
                  </div>
                  {testLocations.length > 0 && (
                    <span className="px-2 py-0.5 text-xs rounded-full bg-surface text-text-secondary border border-border">
                      {testLocations.length} test{testLocations.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {editMode ? (
                    <>
                      <button
                        onClick={() => {
                          setEditMode(false)
                          setFileContent(selectedFile.content)
                        }}
                        className="btn btn-ghost text-sm"
                      >
                        <X size={16} />
                        <span>Cancel</span>
                      </button>
                      <button
                        onClick={saveTestFile}
                        className="btn btn-primary text-sm"
                      >
                        <Save size={16} />
                        <span>Save Changes</span>
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setEditMode(true)}
                      className="btn btn-ghost text-sm"
                    >
                      <Edit size={16} />
                      <span>Edit</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Bottom row: Run controls and LLM info */}
              <div className="px-4 py-2 flex items-center justify-between border-t border-border/50 bg-surface">
                <div className="flex items-center gap-2">
                  <button
                    onClick={runTests}
                    disabled={running || !selectedFile}
                    className={`btn ${running && !runAllLlmsMode ? 'btn-warning' : 'btn-primary'} text-sm`}
                  >
                    {running && !runAllLlmsMode ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Play size={14} />
                    )}
                    <span>{running && !runAllLlmsMode ? 'Running...' : 'Run Tests'}</span>
                  </button>
                  <button
                    onClick={runTestsWithAllLlms}
                    disabled={running || !selectedFile}
                    className="btn btn-secondary text-sm"
                    title="Run tests with all configured LLM providers"
                  >
                    {running && runAllLlmsMode ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Play size={14} />
                    )}
                    <span>{running && runAllLlmsMode ? `${runningTests.completed}/${runningTests.total}` : 'All LLMs'}</span>
                  </button>
                  {resultsHistory.length > 0 && (
                    <button
                      onClick={() => setShowHistory(!showHistory)}
                      className={`btn ${showHistory ? 'btn-primary' : 'btn-ghost'} text-sm`}
                      title="View test run history"
                    >
                      <History size={14} />
                      <span>History</span>
                      <span className="px-1.5 py-0.5 rounded bg-surface text-[10px]">{resultsHistory.length}</span>
                    </button>
                  )}
                </div>

                {selectedLlmProvider && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-text-tertiary">Using:</span>
                    <span className="px-2 py-1 rounded bg-surface-elevated border border-border text-text-secondary font-mono">
                      {selectedLlmProvider.split(':')[1]}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-blue-500/20 text-blue-400">
                      {selectedLlmProvider.split(':')[0]}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Split view: Editor + Bottom Panel */}
            <div className="flex-1 flex flex-col overflow-hidden relative min-h-0">
              {/* Editor area - always takes remaining space */}
              <div className="flex-1 overflow-hidden min-h-0">
                <Editor
                  height="100%"
                  defaultLanguage="yaml"
                  theme="vs-dark"
                  value={fileContent}
                  onChange={(value) => setFileContent(value || '')}
                  onMount={handleEditorDidMount}
                  options={{
                    readOnly: !editMode,
                    minimap: { enabled: false },
                    fontSize: 14,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    glyphMargin: true,
                    folding: true,
                    lineDecorationsWidth: 5,
                  }}
                />
              </div>

              {/* Bottom Panel - Fixed height, doesn't affect editor */}
              {(running || streamingLogs.length > 0 || testResults) && (
                <div className="h-[280px] flex-shrink-0 border-t border-border flex flex-col bg-surface">
                  {/* Tab Bar */}
                  <div className="flex items-center border-b border-border bg-surface-elevated px-2">
                    {/* Logs Tab */}
                    <button
                      className={`px-3 py-2 text-xs font-medium flex items-center gap-2 border-b-2 transition-colors ${
                        bottomPanelTab === 'logs'
                          ? 'border-primary text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`}
                      onClick={() => setBottomPanelTab('logs')}
                    >
                      <Terminal size={12} />
                      <span>Logs</span>
                      {running && <Loader2 size={10} className="animate-spin text-yellow-400" />}
                      {!running && streamingLogs.length > 0 && (
                        <span className="px-1.5 py-0.5 rounded bg-surface text-[10px]">{streamingLogs.length}</span>
                      )}
                    </button>
                    {/* Results Tab */}
                    {testResults && (
                      <button
                        className={`px-3 py-2 text-xs font-medium flex items-center gap-2 border-b-2 transition-colors ${
                          bottomPanelTab === 'results'
                            ? 'border-primary text-primary'
                            : 'border-transparent text-text-tertiary hover:text-text-secondary'
                        }`}
                        onClick={() => setBottomPanelTab('results')}
                      >
                        <CheckCircle size={12} />
                        <span>Results</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                          testResults.summary.failed > 0 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'
                        }`}>
                          {testResults.summary.passed}/{testResults.summary.total}
                        </span>
                      </button>
                    )}
                    {/* Spacer */}
                    <div className="flex-1" />
                    {/* Clear/Close buttons */}
                    {bottomPanelTab === 'logs' && !running && streamingLogs.length > 0 && (
                      <button
                        onClick={clearLogs}
                        className="px-2 py-1 text-xs text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
                      >
                        Clear
                      </button>
                    )}
                    <button
                      onClick={() => { clearResults(); setBottomPanelTab('logs'); }}
                      className="p-1.5 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
                      title="Close panel"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  {/* Panel Content */}
                  <div className="flex-1 overflow-hidden">
                    {/* Show content based on selected tab */}
                    {bottomPanelTab === 'results' && testResults ? (
                      /* Results Content */
                      <div className="h-full flex flex-col">
                        {/* Results Summary Bar */}
                        <div className="px-4 py-2 bg-surface-elevated/50 flex items-center gap-6 text-xs border-b border-border/50">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-green-500"></div>
                            <span className="text-text-tertiary">Passed:</span>
                            <span className="font-semibold text-green-400">{testResults.summary.passed}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-red-500"></div>
                            <span className="text-text-tertiary">Failed:</span>
                            <span className="font-semibold text-red-400">{testResults.summary.failed}</span>
                          </div>
                          {testResults.summary.total_cost > 0 && (
                            <div className="flex items-center gap-2">
                              <span className="text-text-tertiary">Cost:</span>
                              <span className="font-mono text-text-secondary">${testResults.summary.total_cost.toFixed(4)}</span>
                            </div>
                          )}
                        </div>
                        {/* Results List */}
                        <div className="flex-1 overflow-auto p-3">
                          {testResults.results && testResults.results.length > 0 ? (
                            <div className="space-y-2">
                              {testResults.results.map((result, idx) => (
                                <TestResultPanel
                                  key={idx}
                                  result={result}
                                  initialExpanded={!result.passed}
                                />
                              ))}
                            </div>
                          ) : (
                            <div className="text-center py-4 text-text-tertiary text-sm">
                              No test results available
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      /* Logs Content */
                      <div className="h-full overflow-auto p-3 font-mono text-xs bg-gray-950">
                        {streamingLogs.length === 0 ? (
                          <div className="text-gray-500 text-center py-4">
                            Waiting for test execution...
                          </div>
                        ) : (
                          streamingLogs.map((log, idx) => (
                            <div
                              key={idx}
                              className={`py-0.5 leading-relaxed ${
                                log.includes('Error') || log.includes('❌') || log.includes('FAILED') ? 'text-red-400' :
                                log.includes('Tool call') || log.includes('🔧') ? 'text-cyan-400' :
                                log.includes('✅') || log.includes('PASSED') ? 'text-green-400' :
                                log.includes('⏱️') || log.includes('Running') || log.includes('🧪') ? 'text-yellow-400' :
                                log.includes('📁') || log.includes('📋') || log.includes('🤖') || log.includes('🔌') ? 'text-blue-400' :
                                log.includes('===') || log.includes('---') ? 'text-gray-600' :
                                log.includes('💰') || log.includes('📊') ? 'text-purple-400' :
                                'text-gray-300'
                              }`}
                            >
                              {log}
                            </div>
                          ))
                        )}
                        <div ref={logsEndRef} />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Visual Test Execution Status - floating indicator */}
              {running && (
                <div className="absolute top-2 right-2 z-10">
                  <TestStatusIndicator
                    current={runningTests.current}
                    completed={runningTests.completed}
                    total={runningTests.total}
                    status={runningTests.status}
                  />
                </div>
              )}

              {/* History Panel */}
              {showHistory && resultsHistory.length > 0 && (
                <div className="h-[320px] flex-shrink-0 border-t border-border overflow-hidden flex flex-col bg-surface">
                  <div className="px-4 py-2 border-b border-border bg-surface-elevated flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <History size={14} className="text-primary" />
                      <h3 className="font-medium text-sm text-text-primary">Run History</h3>
                      <span className="px-2 py-0.5 text-xs rounded bg-surface text-text-tertiary">
                        {resultsHistory.length} run{resultsHistory.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <button
                      onClick={() => setShowHistory(false)}
                      className="p-1.5 hover:bg-surface-hover rounded text-text-tertiary hover:text-text-primary transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  <div className="flex-1 flex overflow-hidden">
                    {/* Timeline Chart */}
                    <div className="w-64 flex-shrink-0 border-r border-border p-3 overflow-hidden">
                      <div className="text-xs text-text-tertiary mb-2 font-medium">Pass Rate Timeline</div>
                      <div className="h-full flex flex-col justify-end pb-6">
                        <div className="flex items-end gap-1 h-32">
                          {resultsHistory.slice(0, 12).reverse().map((run, idx) => {
                            const passRate = run.pass_rate * 100
                            const height = Math.max(4, passRate)
                            return (
                              <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                                <div
                                  className={`w-full rounded-t transition-all cursor-pointer hover:opacity-80 ${
                                    passRate === 100 ? 'bg-green-500' : passRate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                                  }`}
                                  style={{ height: `${height}%` }}
                                  title={`${passRate.toFixed(0)}% - ${new Date(run.timestamp).toLocaleDateString()}`}
                                  onClick={() => setSelectedHistoryRun(run)}
                                />
                              </div>
                            )
                          })}
                        </div>
                        <div className="flex justify-between text-[10px] text-text-disabled mt-1">
                          <span>Older</span>
                          <span>Recent</span>
                        </div>
                      </div>
                    </div>

                    {/* Run List */}
                    <div className="flex-1 overflow-auto">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-surface-elevated">
                          <tr className="border-b border-border">
                            <th className="text-left py-2 px-3 text-text-tertiary font-medium">Date</th>
                            <th className="text-left py-2 px-3 text-text-tertiary font-medium">Provider</th>
                            <th className="text-left py-2 px-3 text-text-tertiary font-medium">Model</th>
                            <th className="text-center py-2 px-3 text-text-tertiary font-medium">Pass</th>
                            <th className="text-right py-2 px-3 text-text-tertiary font-medium">Cost</th>
                            <th className="text-right py-2 px-3 text-text-tertiary font-medium">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {resultsHistory.map((run, idx) => (
                            <tr
                              key={idx}
                              className={`border-b border-border/30 cursor-pointer transition-colors ${
                                selectedHistoryRun?.run_id === run.run_id
                                  ? 'bg-primary/10'
                                  : 'hover:bg-surface-hover'
                              }`}
                              onClick={() => setSelectedHistoryRun(selectedHistoryRun?.run_id === run.run_id ? null : run)}
                            >
                              <td className="py-2 px-3 text-text-secondary">
                                {new Date(run.timestamp).toLocaleDateString()} {new Date(run.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                              </td>
                              <td className="py-2 px-3">
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400">
                                  {run.provider}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-text-secondary font-mono truncate max-w-[120px]" title={run.model}>
                                {run.model?.split('-').slice(-2).join('-') || run.model}
                              </td>
                              <td className="py-2 px-3 text-center">
                                <span className={`font-semibold ${
                                  run.pass_rate === 1 ? 'text-green-400' : run.pass_rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                  {run.passed}/{run.total}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right text-text-tertiary font-mono">
                                ${run.total_cost?.toFixed(4) || '0.00'}
                              </td>
                              <td className="py-2 px-3 text-right text-text-tertiary">
                                {run.total_duration?.toFixed(1)}s
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Selected Run Details */}
                    {selectedHistoryRun && (
                      <div className="w-72 flex-shrink-0 border-l border-border p-3 overflow-auto bg-surface-elevated/50">
                        <div className="text-xs font-medium text-text-primary mb-2">Run Details</div>
                        <div className="space-y-2 text-xs">
                          <div className="flex justify-between">
                            <span className="text-text-tertiary">Run ID</span>
                            <span className="text-text-secondary font-mono">{selectedHistoryRun.run_id?.slice(0, 12)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-tertiary">Pass Rate</span>
                            <span className={`font-semibold ${
                              selectedHistoryRun.pass_rate === 1 ? 'text-green-400' : 'text-yellow-400'
                            }`}>
                              {(selectedHistoryRun.pass_rate * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-tertiary">Tests</span>
                            <span className="text-text-secondary">{selectedHistoryRun.passed} / {selectedHistoryRun.total}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-tertiary">Cost</span>
                            <span className="text-text-secondary font-mono">${selectedHistoryRun.total_cost?.toFixed(4)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-text-tertiary">Duration</span>
                            <span className="text-text-secondary">{selectedHistoryRun.total_duration?.toFixed(1)}s</span>
                          </div>
                          {selectedHistoryRun.test_scores && (
                            <div className="mt-3 pt-3 border-t border-border">
                              <div className="text-text-tertiary mb-2">Per-Test Results</div>
                              {Object.entries(selectedHistoryRun.test_scores).map(([name, score]) => (
                                <div key={name} className="flex items-center justify-between py-1">
                                  <span className="text-text-secondary truncate max-w-[140px]" title={name}>{name}</span>
                                  {score.passed ? (
                                    <CheckCircle size={12} className="text-green-400" />
                                  ) : (
                                    <XCircle size={12} className="text-red-400" />
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* All LLMs Results Panel */}
              {allLlmsResults && Object.keys(allLlmsResults).length > 0 && !running && (
                <div className="h-[280px] flex-shrink-0 border-t border-border overflow-hidden flex flex-col bg-surface">
                  <div className="px-4 py-3 border-b border-border bg-surface-elevated flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <h3 className="font-medium text-sm text-text-primary">All LLMs Comparison</h3>
                      <span className="px-2 py-0.5 text-xs rounded bg-surface text-text-tertiary">
                        {Object.keys(allLlmsResults).length} provider{Object.keys(allLlmsResults).length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <button
                      onClick={() => setAllLlmsResults(null)}
                      className="p-1.5 hover:bg-surface-hover rounded text-text-tertiary hover:text-text-primary transition-colors"
                      title="Close"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  <div className="flex-1 overflow-auto p-3 bg-surface">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left py-2 px-3 text-text-secondary font-medium">Provider</th>
                            <th className="text-left py-2 px-3 text-text-secondary font-medium">Model</th>
                            <th className="text-center py-2 px-3 text-text-secondary font-medium">Status</th>
                            <th className="text-center py-2 px-3 text-text-secondary font-medium">Passed</th>
                            <th className="text-center py-2 px-3 text-text-secondary font-medium">Failed</th>
                            <th className="text-right py-2 px-3 text-text-secondary font-medium">Cost</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.values(allLlmsResults).map((result, idx) => (
                            <tr key={idx} className="border-b border-border/50 hover:bg-surface-hover">
                              <td className="py-2 px-3 text-text-primary">
                                <span className="inline-flex items-center gap-1.5">
                                  {result.provider.provider}
                                  {['claude-cli', 'codex-cli'].includes(result.provider.provider) && (
                                    <span className="px-1.5 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded">CLI</span>
                                  )}
                                  {['claude-sdk'].includes(result.provider.provider) && (
                                    <span className="px-1.5 py-0.5 text-xs bg-cyan-500/20 text-cyan-400 rounded">SDK</span>
                                  )}
                                  {['anthropic', 'openai'].includes(result.provider.provider) && (
                                    <span className="px-1.5 py-0.5 text-xs bg-emerald-500/20 text-emerald-400 rounded">API</span>
                                  )}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-text-secondary font-mono text-xs">
                                {result.provider.model}
                              </td>
                              <td className="py-2 px-3 text-center">
                                {result.success ? (
                                  <CheckCircle size={16} className="inline text-success" />
                                ) : (
                                  <XCircle size={16} className="inline text-error" />
                                )}
                              </td>
                              <td className="py-2 px-3 text-center text-success font-medium">
                                {result.success ? result.summary?.passed || 0 : '-'}
                              </td>
                              <td className="py-2 px-3 text-center text-error font-medium">
                                {result.success ? result.summary?.failed || 0 : '-'}
                              </td>
                              <td className="py-2 px-3 text-right text-text-tertiary">
                                {result.success && result.summary?.total_cost
                                  ? `$${result.summary.total_cost.toFixed(4)}`
                                  : result.error
                                    ? <span className="text-error text-xs" title={result.error}>Error</span>
                                    : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full bg-background-subtle">
            <div className="text-center">
              <div className="w-20 h-20 bg-surface-elevated rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                <FileText size={36} className="text-text-disabled" />
              </div>
              <p className="text-lg text-text-secondary">Select a test file to view or edit</p>
              <p className="text-sm text-text-tertiary mt-2">Choose a file from the sidebar to get started</p>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  )
}

export default TestManager
