import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useConfirm } from '../components/ConfirmDialog'
import { useNotification } from '../components/NotificationProvider'
import {
  Plus,
  Play,
  Square,
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
  ChevronUp,
  ChevronsUpDown,
  Loader2,
  Terminal,
  History,
  TrendingUp,
  Clock,
  DollarSign,
  Wand2,
  Server,
  Search,
  Zap,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import Wizard from '../components/Wizard'
import BenchmarkModal from '../components/BenchmarkModal'
import Badge from '../components/Badge'
import TestStatusIndicator from '../components/TestStatusIndicator'
import TestResultPanel from '../components/TestResultPanel'
import { useKeyboardShortcuts, useAnnounce } from '../hooks/useKeyboardShortcuts'
import { useTestRun } from '../contexts/TestRunContext'
import { useEditorTheme } from '../hooks/useEditorTheme'
import StreamingLogViewer from '../components/StreamingLogViewer'
import EditorStatusBar from '../components/EditorStatusBar'
import EditorTabStrip from '../components/EditorTabStrip'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

// Parse top-level `provider:` and `model:` declarations from a YAML test
// suite. These are the suite-level overrides that run.py / websocket.py
// already honor server-side — the UI just needs to *show* them so the
// "Using:" badge and the provider dropdown reflect what will actually run.
//
// We scan only the leading lines (before `tests:` or any deeper block),
// matching `key: value` with no indentation. Quoted values are stripped.
// `continue` (not `break`) on indented/nested lines: top-level keys can
// legitimately appear after a multi-line nested block (e.g. a
// `provider_config:` map followed by `tests:`). The `tests:` key always
// terminates the scan since per-test prompts/models live below it; this
// guards against picking up a stray `model:` from inside a test entry.
// Returns { provider: string|null, model: string|null }.
function parseSuiteOverride(content) {
  if (!content) return { provider: null, model: null }
  const out = { provider: null, model: null }
  const lines = content.split('\n')
  for (const line of lines) {
    // Skip nested / indented lines — top-level keys are flush left.
    if (line.startsWith('  ') || line.startsWith('\t') || line.startsWith('-')) continue
    const m = line.match(/^([A-Za-z_][\w]*)\s*:\s*(.*?)\s*(?:#.*)?$/)
    if (!m) continue
    const key = m[1]
    let val = m[2]
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1)
    else if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1)
    if (key === 'provider' && val) out.provider = val
    else if (key === 'model' && val) out.model = val
    // Bail out once we hit `tests:` — anything after is per-test config.
    if (key === 'tests') break
  }
  return out
}

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

// Available evaluator types for the wizard
// Accessible sortable column header. The clickable area is a real <button>
// inside the <th>, so keyboard users can activate it with Enter/Space, and
// the th carries `aria-sort` so assistive tech announces the active sort.
function SortableTH({ sortKey, align = 'left', sort, onSort, children }) {
  const ariaSort =
    sort.key === sortKey ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'
  const alignClass =
    align === 'right' ? 'text-right justify-end' : align === 'center' ? 'text-center justify-center' : 'text-left'
  const indicator =
    sort.key !== sortKey ? (
      <ChevronsUpDown size={10} className="text-text-disabled" />
    ) : sort.dir === 'asc' ? (
      <ChevronUp size={10} className="text-primary" />
    ) : (
      <ChevronDown size={10} className="text-primary" />
    )
  return (
    <th aria-sort={ariaSort} className={`py-0 px-0 text-text-tertiary font-medium ${align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'}`}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={`w-full py-2 px-3 hover:text-text-secondary inline-flex items-center gap-1 ${alignClass}`}
      >
        {children}
        {indicator}
      </button>
    </th>
  )
}

const EVALUATOR_TYPES = [
  { name: 'execution_successful', desc: 'Check that the LLM execution completed without errors', args: [] },
  { name: 'was_mcp_tool_called', desc: 'Check that a specific MCP tool was called', args: [{ key: 'tool_name', label: 'Tool Name', required: true }] },
  { name: 'final_answer_contains', desc: 'Check that the response contains specific text', args: [{ key: 'text', label: 'Expected Text', required: true }, { key: 'case_sensitive', label: 'Case Sensitive', type: 'bool' }] },
  { name: 'tool_called_with_params', desc: 'Check that a tool was called with specific parameters', args: [{ key: 'tool_name', label: 'Tool Name', required: true }, { key: 'params', label: 'Parameters (JSON)', type: 'json' }] },
  { name: 'tool_call_count', desc: 'Check the number of tool calls made', args: [{ key: 'tool_name', label: 'Tool Name', required: true }, { key: 'count', label: 'Expected Count', type: 'number' }] },
  { name: 'within_time_limit', desc: 'Check execution completed within time limit', args: [{ key: 'seconds', label: 'Seconds', type: 'number', required: true }] },
  { name: 'answer_contains_link', desc: 'Check that the response contains a URL/link', args: [] },
  { name: 'sql_query_valid', desc: 'Check that generated SQL is valid', args: [] },
  { name: 'token_usage_reasonable', desc: 'Check token usage is within bounds', args: [{ key: 'max_tokens', label: 'Max Tokens', type: 'number' }] },
]

// Test Case Wizard - guided flow for creating test YAML files
function TestCaseWizard({ onComplete, onCancel }) {
  const [wizardData, setWizardData] = useState({
    // Step 1: File info
    filename: '',
    // Step 2: Tools (optional - for context)
    discoveredTools: [],
    loadingTools: false,
    selectedTools: [],
    // Step 3: Tests
    tests: [{ name: '', prompt: '', evaluators: [{ type: 'execution_successful', args: {} }] }],
    // Step 4: Preview
    yamlPreview: '',
  })

  // Generate YAML from wizard data
  const generateYaml = (data) => {
    let yaml = 'version: "1.0"\ntests:\n'
    for (const test of data.tests) {
      if (!test.name.trim() || !test.prompt.trim()) continue
      yaml += `  - name: ${test.name}\n`
      yaml += `    prompt: "${test.prompt.replace(/"/g, '\\"')}"\n`
      if (test.evaluators.length > 0) {
        yaml += `    evaluators:\n`
        for (const ev of test.evaluators) {
          yaml += `      - name: ${ev.type}\n`
          const evalType = EVALUATOR_TYPES.find(e => e.name === ev.type)
          if (evalType && evalType.args.length > 0) {
            const hasArgs = Object.entries(ev.args || {}).some(([, v]) => v !== '' && v !== undefined)
            if (hasArgs) {
              yaml += `        args:\n`
              for (const [key, value] of Object.entries(ev.args || {})) {
                if (value !== '' && value !== undefined) {
                  // Handle different types
                  if (typeof value === 'number' || value === 'true' || value === 'false') {
                    yaml += `          ${key}: ${value}\n`
                  } else {
                    yaml += `          ${key}: "${value}"\n`
                  }
                }
              }
            }
          }
        }
      }
    }
    return yaml
  }

  const steps = [
    {
      label: 'Setup',
      validate: (data) => {
        if (!data.filename.trim()) return 'File name is required'
        return true
      },
      component: ({ data, setData }) => (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Test File Name</label>
            <input
              type="text"
              value={data.filename}
              onChange={(e) => setData(prev => ({ ...prev, filename: e.target.value }))}
              className="input w-full"
              placeholder="e.g., my_tool_tests.yaml"
              autoFocus
            />
            <p className="text-text-tertiary text-xs mt-1">.yaml extension will be added automatically if missing</p>
          </div>
        </div>
      ),
    },
    {
      label: 'Write Tests',
      validate: (data) => {
        const validTests = data.tests.filter(t => t.name.trim() && t.prompt.trim())
        if (validTests.length === 0) return 'Add at least one test with a name and prompt'
        return true
      },
      component: ({ data, setData }) => (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Define your test cases. Each test needs a name, a prompt for the LLM, and evaluators to check the result.
          </p>

          {data.tests.map((test, testIdx) => (
            <div key={testIdx} className="bg-surface rounded-lg p-4 border border-border space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-tertiary">Test {testIdx + 1}</span>
                {data.tests.length > 1 && (
                  <button
                    type="button"
                    onClick={() => {
                      setData(prev => ({
                        ...prev,
                        tests: prev.tests.filter((_, i) => i !== testIdx)
                      }))
                    }}
                    className="p-1 hover:bg-error/20 rounded text-error"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium mb-1">Test Name</label>
                <input
                  type="text"
                  value={test.name}
                  onChange={(e) => {
                    const newTests = [...data.tests]
                    newTests[testIdx] = { ...test, name: e.target.value }
                    setData(prev => ({ ...prev, tests: newTests }))
                  }}
                  className="input w-full text-sm"
                  placeholder="e.g., list_dashboards_basic"
                />
              </div>

              <div>
                <label className="block text-xs font-medium mb-1">Prompt</label>
                <textarea
                  value={test.prompt}
                  onChange={(e) => {
                    const newTests = [...data.tests]
                    newTests[testIdx] = { ...test, prompt: e.target.value }
                    setData(prev => ({ ...prev, tests: newTests }))
                  }}
                  className="input w-full text-sm"
                  rows={2}
                  placeholder="e.g., List all dashboards and show their titles"
                />
              </div>

              <div>
                <label className="block text-xs font-medium mb-1">Evaluators</label>
                <div className="space-y-2">
                  {test.evaluators.map((ev, evIdx) => (
                    <div key={evIdx} className="flex items-start gap-2">
                      <select
                        value={ev.type}
                        onChange={(e) => {
                          const newTests = [...data.tests]
                          newTests[testIdx].evaluators[evIdx] = { type: e.target.value, args: {} }
                          setData(prev => ({ ...prev, tests: newTests }))
                        }}
                        className="input text-xs flex-1"
                      >
                        {EVALUATOR_TYPES.map(et => (
                          <option key={et.name} value={et.name}>{et.name}</option>
                        ))}
                      </select>

                      {/* Show args for evaluators that need them */}
                      {EVALUATOR_TYPES.find(et => et.name === ev.type)?.args.map(arg => (
                        <input
                          key={arg.key}
                          type={arg.type === 'number' ? 'number' : 'text'}
                          value={ev.args?.[arg.key] || ''}
                          onChange={(e) => {
                            const newTests = [...data.tests]
                            newTests[testIdx].evaluators[evIdx] = {
                              ...ev,
                              args: { ...ev.args, [arg.key]: e.target.value }
                            }
                            setData(prev => ({ ...prev, tests: newTests }))
                          }}
                          className="input text-xs w-32"
                          placeholder={arg.label}
                        />
                      ))}

                      <button
                        type="button"
                        onClick={() => {
                          const newTests = [...data.tests]
                          newTests[testIdx].evaluators = test.evaluators.filter((_, i) => i !== evIdx)
                          setData(prev => ({ ...prev, tests: newTests }))
                        }}
                        className="p-1 hover:bg-error/20 rounded text-error flex-shrink-0"
                        aria-label="Remove evaluator"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}

                  <button
                    type="button"
                    onClick={() => {
                      const newTests = [...data.tests]
                      newTests[testIdx].evaluators = [
                        ...test.evaluators,
                        { type: 'execution_successful', args: {} }
                      ]
                      setData(prev => ({ ...prev, tests: newTests }))
                    }}
                    className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
                  >
                    <Plus size={12} /> Add Evaluator
                  </button>
                </div>
              </div>
            </div>
          ))}

          <button
            type="button"
            onClick={() => {
              setData(prev => ({
                ...prev,
                tests: [
                  ...prev.tests,
                  { name: '', prompt: '', evaluators: [{ type: 'execution_successful', args: {} }] }
                ]
              }))
            }}
            className="w-full p-3 border-2 border-dashed border-border rounded-lg hover:border-primary hover:bg-primary/5 transition-all flex items-center justify-center gap-2 text-text-secondary hover:text-primary text-sm"
          >
            <Plus size={14} /> Add Another Test
          </button>
        </div>
      ),
    },
    {
      label: 'Preview & Save',
      component: ({ data, setData }) => {
        const yaml = generateYaml(data)
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-text-secondary">Generated YAML:</h4>
            <div className="bg-surface rounded-lg border border-border overflow-hidden">
              <pre className="p-4 text-xs font-mono overflow-auto max-h-[400px] text-text-primary">
                {yaml}
              </pre>
            </div>
            <p className="text-xs text-text-tertiary">
              This will create <code className="bg-surface px-1 rounded">{data.filename.endsWith('.yaml') ? data.filename : `${data.filename}.yaml`}</code> in your tests directory.
              You can edit it afterwards in the editor.
            </p>
          </div>
        )
      },
    },
  ]

  const handleComplete = (data) => {
    const yaml = generateYaml(data)
    const filename = data.filename.endsWith('.yaml') ? data.filename : `${data.filename}.yaml`
    onComplete(filename, yaml)
  }

  return (
    <Wizard
      title="Create Test Case"
      steps={steps}
      data={wizardData}
      setData={setWizardData}
      onComplete={handleComplete}
      onCancel={onCancel}
    />
  )
}

function TestManager({ selectedProfiles = [], selectedLlmProfile = null, llmProfiles = [] }) {
  const [confirmAction, confirmElement] = useConfirm()
  const { success: notifySuccess, error: notifyError, warning: notifyWarning, info: notifyInfo } = useNotification()
  const { monacoTheme } = useEditorTheme()
  // Get test run state from context (persists across navigation)
  const {
    running,
    runningTestName,
    testResults,
    streamingLogs,
    runningTests,
    testStatuses,
    activeTestFile,
    pinnedHistoryRun,
    runTests: contextRunTests,
    runSingleTest: contextRunSingleTest,
    runDirectory: contextRunDirectory,
    stopTests,
    clearLogs,
    clearResults,
    resetTestStatuses,
    setTestStatuses,
    setTestResults,
    setPinnedHistoryRun,
    setRunning,
    setRunningTests,
    directoryRunProgress,
    setDirectoryRunProgress,
    currentRunId,
    stopping,
    connectionState,
    attachToRun,
  } = useTestRun()

  // Local UI state (doesn't need to persist)
  const [testData, setTestData] = useState({ folders: {}, files: [] })
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [selectedFile, setSelectedFile] = useState(null)
  const [showBench, setShowBench] = useState(false)
  const [fileContent, setFileContent] = useState('')
  const [editMode, setEditMode] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [showNewFileDialog, setShowNewFileDialog] = useState(false)
  const [testLocations, setTestLocations] = useState([])
  // Editor cursor position for the IDE-style status bar (1-based to match Monaco).
  const [editorCursor, setEditorCursor] = useState({ line: 1, column: 1 })
  // Persisted Monaco view options exposed via the status bar.
  const [editorWordWrap, setEditorWordWrap] = useState(() => {
    return localStorage.getItem('testManagerEditorWordWrap') === '1'
  })
  const [editorMinimap, setEditorMinimap] = useState(() => {
    return localStorage.getItem('testManagerEditorMinimap') === '1'
  })
  // Below md, strip Monaco chrome (minimap, line numbers, gutters) so the
  // code area keeps usable width on phones.
  const [isNarrowViewport, setIsNarrowViewport] = useState(() =>
    typeof window !== 'undefined' ? !window.matchMedia('(min-width: 768px)').matches : false
  )
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const onChange = (e) => setIsNarrowViewport(!e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  const editorRef = useRef(null)
  const monacoRef = useRef(null)
  const testLocationsRef = useRef([]) // Ref to avoid stale closure in click handler
  const logsEndRef = useRef(null)
  const [testProfiles, setTestProfiles] = useState([])
  const [selectedTestProfile, setSelectedTestProfile] = useState(null)
  const [runAllLlmsMode, setRunAllLlmsMode] = useState(false)
  const [allLlmsResults, setAllLlmsResults] = useState(null) // results from running all LLMs
  // directoryRunProgress moved to TestRunContext (SC-108184) so a reload
  // mid-batch can reattach via the persisted currentRunId.
  const [resultsHistory, setResultsHistory] = useState([])
  const [expandedRunId, setExpandedRunId] = useState(null)
  const [expandedRunDetails, setExpandedRunDetails] = useState({})
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [historyFilterQuery, setHistoryFilterQuery] = useState('')
  const [historyProviderFilter, setHistoryProviderFilter] = useState(null) // null = all
  const [historyFailedOnly, setHistoryFailedOnly] = useState(false)
  const [historySort, setHistorySort] = useState({ key: 'timestamp', dir: 'desc' })
  const [selectedRunIds, setSelectedRunIds] = useState(new Set())
  const [historySelectMode, setHistorySelectMode] = useState(false)
  const [bottomPanelTab, setBottomPanelTab] = useState('logs') // 'logs' or 'results'
  const [showFileTree, setShowFileTree] = useState(false)
  const [showTestWizard, setShowTestWizard] = useState(false)
  const [bottomPanelHeight, setBottomPanelHeight] = useState(() => {
    const saved = localStorage.getItem('testManagerPanelHeight')
    return saved ? Number(saved) : 280
  })
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('testManagerSidebarWidth')
    return saved ? Number(saved) : 300
  })
  const containerRef = useRef(null)  // inner editor/panel split container (used by bottom-panel drag)
  const sidebarRef = useRef(null)
  const overlayRef = useRef(null)
  const rafRef = useRef(null)

  // Show/hide the drag overlay via DOM — zero React re-renders
  const showOverlay = (cursor) => {
    if (overlayRef.current) {
      overlayRef.current.style.display = 'block'
      overlayRef.current.style.cursor = cursor
    }
    document.body.style.cursor = cursor
    document.body.style.userSelect = 'none'
  }
  const hideOverlay = () => {
    if (overlayRef.current) overlayRef.current.style.display = 'none'
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  // Mouse or touch coordinates from any pointer event
  const pointerXY = (e) => {
    const p = e.touches?.[0] ?? e.changedTouches?.[0] ?? e
    return { x: p.clientX, y: p.clientY }
  }

  // Bottom panel drag — pure DOM, no setState during drag (mouse + touch)
  const handleDragStart = useCallback((e) => {
    e.preventDefault()
    showOverlay('row-resize')
    const panelEl = containerRef.current?.querySelector('[data-bottom-panel]')
    let currentHeight = bottomPanelHeight

    const onMove = (e) => {
      const { y } = pointerXY(e)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        if (!containerRef.current) return
        const rect = containerRef.current.getBoundingClientRect()
        const h = Math.min(Math.max(rect.bottom - y, 80), rect.height * 0.8)
        currentHeight = h
        if (panelEl) panelEl.style.height = `${h}px`
      })
    }

    const onUp = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      hideOverlay()
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('touchmove', onMove)
      document.removeEventListener('touchend', onUp)
      setBottomPanelHeight(currentHeight)
      localStorage.setItem('testManagerPanelHeight', String(currentHeight))
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.addEventListener('touchmove', onMove, { passive: false })
    document.addEventListener('touchend', onUp)
  }, [bottomPanelHeight])

  // Sidebar drag — pure DOM, no setState during drag (mouse + touch)
  const handleSidebarDragStart = useCallback((e) => {
    e.preventDefault()
    showOverlay('col-resize')
    const sidebarEl = sidebarRef.current
    // Capture sidebar's left edge once at drag start (it doesn't move during drag).
    const sidebarLeft = sidebarEl?.getBoundingClientRect().left ?? 0
    let currentWidth = sidebarWidth

    const onMove = (e) => {
      const { x } = pointerXY(e)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        const w = Math.min(Math.max(x - sidebarLeft, 180), 600)
        currentWidth = w
        if (sidebarEl) sidebarEl.style.width = `${w}px`
      })
    }

    const onUp = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      hideOverlay()
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('touchmove', onMove)
      document.removeEventListener('touchend', onUp)
      setSidebarWidth(currentWidth)
      localStorage.setItem('testManagerSidebarWidth', String(currentWidth))
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.addEventListener('touchmove', onMove, { passive: false })
    document.addEventListener('touchend', onUp)
  }, [sidebarWidth])

  useEffect(() => {
    loadTestFiles()
    loadTestProfiles()
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

  // Derive MCP profile from global selectedProfiles prop
  // selectedProfiles is an array of "profile_id:mcp_name" strings
  const selectedMcpProfile = selectedProfiles.length > 0 ? selectedProfiles[0] : null

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

  // Sequencing for history-pin fetches. We track the latest pin request id
  // and abort the previous in-flight fetch on every new click, so a slow
  // earlier response can't win the race and pin the wrong run. Also re-checks
  // `running` AFTER the await: if a new run started during the fetch, drop
  // the response on the floor instead of stomping the live results.
  const pinFetchRef = useRef({ id: 0, controller: null })
  const pinHistoryRun = async (runId) => {
    if (!runId || running) return
    if (pinFetchRef.current.controller) {
      pinFetchRef.current.controller.abort()
    }
    const myId = ++pinFetchRef.current.id
    const controller = new AbortController()
    pinFetchRef.current.controller = controller
    try {
      const res = await fetch(`/api/results/run/${encodeURIComponent(runId)}`, {
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      // A newer pin click superseded us, OR a live run started while we were
      // fetching — either way, abandon this response.
      if (myId !== pinFetchRef.current.id || running) return
      setPinnedHistoryRun(data)
      setBottomPanelTab('results')
    } catch (error) {
      if (error.name === 'AbortError') return
      console.error('Failed to load historical run:', error)
    }
  }

  // Unique providers across all history runs — drives the provider chip filter.
  const historyProviders = useMemo(
    () => Array.from(new Set(resultsHistory.map((r) => r.provider).filter(Boolean))).sort(),
    [resultsHistory],
  )

  // Auto-clear a stale provider filter when switching to a file whose history
  // doesn't contain the previously-selected provider. Otherwise the chip
  // disappears (provider chips only render for providers in the current
  // history) but the filter stays applied, leaving the table mysteriously
  // empty with no UI to clear it.
  useEffect(() => {
    if (historyProviderFilter && !historyProviders.includes(historyProviderFilter)) {
      setHistoryProviderFilter(null)
    }
  }, [historyProviders, historyProviderFilter])

  // History view derives a filtered + sorted view; the source array is left
  // untouched so the chart can still slice the most recent untouched runs if
  // we want to switch back later.
  const filteredHistory = useMemo(() => {
    const q = historyFilterQuery.trim().toLowerCase()
    const filtered = resultsHistory.filter((run) => {
      if (historyProviderFilter && run.provider !== historyProviderFilter) return false
      if (historyFailedOnly && (run.failed ?? 0) === 0) return false
      if (q) {
        const hay = `${run.provider || ''} ${run.model || ''} ${run.run_id || ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
    const dir = historySort.dir === 'asc' ? 1 : -1
    const cmp = (a, b) => {
      switch (historySort.key) {
        case 'pass':
          return ((a.pass_rate ?? 0) - (b.pass_rate ?? 0)) * dir
        case 'cost':
          return ((a.total_cost ?? 0) - (b.total_cost ?? 0)) * dir
        case 'duration':
          return ((a.total_duration ?? 0) - (b.total_duration ?? 0)) * dir
        case 'timestamp':
        default:
          return (new Date(a.timestamp) - new Date(b.timestamp)) * dir
      }
    }
    return [...filtered].sort(cmp)
  }, [resultsHistory, historyFilterQuery, historyProviderFilter, historyFailedOnly, historySort])

  // Dashboard metrics computed from history — no extra API call needed
  const dashboardData = useMemo(() => {
    if (!resultsHistory.length) return { chartData: [], stats: null, modelBreakdown: [] }
    const chrono = [...resultsHistory].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
    const last20 = chrono.slice(-20)
    const chartData = last20.map(r => ({
      date: r.timestamp ? r.timestamp.slice(5, 10) : '',
      pass_rate: Math.round((r.pass_rate ?? 0) * 100),
      cost: parseFloat((r.total_cost ?? 0).toFixed(4)),
      duration: parseFloat((r.total_duration ?? 0).toFixed(1)),
    }))
    const n = resultsHistory.length
    const avgPassRate = Math.round(resultsHistory.reduce((s, r) => s + (r.pass_rate ?? 0), 0) / n * 100)
    const avgCost = resultsHistory.reduce((s, r) => s + (r.total_cost ?? 0), 0) / n
    const modelMap = {}
    for (const r of resultsHistory) {
      const key = `${r.provider}||${r.model}`
      if (!modelMap[key]) modelMap[key] = { provider: r.provider, model: r.model, runs: 0, totalPass: 0, totalCost: 0 }
      modelMap[key].runs++
      modelMap[key].totalPass += (r.pass_rate ?? 0)
      modelMap[key].totalCost += (r.total_cost ?? 0)
    }
    const modelBreakdown = Object.values(modelMap).map(m => ({
      provider: m.provider,
      model: m.model,
      runs: m.runs,
      avgPassRate: Math.round(m.totalPass / m.runs * 100),
      avgCost: m.totalCost / m.runs,
    })).sort((a, b) => b.runs - a.runs)
    return { chartData, stats: { totalRuns: n, avgPassRate, avgCost }, modelBreakdown }
  }, [resultsHistory])

  // Expand a history row inline, fetching full run details on demand
  const expandRunDetails = async (runId) => {
    if (expandedRunId === runId) { setExpandedRunId(null); return }
    setExpandedRunId(runId)
    if (!expandedRunDetails[runId]) {
      setLoadingRunId(runId)
      try {
        const res = await fetch(`/api/results/run/${encodeURIComponent(runId)}`)
        if (res.ok) {
          const data = await res.json()
          setExpandedRunDetails(prev => ({ ...prev, [runId]: data }))
        }
      } catch (e) {
        console.error('Failed to load run details', e)
      } finally {
        setLoadingRunId(null)
      }
    }
  }

  const toggleHistorySort = (key) => {
    setHistorySort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: key === 'timestamp' ? 'desc' : 'asc' },
    )
  }
  const SortIcon = ({ k }) => {
    if (historySort.key !== k) return <ChevronsUpDown size={10} className="text-text-disabled" />
    return historySort.dir === 'asc' ? (
      <ChevronUp size={10} className="text-primary" />
    ) : (
      <ChevronDown size={10} className="text-primary" />
    )
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

  // Get model and provider from selected LLM provider — with suite-level
  // override applied. If the open YAML file declares `provider:` / `model:`
  // at the top level, those win over the LLM profile default. The server
  // already honors suite-level overrides; this keeps the UI honest about
  // what will actually run (e.g. chatbot YAML → `assistant` provider, not
  // whatever the LLM profile defaults to).
  const getLlmConfig = () => {
    const suite = parseSuiteOverride(fileContent)
    // Defaults match what the Python config layer uses when nothing is
    // configured (keep these in sync with config.default_model / default_provider).
    let model = 'claude-sonnet-4-6'
    let provider = 'claude-sdk'
    if (selectedLlmProfile && llmProfiles.length > 0) {
      const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
      if (profile && profile.providers && profile.providers.length > 0) {
        const defaultProvider = profile.providers.find(p => p.default) || profile.providers[0]
        model = defaultProvider.model || model
        provider = defaultProvider.provider || provider
      }
    }
    return {
      model: suite.model || model,
      provider: suite.provider || provider,
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

    // Track cursor position for the status bar.
    editor.onDidChangeCursorPosition((e) => {
      setEditorCursor({ line: e.position.lineNumber, column: e.position.column })
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
    contextRunSingleTest(testName, testFile, selectedFile.path, llmConfig, selectedMcpProfile, selectedLlmProfile)
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
      notifySuccess('File saved successfully')
    } catch (error) {
      console.error('Failed to save test file:', error)
      notifyError(`Failed to save file: ${error.message}`)
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
      notifyError('Failed to create file')
    }
  }

  const deleteTestFile = async (relativePath) => {
    if (!(await confirmAction({ title: 'Delete file', message: `Delete ${relativePath}?` }))) return

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
      notifyError('Failed to delete file')
    }
  }

  const runTests = async () => {
    if (!selectedFile) return
    const llmConfig = getLlmConfig()
    const testFile = selectedFile.relative_path || selectedFile.filename
    contextRunTests(testFile, selectedFile.path, llmConfig, selectedMcpProfile, testLocations, selectedLlmProfile)
    setBottomPanelTab('logs') // Show logs while running
  }

  const runAllInDirectory = async (folderName, files) => {
    if (running || directoryRunProgress || !files || files.length === 0) return
    const llmConfig = getLlmConfig()
    // Surface the Logs tab immediately — the WS stream lands per-file
    // logs there as the batch progresses.
    setBottomPanelTab('logs')
    // Delegate to the context's WS-based directory runner (SC-108184).
    // Pre-fix this issued sequential HTTP POSTs with no streaming and
    // ended in an alert() box; now logs flow naturally through the
    // Logs tab and a reload mid-batch can reattach to the same run.
    await contextRunDirectory(
      folderName,
      files,
      llmConfig,
      selectedMcpProfile,
      selectedLlmProfile,
    )
  }

  // Auto-switch to dashboard when a new file is selected (not mid-run)
  useEffect(() => {
    if (selectedFile && !running) {
      setBottomPanelTab('dashboard')
      setExpandedRunId(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFile?.relative_path, selectedFile?.filename])

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
      notifyWarning('No LLM providers configured')
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
      {confirmElement}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden min-h-0 relative">
        {/* Permanent overlay — shown/hidden via ref during drag to prevent Monaco from stealing mouse events. Never triggers React re-render. */}
        <div ref={overlayRef} className="absolute inset-0 z-30" style={{ display: 'none' }} />
        {/* File List Sidebar — resizable */}
        <div
          ref={sidebarRef}
          data-sidebar
          className={`flex-shrink-0 border-b md:border-b-0 md:border-r border-border ${showFileTree ? 'flex flex-col' : 'hidden'} md:flex md:flex-col bg-surface-elevated overflow-hidden max-h-[40vh] md:max-h-none`}
          style={{ width: typeof window !== 'undefined' && window.innerWidth >= 768 ? sidebarWidth : '100%' }}
        >
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base md:text-lg font-semibold text-text-primary">Test Files</h2>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowTestWizard(true)}
                  className="p-2 hover:bg-surface-hover rounded-lg transition-all duration-200 text-primary hover:text-primary/80"
                  title="Create test (Wizard)"
                >
                  <Wand2 size={18} />
                </button>
                <button
                  onClick={() => setShowNewFileDialog(true)}
                  className="p-2 hover:bg-surface-hover rounded-lg transition-all duration-200 text-text-secondary hover:text-text-primary"
                  title="Create new test file"
                >
                  <Plus size={20} />
                </button>
              </div>
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
                  aria-label="Close dialog"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {/* Root files */}
          {testData.files && [...testData.files].sort((a, b) =>
            (a.filename || a.relative_path || '').localeCompare(b.filename || b.relative_path || '', undefined, { numeric: true })
          ).map((file) => (
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
                  <span title={file.relative_path || file.filename} className={`font-medium truncate ${
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
          {testData.folders && Object.entries(testData.folders)
            .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
            .map(([folderName, files]) => (
            <div key={folderName} className="border-b border-border">
              {/* Folder Header */}
              <div
                className="p-4 cursor-pointer hover:bg-surface-hover transition-all duration-200 flex items-center gap-2 group/folder"
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
                {directoryRunProgress?.folder === folderName ? (
                  <Badge variant="warning" size="xs" className="font-medium">
                    <Loader2 size={10} className="animate-spin" />
                    {directoryRunProgress.current}/{directoryRunProgress.total}
                  </Badge>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      runAllInDirectory(folderName, files)
                    }}
                    className="p-1 hover:bg-primary/20 rounded transition-all duration-200 opacity-0 group-hover/folder:opacity-100 text-primary disabled:opacity-30 disabled:cursor-not-allowed"
                    title={directoryRunProgress ? 'A directory run is already in progress' : `Run all tests in ${folderName}`}
                    disabled={running || !!directoryRunProgress}
                  >
                    <Play size={12} />
                  </button>
                )}
              </div>

              {/* Folder Files */}
              {expandedFolders.has(folderName) && [...files].sort((a, b) =>
                (a.filename || '').localeCompare(b.filename || '', undefined, { numeric: true })
              ).map((file) => (
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
                      <span title={file.relative_path || file.filename} className={`text-sm truncate ${
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

        {/* Sidebar resize handle */}
        <div
          className="hidden md:flex w-1.5 flex-shrink-0 cursor-col-resize bg-transparent hover:bg-primary/30 active:bg-primary/50 transition-colors items-center justify-center group"
          onMouseDown={handleSidebarDragStart}
          onTouchStart={handleSidebarDragStart}
          title="Drag to resize"
        >
          <div className="w-0.5 h-8 bg-border group-hover:bg-primary/50 rounded-full transition-colors" />
        </div>

        {/* Mobile file tree toggle */}
        <button onClick={() => setShowFileTree(!showFileTree)} className="md:hidden flex items-center gap-2 px-3 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-hover border-b border-border w-full">
          <Folder size={16} />
          <span>{showFileTree ? 'Hide Files' : 'Show Files'}</span>
        </button>

        {/* Editor & Results - inside main flex container, sibling to sidebar */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {selectedFile ? (
          <>
            {/* Editor Header - fixed height, won't shrink */}
            <div className="flex-shrink-0 border-b border-border bg-surface-elevated">
              {/* Tab strip: file as a tab + edit controls on the right */}
              <EditorTabStrip
                filename={selectedFile.filename}
                pathSubtitle={selectedFile.relative_path || selectedFile.filename}
                testCount={testLocations.length}
                dirty={editMode && fileContent !== selectedFile.content}
                onClose={async () => {
                  // Confirm before discarding unsaved edits — closing the tab
                  // shouldn't silently lose user work.
                  const dirty = editMode && fileContent !== selectedFile.content
                  if (dirty && !(await confirmAction({ title: 'Unsaved changes', message: 'You have unsaved changes. Close anyway?', confirmLabel: 'Close anyway' }))) {
                    return
                  }
                  setSelectedFile(null)
                  setEditMode(false)
                  setFileContent('')
                  localStorage.removeItem('selectedTestFile')
                }}
                rightSlot={
                  editMode ? (
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
                  )
                }
              />

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
                  <button
                    onClick={() => setShowBench(true)}
                    disabled={running || !selectedFile}
                    className="btn btn-secondary text-sm"
                    title="Benchmark this test across models × providers × profiles × repeats"
                  >
                    <Zap size={14} />
                    <span>Benchmark</span>
                  </button>
                  {/* Stop is visible whenever:
                      - a run is live (running=true), OR
                      - a directory batch is in progress (the v0.7.21 batch
                        runner sets directoryRunProgress and keeps going
                        server-side even when a per-file error flipped
                        running=false), OR
                      - we're in the transient "Stopping…" state.
                      Disabled while stopping so the user can't double-fire
                      the stop request. SC-108217. */}
                  {!runAllLlmsMode && (running || directoryRunProgress || stopping) && (
                    <button
                      onClick={stopTests}
                      disabled={stopping}
                      className={`btn text-sm ${stopping ? 'btn-secondary' : 'btn-error'}`}
                      title={stopping ? 'Server is cancelling the run…' : 'Stop the current test run'}
                    >
                      <Square size={14} fill="currentColor" />
                      <span>{stopping ? 'Stopping…' : 'Stop'}</span>
                    </button>
                  )}
                </div>

                {selectedLlmProfile && llmProfiles.length > 0 && (() => {
                  const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
                  const defaultProv = profile?.providers?.find(p => p.default) || profile?.providers?.[0]
                  if (!defaultProv) return null
                  // Suite-level override (declared at the top of the YAML) wins
                  // over the LLM profile default — show that so the user isn't
                  // surprised when a chatbot YAML actually runs against the
                  // assistant provider regardless of which LLM profile is active.
                  const suite = parseSuiteOverride(fileContent)
                  const effectiveModel = suite.model || defaultProv.model
                  const effectiveProvider = suite.provider || defaultProv.provider
                  const overridden = !!(suite.provider || suite.model)
                  // Chatbot YAMLs declare `model: default` to mean "let the
                  // server pick" — rendering the literal string "default" as
                  // a model name reads like a bug. Show a friendlier label
                  // (italic, lowercased) so the user can tell it's a sentinel.
                  const modelIsSentinel = effectiveModel === 'default'
                  return (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-text-tertiary">Using:</span>
                      <span
                        className={`px-2 py-1 rounded bg-surface-elevated border border-border font-mono ${
                          modelIsSentinel ? 'italic text-text-tertiary' : 'text-text-secondary'
                        }`}
                        title={modelIsSentinel ? 'YAML declares model: default — the chatbot endpoint picks the actual model.' : effectiveModel}
                      >
                        {modelIsSentinel ? 'provider default' : effectiveModel}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-blue-500/20 text-blue-400">
                        {effectiveProvider}
                      </span>
                      {overridden && (
                        <span
                          title="This test file declares provider/model at the top level — that override is being used instead of the LLM profile default."
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                        >
                          suite override
                        </span>
                      )}
                    </div>
                  )
                })()}
              </div>
            </div>

            {/* Split view: Editor + Bottom Panel */}
            <div ref={containerRef} className="flex-1 flex flex-col overflow-hidden relative min-h-0">
              {/* Editor area - always takes remaining space; column-flex so the
                  status bar sits flush below Monaco without re-flowing on resize.
                  In edit mode the warning-tinted left border makes it obvious the
                  buffer is mutable (paired with the EDIT badge in the status bar). */}
              <div
                className={`flex-1 flex flex-col overflow-hidden min-h-0 min-h-[250px] border-l-2 transition-colors ${
                  editMode ? 'border-warning/60' : 'border-transparent'
                }`}
              >
                <div className="flex-1 min-h-0">
                  <Editor
                    height="100%"
                    defaultLanguage="yaml"
                    theme={monacoTheme}
                    value={fileContent}
                    onChange={(value) => setFileContent(value || '')}
                    onMount={handleEditorDidMount}
                    options={{
                      readOnly: !editMode,
                      minimap: { enabled: editorMinimap && !isNarrowViewport },
                      wordWrap: isNarrowViewport ? 'on' : editorWordWrap ? 'on' : 'off',
                      fontSize: 14,
                      lineNumbers: isNarrowViewport ? 'off' : 'on',
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      glyphMargin: !isNarrowViewport,
                      folding: !isNarrowViewport,
                      lineDecorationsWidth: isNarrowViewport ? 2 : 5,
                    }}
                  />
                </div>
                <EditorStatusBar
                  line={editorCursor.line}
                  column={editorCursor.column}
                  language="YAML"
                  editMode={editMode}
                  dirty={editMode && fileContent !== selectedFile.content}
                  wordWrap={editorWordWrap}
                  onToggleWordWrap={() => {
                    setEditorWordWrap((v) => {
                      localStorage.setItem('testManagerEditorWordWrap', v ? '0' : '1')
                      return !v
                    })
                  }}
                  minimap={editorMinimap}
                  onToggleMinimap={() => {
                    setEditorMinimap((v) => {
                      localStorage.setItem('testManagerEditorMinimap', v ? '0' : '1')
                      return !v
                    })
                  }}
                />
              </div>

              {/* Bottom Panel - always visible when a file is open */}
              {(running || streamingLogs.length > 0 || testResults || pinnedHistoryRun || resultsHistory.length > 0 || true) && (
                <>
                {/* Drag handle */}
                <div
                  onMouseDown={handleDragStart}
                  onTouchStart={handleDragStart}
                  className="h-2.5 md:h-1.5 flex-shrink-0 cursor-row-resize bg-border hover:bg-primary/40 transition-colors group flex items-center justify-center touch-none"
                >
                  <div className="w-8 h-0.5 rounded-full bg-text-disabled group-hover:bg-primary transition-colors" />
                </div>
                <div data-bottom-panel className="flex-shrink-0 flex flex-col bg-surface" style={{ height: bottomPanelHeight }}>
                  {/* Tab Bar */}
                  <div className="flex items-center border-b border-border bg-surface-elevated px-2 sticky top-0 z-10">
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
                    {/* Results Tab — backed by either the live run or a pinned history run */}
                    {(pinnedHistoryRun || testResults) && (() => {
                      const displayResults = pinnedHistoryRun || testResults
                      return (
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
                            displayResults.summary.failed > 0 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'
                          }`}>
                            {displayResults.summary.passed}/{displayResults.summary.total}
                          </span>
                        </button>
                      )
                    })()}
                    {/* Dashboard Tab */}
                    <button
                      className={`px-3 py-2 text-xs font-medium flex items-center gap-2 border-b-2 transition-colors ${
                        bottomPanelTab === 'dashboard'
                          ? 'border-primary text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`}
                      onClick={() => setBottomPanelTab('dashboard')}
                    >
                      <TrendingUp size={12} />
                      <span>Dashboard</span>
                      {resultsHistory.length > 0 && (
                        <span className="px-1.5 py-0.5 rounded bg-surface text-[10px]">{resultsHistory.length}</span>
                      )}
                    </button>
                    {/* History Tab */}
                    <button
                      className={`px-3 py-2 text-xs font-medium flex items-center gap-2 border-b-2 transition-colors ${
                        bottomPanelTab === 'history'
                          ? 'border-primary text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`}
                      onClick={() => setBottomPanelTab('history')}
                    >
                      <History size={12} />
                      <span>History</span>
                      {resultsHistory.length > 0 && (
                        <span className="px-1.5 py-0.5 rounded bg-surface text-[10px]">{resultsHistory.length}</span>
                      )}
                    </button>
                    {/* Spacer */}
                    <div className="flex-1" />
                    {/* Clear logs button */}
                    {bottomPanelTab === 'logs' && !running && streamingLogs.length > 0 && (
                      <button
                        onClick={clearLogs}
                        className="px-2 py-1 text-xs text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
                      >
                        Clear
                      </button>
                    )}
                  </div>

                  {/* Panel Content */}
                  <div className="flex-1 overflow-hidden">
                    {/* Dashboard Tab */}
                    {bottomPanelTab === 'dashboard' && (
                      <div className="h-full overflow-auto p-4">
                        {!dashboardData.stats ? (
                          <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
                            No run history yet — run this test file to see insights here.
                          </div>
                        ) : (
                          <div className="space-y-4">
                            {/* Stats row */}
                            <div className="grid grid-cols-3 gap-3">
                              <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                                <div className="text-xs text-text-tertiary mb-1">Total Runs</div>
                                <div className="text-xl font-bold text-text-primary">{dashboardData.stats.totalRuns}</div>
                              </div>
                              <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                                <div className="text-xs text-text-tertiary mb-1">Avg Pass Rate</div>
                                <div className={`text-xl font-bold ${dashboardData.stats.avgPassRate >= 80 ? 'text-green-400' : dashboardData.stats.avgPassRate >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                                  {dashboardData.stats.avgPassRate}%
                                </div>
                              </div>
                              <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                                <div className="text-xs text-text-tertiary mb-1">Avg Cost/Run</div>
                                <div className="text-xl font-bold text-text-primary font-mono">${dashboardData.stats.avgCost.toFixed(4)}</div>
                              </div>
                            </div>

                            {/* Pass Rate chart */}
                            <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                              <div className="text-xs font-medium text-text-secondary mb-2">Pass Rate Over Time (last 20 runs)</div>
                              <ResponsiveContainer width="100%" height={120}>
                                <LineChart data={dashboardData.chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="rgba(255,255,255,0.2)" />
                                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="rgba(255,255,255,0.2)" />
                                  <Tooltip
                                    contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, fontSize: 11 }}
                                    formatter={(v) => [`${v}%`, 'Pass Rate']}
                                  />
                                  <Line type="monotone" dataKey="pass_rate" stroke="#4ade80" strokeWidth={2} dot={{ r: 3, fill: '#4ade80' }} />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>

                            {/* Cost + Duration charts */}
                            <div className="grid grid-cols-2 gap-3">
                              <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                                <div className="text-xs font-medium text-text-secondary mb-2">Cost per Run ($)</div>
                                <ResponsiveContainer width="100%" height={90}>
                                  <BarChart data={dashboardData.chartData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                                    <XAxis dataKey="date" tick={{ fontSize: 9 }} stroke="rgba(255,255,255,0.2)" />
                                    <YAxis tick={{ fontSize: 9 }} stroke="rgba(255,255,255,0.2)" />
                                    <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, fontSize: 11 }} formatter={(v) => [`$${v}`, 'Cost']} />
                                    <Bar dataKey="cost" fill="#60a5fa" radius={[2, 2, 0, 0]} />
                                  </BarChart>
                                </ResponsiveContainer>
                              </div>
                              <div className="bg-surface-elevated rounded-lg p-3 border border-border">
                                <div className="text-xs font-medium text-text-secondary mb-2">Duration per Run (s)</div>
                                <ResponsiveContainer width="100%" height={90}>
                                  <BarChart data={dashboardData.chartData} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
                                    <XAxis dataKey="date" tick={{ fontSize: 9 }} stroke="rgba(255,255,255,0.2)" />
                                    <YAxis tick={{ fontSize: 9 }} stroke="rgba(255,255,255,0.2)" />
                                    <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, fontSize: 11 }} formatter={(v) => [`${v}s`, 'Duration']} />
                                    <Bar dataKey="duration" fill="#f59e0b" radius={[2, 2, 0, 0]} />
                                  </BarChart>
                                </ResponsiveContainer>
                              </div>
                            </div>

                            {/* Model breakdown */}
                            {dashboardData.modelBreakdown.length > 0 && (
                              <div className="bg-surface-elevated rounded-lg border border-border overflow-hidden">
                                <div className="px-3 py-2 text-xs font-medium text-text-secondary border-b border-border">Model Breakdown</div>
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-border">
                                      <th className="text-left py-1.5 px-3 text-text-tertiary font-medium">Provider</th>
                                      <th className="text-left py-1.5 px-3 text-text-tertiary font-medium">Model</th>
                                      <th className="text-center py-1.5 px-3 text-text-tertiary font-medium">Runs</th>
                                      <th className="text-center py-1.5 px-3 text-text-tertiary font-medium">Avg Pass</th>
                                      <th className="text-right py-1.5 px-3 text-text-tertiary font-medium">Avg Cost</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {dashboardData.modelBreakdown.map((m, i) => (
                                      <tr key={i} className="border-b border-border/30 hover:bg-surface-hover">
                                        <td className="py-1.5 px-3"><span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400">{m.provider}</span></td>
                                        <td className="py-1.5 px-3 font-mono text-text-secondary truncate max-w-[140px]" title={m.model}>{m.model?.split('-').slice(-2).join('-') || m.model}</td>
                                        <td className="py-1.5 px-3 text-center text-text-secondary">{m.runs}</td>
                                        <td className="py-1.5 px-3 text-center">
                                          <span className={`font-semibold ${m.avgPassRate >= 80 ? 'text-green-400' : m.avgPassRate >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>{m.avgPassRate}%</span>
                                        </td>
                                        <td className="py-1.5 px-3 text-right font-mono text-text-tertiary">${m.avgCost.toFixed(4)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* History Tab */}
                    {bottomPanelTab === 'history' && (
                      <div className="h-full flex flex-col overflow-hidden">
                        {resultsHistory.length === 0 ? (
                          <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
                            No run history yet for this test file.
                          </div>
                        ) : (
                          <>
                            {/* Filter row */}
                            <div className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 bg-surface border-b border-border">
                              <div className="relative flex-1 max-w-sm">
                                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-disabled pointer-events-none" />
                                <input
                                  type="text"
                                  value={historyFilterQuery}
                                  onChange={(e) => setHistoryFilterQuery(e.target.value)}
                                  placeholder="Filter runs (provider, model, run id)…"
                                  className="w-full pl-7 pr-2 py-1 text-xs rounded bg-surface-elevated border border-border focus:border-primary focus:outline-none text-text-primary placeholder:text-text-disabled"
                                />
                              </div>
                              {historyProviders.length > 1 && historyProviders.map((p) => (
                                <button key={p} type="button" onClick={() => setHistoryProviderFilter((cur) => (cur === p ? null : p))}
                                  className={`px-1.5 py-0.5 rounded text-[10px] transition ${historyProviderFilter === p ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface-elevated text-text-tertiary border border-border hover:text-text-secondary'}`}>
                                  {p}
                                </button>
                              ))}
                              <label className="inline-flex items-center gap-1.5 text-[11px] text-text-tertiary cursor-pointer select-none">
                                <input type="checkbox" checked={historyFailedOnly} onChange={(e) => setHistoryFailedOnly(e.target.checked)} className="accent-primary" />
                                Failed only
                              </label>
                              <span className="text-[10px] text-text-disabled">{filteredHistory.length} / {resultsHistory.length}</span>
                              {historySelectMode && selectedRunIds.size > 0 && (
                                <button
                                  onClick={async () => {
                                    if (!(await confirmAction({ title: 'Delete runs', message: `Delete ${selectedRunIds.size} run${selectedRunIds.size > 1 ? 's' : ''}?` }))) return
                                    const ids = Array.from(selectedRunIds)
                                    try {
                                      const res = await fetch('/api/results/runs/bulk-delete', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ run_ids: ids }),
                                      })
                                      if (!res.ok) { notifyError('Delete failed'); return }
                                      const { run_ids: deletedIds } = await res.json()
                                      const deletedSet = new Set(deletedIds)
                                      if (pinnedHistoryRun?.metadata?.run_id && deletedSet.has(pinnedHistoryRun.metadata.run_id)) setPinnedHistoryRun(null)
                                      setSelectedRunIds(new Set())
                                      setHistorySelectMode(false)
                                      const testFile = selectedFile?.relative_path || selectedFile?.filename
                                      if (testFile) loadResultsHistory(testFile)
                                    } catch (e) { notifyError('Failed to delete selected runs') }
                                  }}
                                  className="px-2 py-1 text-xs rounded bg-error/20 text-error hover:bg-error/30 transition-colors"
                                >
                                  Delete {selectedRunIds.size}
                                </button>
                              )}
                              <button
                                onClick={() => { setHistorySelectMode(prev => !prev); setSelectedRunIds(new Set()) }}
                                className={`px-2 py-1 text-xs rounded transition-colors ${historySelectMode ? 'bg-primary/20 text-primary' : 'bg-surface text-text-tertiary hover:text-text-primary hover:bg-surface-hover'}`}
                              >
                                {historySelectMode ? 'Cancel' : 'Select'}
                              </button>
                            </div>

                            {/* Run list with expandable details */}
                            <div className="flex-1 overflow-auto">
                              <table className="w-full text-xs">
                                <thead className="sticky top-0 bg-surface-elevated z-10">
                                  <tr className="border-b border-border">
                                    {historySelectMode && (
                                      <th className="py-2 px-3">
                                        <input type="checkbox" className="accent-primary"
                                          checked={filteredHistory.length > 0 && filteredHistory.every(r => selectedRunIds.has(r.run_id))}
                                          onChange={(e) => { if (e.target.checked) { setSelectedRunIds(new Set(filteredHistory.map(r => r.run_id))) } else { setSelectedRunIds(new Set()) } }}
                                        />
                                      </th>
                                    )}
                                    <SortableTH sortKey="timestamp" align="left" sort={historySort} onSort={toggleHistorySort}>Date</SortableTH>
                                    <th className="text-left py-2 px-3 text-text-tertiary font-medium">Provider</th>
                                    <th className="text-left py-2 px-3 text-text-tertiary font-medium">Model</th>
                                    <SortableTH sortKey="pass" align="center" sort={historySort} onSort={toggleHistorySort}>Pass</SortableTH>
                                    <SortableTH sortKey="cost" align="right" sort={historySort} onSort={toggleHistorySort}>Cost</SortableTH>
                                    <SortableTH sortKey="duration" align="right" sort={historySort} onSort={toggleHistorySort}>Time</SortableTH>
                                    <th className="py-2 px-3 w-6" />
                                  </tr>
                                </thead>
                                <tbody>
                                  {filteredHistory.map((run, idx) => {
                                    const isPinned = pinnedHistoryRun?.metadata?.run_id === run.run_id
                                    const isSelected = selectedRunIds.has(run.run_id)
                                    const isExpanded = expandedRunId === run.run_id
                                    const isLoading = loadingRunId === run.run_id
                                    const details = expandedRunDetails[run.run_id]
                                    return (
                                      <React.Fragment key={run.run_id || idx}>
                                        <tr
                                          className={`border-b border-border/30 cursor-pointer transition-colors ${isSelected ? 'bg-primary/10' : isPinned ? 'bg-primary/15' : isExpanded ? 'bg-surface-elevated' : 'hover:bg-surface-hover'}`}
                                          onClick={() => {
                                            if (historySelectMode) {
                                              setSelectedRunIds(prev => { const n = new Set(prev); n.has(run.run_id) ? n.delete(run.run_id) : n.add(run.run_id); return n })
                                            } else {
                                              expandRunDetails(run.run_id)
                                            }
                                          }}
                                        >
                                          {historySelectMode && (
                                            <td className="py-2 px-3" onClick={e => e.stopPropagation()}>
                                              <input type="checkbox" className="accent-primary" checked={isSelected}
                                                onChange={() => setSelectedRunIds(prev => { const n = new Set(prev); n.has(run.run_id) ? n.delete(run.run_id) : n.add(run.run_id); return n })}
                                              />
                                            </td>
                                          )}
                                          <td className="py-2 px-3 text-text-secondary">
                                            {new Date(run.timestamp).toLocaleDateString()} {new Date(run.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                                          </td>
                                          <td className="py-2 px-3">
                                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400">{run.provider}</span>
                                          </td>
                                          <td className="py-2 px-3 text-text-secondary font-mono truncate max-w-[120px]" title={run.model}>
                                            {run.model?.split('-').slice(-2).join('-') || run.model}
                                          </td>
                                          <td className="py-2 px-3 text-center">
                                            <span className={`font-semibold ${run.pass_rate === 1 ? 'text-green-400' : run.pass_rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'}`}>
                                              {run.passed}/{run.total}
                                            </span>
                                          </td>
                                          <td className="py-2 px-3 text-right text-text-tertiary font-mono">${run.total_cost?.toFixed(4) || '0.00'}</td>
                                          <td className="py-2 px-3 text-right text-text-tertiary">{run.total_duration?.toFixed(1)}s</td>
                                          <td className="py-2 px-3 text-center text-text-disabled">
                                            {isLoading ? <Loader2 size={12} className="animate-spin inline" /> : isExpanded ? <ChevronUp size={12} className="inline text-primary" /> : <ChevronDown size={12} className="inline" />}
                                          </td>
                                        </tr>
                                        {/* Expanded run details */}
                                        {isExpanded && (
                                          <tr className="border-b border-border/30">
                                            <td colSpan={historySelectMode ? 8 : 7} className="p-0">
                                              <div className="bg-surface-elevated/40 border-l-2 border-primary px-4 py-3">
                                                {isLoading ? (
                                                  <div className="flex items-center gap-2 text-text-tertiary text-xs py-2">
                                                    <Loader2 size={14} className="animate-spin" /> Loading run details…
                                                  </div>
                                                ) : details ? (
                                                  <div>
                                                    {/* Summary strip */}
                                                    <div className="flex items-center gap-4 text-xs text-text-tertiary mb-3 pb-2 border-b border-border/50">
                                                      <span className="font-medium text-text-secondary">{new Date(run.timestamp).toLocaleString()}</span>
                                                      <span><span className="text-green-400 font-semibold">{details.summary?.passed ?? run.passed}</span> passed</span>
                                                      <span><span className="text-red-400 font-semibold">{details.summary?.failed ?? (run.total - run.passed)}</span> failed</span>
                                                      {(() => {
                                                        const cost = details.summary?.total_cost ?? details.summary?.total_cost_usd ?? details.metadata?.total_cost ?? 0
                                                        return cost > 0 ? <span className="font-mono">${cost.toFixed(4)}</span> : null
                                                      })()}
                                                      <button
                                                        type="button"
                                                        onClick={(e) => { e.stopPropagation(); pinHistoryRun(run.run_id); setBottomPanelTab('results') }}
                                                        className="ml-auto px-2 py-0.5 rounded text-[11px] text-primary hover:bg-primary/20 border border-primary/30 transition"
                                                      >
                                                        View in Results tab →
                                                      </button>
                                                    </div>
                                                    {/* TestResultPanel cards */}
                                                    <div className="space-y-2">
                                                      {details.results?.map((result, i) => (
                                                        <TestResultPanel key={i} result={result} initialExpanded={!result.passed} />
                                                      ))}
                                                    </div>
                                                  </div>
                                                ) : (
                                                  <div className="text-xs text-text-tertiary py-2">Failed to load run details.</div>
                                                )}
                                              </div>
                                            </td>
                                          </tr>
                                        )}
                                      </React.Fragment>
                                    )
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {/* Results Tab */}
                    {bottomPanelTab === 'results' && (pinnedHistoryRun || testResults) && (() => {
                      const displayResults = pinnedHistoryRun || testResults
                      return (
                        <div className="h-full flex flex-col">
                          {pinnedHistoryRun && (
                            <div className="px-4 py-2 flex items-center gap-3 text-xs bg-primary/10 border-b border-primary/20">
                              <History size={12} className="text-primary flex-shrink-0" />
                              <span className="text-text-secondary">
                                Viewing historical run from{' '}
                                <span className="text-text-primary font-medium">
                                  {pinnedHistoryRun.metadata?.timestamp ? new Date(pinnedHistoryRun.metadata.timestamp).toLocaleString() : 'unknown date'}
                                </span>
                                {pinnedHistoryRun.metadata?.provider && <> · <span className="text-text-tertiary">{pinnedHistoryRun.metadata.provider}</span></>}
                                {pinnedHistoryRun.metadata?.model && <> · <span className="text-text-tertiary font-mono">{pinnedHistoryRun.metadata.model}</span></>}
                              </span>
                              <span className="flex-1" />
                              <button type="button" onClick={() => { setPinnedHistoryRun(null); if (!testResults) setBottomPanelTab('dashboard') }}
                                className="px-2 py-0.5 rounded text-[11px] text-primary hover:bg-primary/20 transition">Unpin</button>
                            </div>
                          )}
                          <div className="px-4 py-2 bg-surface-elevated/50 flex items-center gap-6 text-xs border-b border-border/50">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 rounded-full bg-green-500" />
                              <span className="text-text-tertiary">Passed:</span>
                              <span className="font-semibold text-green-400">{displayResults.summary.passed}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 rounded-full bg-red-500" />
                              <span className="text-text-tertiary">Failed:</span>
                              <span className="font-semibold text-red-400">{displayResults.summary.failed}</span>
                            </div>
                            {(() => {
                              const cost = displayResults.summary?.total_cost ?? displayResults.summary?.total_cost_usd ?? displayResults.metadata?.total_cost ?? 0
                              return cost > 0 ? <div className="flex items-center gap-2"><span className="text-text-tertiary">Cost:</span><span className="font-mono text-text-secondary">${cost.toFixed(4)}</span></div> : null
                            })()}
                          </div>
                          <div className="flex-1 overflow-auto p-3">
                            {displayResults.results?.length > 0 ? (
                              <div className="space-y-2">
                                {displayResults.results.map((result, idx) => (
                                  <TestResultPanel key={idx} result={result} initialExpanded={!result.passed} />
                                ))}
                              </div>
                            ) : (
                              <div className="text-center py-4 text-text-tertiary text-sm">No test results available</div>
                            )}
                          </div>
                        </div>
                      )
                    })()}

                    {/* Results Tab — empty state */}
                    {bottomPanelTab === 'results' && !pinnedHistoryRun && !testResults && (
                      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
                        Run tests to see results here, or click a row in the History tab.
                      </div>
                    )}

                    {/* Logs Tab */}
                    {bottomPanelTab === 'logs' && (
                      <StreamingLogViewer logs={streamingLogs} running={running} />
                    )}
                  </div>
                </div>
              </>
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

              {/* Connection-health banner — the run survives server-side;
                  this strip only reports the state of the streaming pipe. */}
              {connectionState === 'reconnecting' && (
                <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1.5 rounded-lg border border-warning/30 bg-warning/10 text-warning text-xs shadow-lg">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Connection lost — reconnecting to the run…</span>
                </div>
              )}
              {connectionState === 'disconnected' && (
                <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1.5 rounded-lg border border-error/30 bg-error/10 text-error text-xs shadow-lg">
                  <span>Disconnected — the run may still be going on the server.</span>
                  <button
                    onClick={() => attachToRun(currentRunId)}
                    className="px-2 py-0.5 rounded bg-error/20 hover:bg-error/30 font-medium transition-colors"
                  >
                    Reattach
                  </button>
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
                      aria-label="Close"
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
              <p className="text-base md:text-lg text-text-secondary">Select a test file to view or edit</p>
              <p className="text-sm text-text-tertiary mt-2">Choose a file from the sidebar to get started</p>
            </div>
          </div>
        )}
        </div>
      </div>

      {/* Test Case Wizard */}
      {showTestWizard && (
        <TestCaseWizard
          onComplete={async (filename, yamlContent) => {
            try {
              await fetch('/api/tests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, content: yamlContent }),
              })
              setShowTestWizard(false)
              loadTestFiles()
              loadTestFile(filename)
            } catch (error) {
              console.error('Failed to create test file:', error)
              notifyError('Failed to create test file')
            }
          }}
          onCancel={() => setShowTestWizard(false)}
        />
      )}

      {showBench && (
        <BenchmarkModal
          defaultTestPath={selectedFile?.relative_path || selectedFile?.filename || 'tests/'}
          onClose={() => setShowBench(false)}
        />
      )}
    </div>
  )
}

export default TestManager
