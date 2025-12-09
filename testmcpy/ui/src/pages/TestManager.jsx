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
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import TestStatusIndicator from '../components/TestStatusIndicator'
import TestResultPanel from '../components/TestResultPanel'
import { useKeyboardShortcuts, useAnnounce } from '../hooks/useKeyboardShortcuts'

// Parse YAML content to find test locations (line numbers)
function parseTestLocations(content) {
  const lines = content.split('\n')
  const tests = []
  let inTestsArray = false
  let currentIndent = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Detect start of tests array
    if (trimmed === 'tests:') {
      inTestsArray = true
      currentIndent = line.indexOf('tests:')
      continue
    }

    if (inTestsArray) {
      // Check for test item (starts with "- name:")
      const match = line.match(/^(\s*)- name:\s*["']?([^"'\n]+)["']?/)
      if (match) {
        const indent = match[1].length
        // Make sure it's at the right indentation level (inside tests array)
        if (indent > currentIndent) {
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
  const [testData, setTestData] = useState({ folders: {}, files: [] })
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [editMode, setEditMode] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [showNewFileDialog, setShowNewFileDialog] = useState(false)
  const [testResults, setTestResults] = useState(null)
  const [running, setRunning] = useState(false)
  const [runningTestName, setRunningTestName] = useState(null)
  const [testLocations, setTestLocations] = useState([])
  const [testStatuses, setTestStatuses] = useState({}) // { testName: 'idle' | 'running' | 'passed' | 'failed' }
  const editorRef = useRef(null)
  const monacoRef = useRef(null)
  const testLocationsRef = useRef([]) // Ref to avoid stale closure in click handler
  const [runningTests, setRunningTests] = useState({
    current: null,
    total: 0,
    completed: 0,
    status: 'idle'
  })
  const [testProfiles, setTestProfiles] = useState([])
  const [selectedTestProfile, setSelectedTestProfile] = useState(null)
  const [mcpProfiles, setMcpProfiles] = useState([])
  const [selectedMcpProfile, setSelectedMcpProfile] = useState(null)
  const [llmProfiles, setLlmProfiles] = useState([])
  const [selectedLlmProfile, setSelectedLlmProfile] = useState(null)

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

      // Check localStorage for saved LLM profile
      const savedProfile = localStorage.getItem('selectedLLMProfileForTests')
      if (savedProfile) {
        setSelectedLlmProfile(savedProfile)
      } else if (data.default) {
        setSelectedLlmProfile(data.default)
        localStorage.setItem('selectedLLMProfileForTests', data.default)
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
  }

  // Get model and provider from selected LLM profile
  const getLlmConfig = () => {
    if (!selectedLlmProfile || llmProfiles.length === 0) {
      return { model: 'claude-sonnet-4-5', provider: 'anthropic' }
    }
    const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
    if (!profile || !profile.providers || profile.providers.length === 0) {
      return { model: 'claude-sonnet-4-5', provider: 'anthropic' }
    }
    const defaultProvider = profile.providers.find(p => p.default) || profile.providers[0]
    return {
      model: defaultProvider.model || 'claude-sonnet-4-5',
      provider: defaultProvider.provider || 'anthropic'
    }
  }

  // Parse test locations when file content changes
  useEffect(() => {
    if (fileContent) {
      const locations = parseTestLocations(fileContent)
      setTestLocations(locations)
      testLocationsRef.current = locations // Keep ref in sync
      // Reset test statuses when content changes
      const initialStatuses = {}
      locations.forEach(t => initialStatuses[t.name] = 'idle')
      setTestStatuses(initialStatuses)
    } else {
      setTestLocations([])
      testLocationsRef.current = []
      setTestStatuses({})
    }
  }, [fileContent])

  // Update editor decorations when test statuses change
  const updateEditorDecorations = useCallback(() => {
    if (!editorRef.current || !monacoRef.current) return
    if (testLocations.length === 0) return

    const editor = editorRef.current
    const monaco = monacoRef.current
    const decorations = []

    console.log('Updating decorations for tests:', testLocations.map(t => t.name))

    testLocations.forEach(test => {
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
  }, [testLocations, testStatuses])

  // Update decorations when statuses or locations change
  useEffect(() => {
    updateEditorDecorations()
  }, [testStatuses, testLocations, updateEditorDecorations])

  // Handle editor mount
  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco

    // Add custom CSS for test decorations
    const styleEl = document.createElement('style')
    styleEl.textContent = `
      .test-line-idle { background: transparent; }
      .test-line-running { background: rgba(234, 179, 8, 0.15) !important; }
      .test-line-passed { background: rgba(34, 197, 94, 0.15) !important; }
      .test-line-failed { background: rgba(239, 68, 68, 0.15) !important; }

      .test-glyph-idle::before {
        content: '\\25B6';
        color: #6b7280;
        font-size: 10px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
      }
      .test-glyph-idle:hover::before { color: #22c55e; }
      .test-glyph-running::before {
        content: '';
        width: 10px;
        height: 10px;
        border: 2px solid #eab308;
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: auto;
      }
      .test-glyph-passed::before {
        content: '\\2713';
        color: #22c55e;
        font-size: 12px;
        font-weight: bold;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
      }
      .test-glyph-failed::before {
        content: '\\2717';
        color: #ef4444;
        font-size: 12px;
        font-weight: bold;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
    `
    document.head.appendChild(styleEl)

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

    // Initial decoration update
    setTimeout(updateEditorDecorations, 100)
  }

  // Run a single test by name
  const runSingleTest = async (testName) => {
    if (!selectedFile || running) return

    setRunning(true)
    setRunningTestName(testName)
    setTestStatuses(prev => ({ ...prev, [testName]: 'running' }))

    try {
      const llmConfig = getLlmConfig()
      const res = await fetch('/api/tests/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_path: selectedFile.path,
          model: llmConfig.model,
          provider: llmConfig.provider,
          profile: selectedMcpProfile,
          test_name: testName, // Run only this test
        }),
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()

      // Update status based on result
      const testResult = data.results?.find(r => r.test_name === testName)
      if (testResult) {
        setTestStatuses(prev => ({
          ...prev,
          [testName]: testResult.passed ? 'passed' : 'failed'
        }))
      }

      // Merge with existing results or set new results
      setTestResults(prev => {
        if (!prev) return data
        // Merge results
        const existingResults = prev.results.filter(r => r.test_name !== testName)
        return {
          ...data,
          results: [...existingResults, ...(data.results || [])],
          summary: {
            total: existingResults.length + (data.results?.length || 0),
            passed: existingResults.filter(r => r.passed).length + (data.summary?.passed || 0),
            failed: existingResults.filter(r => !r.passed).length + (data.summary?.failed || 0),
            total_cost: (prev.summary?.total_cost || 0) + (data.summary?.total_cost || 0)
          }
        }
      })
    } catch (error) {
      console.error('Failed to run test:', error)
      setTestStatuses(prev => ({ ...prev, [testName]: 'failed' }))
    } finally {
      setRunning(false)
      setRunningTestName(null)
    }
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
    }
  }

  const saveTestFile = async () => {
    if (!selectedFile) return

    try {
      const pathToUse = selectedFile.relative_path || selectedFile.filename
      await fetch(`/api/tests/${pathToUse}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: fileContent }),
      })
      setEditMode(false)
      loadTestFiles()
      alert('File saved successfully')
    } catch (error) {
      console.error('Failed to save test file:', error)
      alert('Failed to save file')
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

    setRunning(true)
    setTestResults(null)

    // Initialize running tests state and set all tests to running
    const totalTests = selectedFile.test_count || 1
    setRunningTests({
      current: 'Initializing...',
      total: totalTests,
      completed: 0,
      status: 'running'
    })

    // Mark all tests as running
    const runningStatuses = {}
    testLocations.forEach(t => runningStatuses[t.name] = 'running')
    setTestStatuses(runningStatuses)

    try {
      const llmConfig = getLlmConfig()
      const res = await fetch('/api/tests/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_path: selectedFile.path,
          model: llmConfig.model,
          provider: llmConfig.provider,
          profile: selectedMcpProfile,
        }),
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      console.log('Test results received:', data)
      setTestResults(data)

      // Update test statuses based on results
      if (data.results) {
        const newStatuses = {}
        data.results.forEach(result => {
          newStatuses[result.test_name] = result.passed ? 'passed' : 'failed'
        })
        setTestStatuses(prev => ({ ...prev, ...newStatuses }))
      }
    } catch (error) {
      console.error('Failed to run tests:', error)
      setTestResults({
        summary: {
          total: 0,
          passed: 0,
          failed: 0,
          total_cost: 0
        },
        results: [],
        error: error.message
      })
      // Mark all tests as failed on error
      const failedStatuses = {}
      testLocations.forEach(t => failedStatuses[t.name] = 'failed')
      setTestStatuses(failedStatuses)
      alert(`Failed to run tests: ${error.message}`)
    } finally {
      setRunning(false)
      setRunningTests({
        current: null,
        total: 0,
        completed: 0,
        status: 'idle'
      })
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Profile Selectors */}
      <div className="px-6 py-3 border-b border-border bg-surface-elevated">
        <div className="grid grid-cols-3 gap-4">
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

          {/* Test Profile Selector */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">
              Test Environment
            </label>
            <select
              value={selectedTestProfile || ''}
              onChange={(e) => handleTestProfileChange(e.target.value)}
              className="input text-sm"
            >
              {!selectedTestProfile && <option value="">Select environment...</option>}
              {testProfiles.map(profile => {
                const defaultConfig = profile.test_configs?.find(c => c.default) || profile.test_configs?.[0]
                return (
                  <option key={profile.profile_id} value={profile.profile_id}>
                    {profile.name} {defaultConfig ? `(${defaultConfig.tests_dir})` : ''}
                  </option>
                )
              })}
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 flex">
        {/* File List */}
        <div className="w-80 border-r border-border flex flex-col bg-surface-elevated">
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
      </div>

      {/* Editor & Results */}
      <div className="flex-1 flex flex-col">
        {selectedFile ? (
          <>
            {/* Editor Header */}
            <div className="p-4 border-b border-border flex items-center justify-between bg-surface-elevated">
              <div className="flex items-center gap-4">
                <h2 className="font-semibold text-lg text-text-primary">{selectedFile.filename}</h2>
                {editMode ? (
                  <div className="flex gap-2">
                    <button
                      onClick={saveTestFile}
                      className="btn btn-primary text-sm"
                    >
                      <Save size={16} />
                      <span>Save</span>
                    </button>
                    <button
                      onClick={() => {
                        setEditMode(false)
                        setFileContent(selectedFile.content)
                      }}
                      className="btn btn-secondary text-sm"
                    >
                      <span>Cancel</span>
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditMode(true)}
                    className="btn btn-secondary text-sm"
                  >
                    <Edit size={16} />
                    <span>Edit</span>
                  </button>
                )}
              </div>

              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={runTests}
                  disabled={running || !selectedFile}
                  className="btn btn-primary"
                >
                  <Play size={16} />
                  <span>{running ? 'Running...' : 'Run Tests'}</span>
                </button>
                {selectedLlmProfile && llmProfiles.length > 0 && (
                  <div className="text-xs text-text-tertiary">
                    Using: {llmProfiles.find(p => p.profile_id === selectedLlmProfile)?.name || 'Default'} profile
                  </div>
                )}
              </div>
            </div>

            {/* Split view: Editor + Results */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Editor area */}
              <div className={`${testResults && !running ? 'h-1/2' : 'flex-1'} transition-all duration-300 overflow-hidden`}>
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

              {/* Visual Test Execution Status (section 4.1) */}
              <TestStatusIndicator
                current={runningTests.current}
                completed={runningTests.completed}
                total={runningTests.total}
                status={runningTests.status}
              />

              {/* Results panel (slides up from bottom) - section 4.4 */}
              {testResults && !running && (
                <div className="h-1/2 border-t border-border overflow-hidden flex flex-col animate-slide-up">
                  {/* Results Header */}
                  <div className="p-4 border-b border-border bg-surface-elevated">
                    {testResults.error && (
                      <div className="mb-4 p-3 bg-error/10 border border-error/30 rounded-lg">
                        <p className="text-sm text-error font-medium">
                          Error: {testResults.error}
                        </p>
                      </div>
                    )}

                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-lg text-text-primary">Test Results</h3>
                      <div className="flex gap-6 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-success"></div>
                          <span className="text-text-secondary">Passed:</span>
                          <span className="font-semibold text-success">{testResults.summary.passed}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-error"></div>
                          <span className="text-text-secondary">Failed:</span>
                          <span className="font-semibold text-error">{testResults.summary.failed}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-text-secondary">Total:</span>
                          <span className="font-semibold text-text-primary">{testResults.summary.total}</span>
                        </div>
                        {testResults.summary.total_cost > 0 && (
                          <div className="flex items-center gap-2">
                            <span className="text-text-secondary">Cost:</span>
                            <span className="font-semibold text-text-primary">${testResults.summary.total_cost.toFixed(4)}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Results List (section 4.5 - using TestResultPanel) */}
                  <div className="flex-1 overflow-auto p-4 bg-surface">
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
                      <div className="text-center py-8">
                        <p className="text-text-tertiary">No test results available</p>
                      </div>
                    )}
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
