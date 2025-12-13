import React, { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Copy, Check, EyeOff, Sparkles, Code2, Search, Command, HelpCircle, CheckSquare, Square, MessageSquare, Wand2, TestTube2, Play, Clock, Bug, AlertCircle, GitCompare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ParameterCard from '../components/ParameterCard'
import TestGenerationModal from '../components/TestGenerationModal'
import SchemaCodeViewer from '../components/SchemaCodeViewer'
import OptimizeDocsModal from '../components/OptimizeDocsModal'
import ToolDebugModal from '../components/ToolDebugModal'
import { ToolCardSkeleton } from '../components/SkeletonLoader'
import { LoadingSpinner } from '../components/LoadingSpinner'

function MCPExplorer({ selectedProfiles = [] }) {
  const navigate = useNavigate()
  const [tools, setTools] = useState([])
  const [resources, setResources] = useState([])
  const [prompts, setPrompts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedTools, setExpandedTools] = useState(new Set())
  const [copiedId, setCopiedId] = useState(null)
  const [activeTab, setActiveTab] = useState('tools')
  const [showCodeViewer, setShowCodeViewer] = useState(new Set())
  const [selectedToolForGeneration, setSelectedToolForGeneration] = useState(null)
  const [selectedToolForOptimization, setSelectedToolForOptimization] = useState(null)
  const [selectedToolForDebug, setSelectedToolForDebug] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [selectedTools, setSelectedTools] = useState(new Set())
  const [batchMode, setBatchMode] = useState(false)
  const [toolTests, setToolTests] = useState({}) // Map of tool name -> test info
  const [runningTests, setRunningTests] = useState(new Set()) // Set of tool names currently running tests

  // Smoke test state
  const [smokeTestReport, setSmokeTestReport] = useState(null)
  const [runningSmokeTest, setRunningSmokeTest] = useState(false)
  const [showSmokeTestResults, setShowSmokeTestResults] = useState(false)

  // Comparison mode state
  const [compareProfile1, setCompareProfile1] = useState([])
  const [compareProfile2, setCompareProfile2] = useState([])
  const [compareToolName, setCompareToolName] = useState('')
  const [compareParameters, setCompareParameters] = useState('{}')
  const [compareIterations, setCompareIterations] = useState(3)
  const [comparisonResults, setComparisonResults] = useState(null)
  const [runningComparison, setRunningComparison] = useState(false)

  // For Explorer, only use the first selected profile (single MCP at a time)
  const activeProfile = selectedProfiles.length > 0 ? selectedProfiles[0] : null
  const hasMultipleSelected = selectedProfiles.length > 1

  // Load data on mount and when active profile changes
  useEffect(() => {
    loadData()
    loadToolTests()
  }, [activeProfile])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e) => {
      // Ignore if typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') {
          e.target.blur()
          setSearchQuery('')
        }
        return
      }

      // "/" - Focus search
      if (e.key === '/') {
        e.preventDefault()
        document.getElementById('explorer-search')?.focus()
      }

      // "?" - Show shortcuts
      if (e.key === '?') {
        e.preventDefault()
        setShowShortcuts(!showShortcuts)
      }

      // "Escape" - Close modals/clear search
      if (e.key === 'Escape') {
        setShowShortcuts(false)
        setSearchQuery('')
        setSelectedToolForGeneration(null)
        setSelectedToolForOptimization(null)
      }

      // "c" - Copy first visible tool
      if (e.key === 'c') {
        const visibleTools = filterTools()
        if (visibleTools.length > 0) {
          copyToClipboard(visibleTools[0].name, 'quick-copy')
        }
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [showShortcuts, searchQuery])

  const fetchWithRetry = async (url, retries = 3, delay = 1000) => {
    for (let i = 0; i < retries; i++) {
      try {
        const response = await fetch(url)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response
      } catch (error) {
        if (i === retries - 1) throw error
        console.log(`Retry ${i + 1}/${retries} for ${url}...`)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      // Only use the first selected profile for Explorer (single MCP at a time)
      const params = new URLSearchParams()
      if (activeProfile) {
        params.append('profiles', activeProfile)
      }
      const queryString = params.toString() ? `?${params.toString()}` : ''

      const [toolsRes, resourcesRes, promptsRes] = await Promise.all([
        fetchWithRetry(`/api/mcp/tools${queryString}`),
        fetchWithRetry(`/api/mcp/resources${queryString}`),
        fetchWithRetry(`/api/mcp/prompts${queryString}`),
      ])

      setTools(await toolsRes.json())
      setResources(await resourcesRes.json())
      setPrompts(await promptsRes.json())
    } catch (err) {
      console.error('Failed to load MCP data:', err)
      setError(err.message || 'Failed to load MCP data')
    } finally {
      setLoading(false)
    }
  }

  const loadToolTests = async () => {
    try {
      const res = await fetch('/api/tests')
      const data = await res.json()

      // Build a map of tool name -> test info
      const testsMap = {}

      // Process folders (folders are named after tools)
      Object.entries(data.folders || {}).forEach(([folderName, files]) => {
        testsMap[folderName] = {
          count: files.length,
          files: files,
          lastRun: getLastTestRunResult(folderName),
        }
      })

      setToolTests(testsMap)
    } catch (error) {
      console.error('Failed to load tool tests:', error)
    }
  }

  const sanitizeToolName = (toolName) => {
    // Convert tool name to safe folder name (same logic as backend)
    return toolName.replace(/[^a-zA-Z0-9_-]/g, '_')
  }

  const getLastTestRunResult = (toolName) => {
    // Try to get last test result from localStorage
    try {
      const key = `test_result_${toolName}`
      const stored = localStorage.getItem(key)
      if (stored) {
        return JSON.parse(stored)
      }
    } catch (error) {
      console.error('Failed to load test result:', error)
    }
    return null
  }

  const saveTestRunResult = (toolName, result) => {
    try {
      const key = `test_result_${toolName}`
      localStorage.setItem(key, JSON.stringify({
        timestamp: Date.now(),
        passed: result.summary.passed,
        failed: result.summary.failed,
        total: result.summary.total,
      }))
    } catch (error) {
      console.error('Failed to save test result:', error)
    }
  }

  const runToolTests = async (toolName) => {
    const safeName = sanitizeToolName(toolName)
    const testInfo = toolTests[safeName]

    if (!testInfo || testInfo.count === 0) {
      alert('No tests found for this tool')
      return
    }

    setRunningTests(prev => new Set([...prev, toolName]))

    try {
      // Use the new backend endpoint that runs all tests for a tool
      const res = await fetch(`/api/tests/run-tool/${encodeURIComponent(toolName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      if (res.ok) {
        const result = await res.json()

        // Save result
        saveTestRunResult(safeName, result)

        // Reload test info to show updated status
        await loadToolTests()

        const summary = result.summary
        alert(`Test run complete!\nPassed: ${summary.passed}/${summary.total}\nFailed: ${summary.failed}\n\nFiles tested: ${result.files_tested.length}`)
      } else {
        const error = await res.json()
        console.error('Test run failed:', error)
        alert(`Failed to run tests: ${error.detail || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Failed to run tests:', error)
      alert(`Failed to run tests: ${error.message}`)
    } finally {
      setRunningTests(prev => {
        const next = new Set(prev)
        next.delete(toolName)
        return next
      })
    }
  }

  const runSmokeTest = async () => {
    if (!activeProfile) {
      alert('No MCP profile selected')
      return
    }

    setRunningSmokeTest(true)
    setSmokeTestReport(null)

    try {
      // Extract profile ID from "profile_id:mcp_name" format
      const profileId = activeProfile.split(':')[0]

      const res = await fetch('/api/smoke-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: profileId,
          test_all_tools: true,
          max_tools_to_test: 10,
        }),
      })

      if (res.ok) {
        const report = await res.json()
        setSmokeTestReport(report)
        setShowSmokeTestResults(true)
      } else {
        const error = await res.json()
        console.error('Smoke test failed:', error)
        alert(`Failed to run smoke test: ${error.detail || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Failed to run smoke test:', error)
      alert(`Failed to run smoke test: ${error.message}`)
    } finally {
      setRunningSmokeTest(false)
    }
  }

  const tryInChat = (tool) => {
    // Navigate to chat with pre-filled tool information
    // We'll store the tool info in localStorage for the chat to pick up
    try {
      localStorage.setItem('prefillTool', JSON.stringify({
        name: tool.name,
        description: tool.description,
        schema: tool.input_schema,
      }))
      navigate('/chat')
    } catch (error) {
      console.error('Failed to navigate to chat:', error)
    }
  }

  const toggleTool = (toolName) => {
    const newExpanded = new Set(expandedTools)
    if (newExpanded.has(toolName)) {
      newExpanded.delete(toolName)
    } else {
      newExpanded.add(toolName)
    }
    setExpandedTools(newExpanded)
  }

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const toggleCodeViewer = (toolName) => {
    const newShowCode = new Set(showCodeViewer)
    if (newShowCode.has(toolName)) {
      newShowCode.delete(toolName)
    } else {
      newShowCode.add(toolName)
    }
    setShowCodeViewer(newShowCode)
  }

  const handleTestGenerationSuccess = (data) => {
    // Show success notification
    alert(`Successfully generated ${data.test_count} test(s) in ${data.filename}`)
    // Close modal
    setSelectedToolForGeneration(null)
    // Reload test info to show the new tests
    loadToolTests()
  }

  const toggleToolSelection = (toolName) => {
    const newSelected = new Set(selectedTools)
    if (newSelected.has(toolName)) {
      newSelected.delete(toolName)
    } else {
      newSelected.add(toolName)
    }
    setSelectedTools(newSelected)
  }

  const selectAllTools = () => {
    setSelectedTools(new Set(filterTools().map(t => t.name)))
  }

  const deselectAllTools = () => {
    setSelectedTools(new Set())
  }

  const generateBatchTests = () => {
    if (selectedTools.size === 0) {
      alert('Please select at least one tool')
      return
    }
    // For now, open modal for first selected tool
    // TODO: Implement proper batch generation
    const firstTool = tools.find(t => selectedTools.has(t.name))
    if (firstTool) {
      setSelectedToolForGeneration(firstTool)
    }
  }

  // Fuzzy filter tools/resources/prompts
  const filterTools = () => {
    if (!searchQuery.trim()) return tools
    const query = searchQuery.toLowerCase()
    return tools.filter(tool =>
      tool.name.toLowerCase().includes(query) ||
      tool.description.toLowerCase().includes(query)
    )
  }

  const filterResources = () => {
    if (!searchQuery.trim()) return resources
    const query = searchQuery.toLowerCase()
    return resources.filter(res =>
      res.name.toLowerCase().includes(query) ||
      res.description.toLowerCase().includes(query)
    )
  }

  const filterPrompts = () => {
    if (!searchQuery.trim()) return prompts
    const query = searchQuery.toLowerCase()
    return prompts.filter(prompt =>
      prompt.name.toLowerCase().includes(query) ||
      prompt.description.toLowerCase().includes(query)
    )
  }

  // Run tool comparison
  const runComparison = async () => {
    if (!compareToolName.trim()) {
      alert('Please select a tool to compare')
      return
    }
    if (compareProfile1.length === 0 || compareProfile2.length === 0) {
      alert('Please select two profiles/servers to compare')
      return
    }
    if (compareProfile1[0] === compareProfile2[0]) {
      alert('Please select two different profiles/servers')
      return
    }

    let parameters = {}
    try {
      parameters = JSON.parse(compareParameters)
    } catch (e) {
      alert('Invalid JSON in parameters field')
      return
    }

    setRunningComparison(true)
    setComparisonResults(null)

    try {
      const response = await fetch('/api/tools/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: compareToolName,
          profile1: compareProfile1[0],
          profile2: compareProfile2[0],
          parameters: parameters,
          iterations: compareIterations,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Comparison failed')
      }

      const data = await response.json()
      setComparisonResults(data)
    } catch (error) {
      console.error('Comparison error:', error)
      alert(`Comparison failed: ${error.message}`)
    } finally {
      setRunningComparison(false)
    }
  }

  if (loading) {
    return (
      <div className="h-full flex flex-col">
        <div className="p-4 border-b border-border bg-surface-elevated">
          <h1 className="text-2xl font-bold">Explorer</h1>
          <p className="text-text-secondary mt-1 text-base">
            Loading MCP data...
          </p>
        </div>
        <div className="flex-1 overflow-auto p-4 bg-background-subtle">
          <div className="max-w-5xl mx-auto space-y-4">
            {Array.from({ length: 5 }).map((_, idx) => (
              <ToolCardSkeleton key={idx} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex flex-col">
        <div className="p-4 border-b border-border bg-surface-elevated">
          <h1 className="text-2xl font-bold">Explorer</h1>
          <p className="text-text-secondary mt-1 text-base">
            Failed to load MCP data
          </p>
        </div>
        <div className="flex-1 overflow-auto p-4 bg-background-subtle">
          <div className="max-w-2xl mx-auto">
            <div className="bg-error/10 border border-error/30 rounded-lg p-6 text-center">
              <AlertCircle size={48} className="text-error mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-error mb-2">Failed to Load MCP Data</h2>
              <p className="text-text-secondary mb-4">{error}</p>
              <button
                onClick={loadData}
                className="btn btn-primary"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-border bg-surface-elevated">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold">Explorer</h1>
            <p className="text-text-secondary mt-1 text-base">
              Browse tools, resources, and prompts from your MCP service
              {batchMode && selectedTools.size > 0 && (
                <span className="ml-2 text-xs bg-primary/10 text-primary px-2 py-0.5 rounded border border-primary/20">
                  {selectedTools.size} selected
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => runSmokeTest()}
              className="btn btn-primary text-sm flex items-center gap-2"
              title="Run smoke tests on this MCP server"
              disabled={!activeProfile || runningSmokeTest}
            >
              {runningSmokeTest ? (
                <>
                  <LoadingSpinner size={16} />
                  <span>Running...</span>
                </>
              ) : (
                <>
                  <TestTube2 size={16} />
                  <span>Smoke Test</span>
                </>
              )}
            </button>
            <button
              onClick={() => {
                setBatchMode(!batchMode)
                if (!batchMode) {
                  deselectAllTools()
                }
              }}
              className={`btn text-sm flex items-center gap-2 ${batchMode ? 'btn-primary' : 'btn-secondary'}`}
              title="Toggle batch selection mode"
            >
              {batchMode ? <CheckSquare size={16} /> : <Square size={16} />}
              <span>{batchMode ? 'Exit Batch Mode' : 'Batch Mode'}</span>
            </button>
            <button
              onClick={() => setShowShortcuts(true)}
              className="btn btn-secondary text-sm flex items-center gap-2"
              title="Show keyboard shortcuts (press ?)"
            >
              <HelpCircle size={16} />
              <span>Shortcuts</span>
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative mt-3">
          <Search size={18} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-tertiary" />
          <input
            id="explorer-search"
            type="text"
            placeholder="Search tools, resources, and prompts... (press / to focus)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input pl-10 pr-4 w-full text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-text-tertiary hover:text-text-primary"
            >
              <span className="text-xs">Clear</span>
            </button>
          )}
        </div>

        {/* Active MCP Banner */}
        {activeProfile && (
          <div className="mt-3">
            {hasMultipleSelected ? (
              <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 flex items-start gap-3">
                <div className="text-warning-light mt-0.5">⚠️</div>
                <div className="flex-1 text-sm">
                  <p className="text-warning-light font-semibold mb-1">Multiple MCP Servers Selected</p>
                  <p className="text-text-secondary">
                    Explorer shows tools from <strong className="text-text-primary">{activeProfile.split(':')[1] || activeProfile}</strong> only.
                    Use the Tests page to work with multiple servers simultaneously.
                  </p>
                </div>
              </div>
            ) : (
              <div className="bg-info/10 border border-info/30 rounded-lg p-3 flex items-center gap-3">
                <div className="text-info-light">ℹ️</div>
                <div className="text-sm text-text-secondary">
                  Showing tools from <strong className="text-info-light">{activeProfile.split(':')[1] || activeProfile}</strong>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="px-4 pt-4 border-b border-border bg-surface-elevated/50">
        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab('tools')}
              className={`tab ${
                activeTab === 'tools' ? 'tab-active' : 'tab-inactive'
              }`}
            >
              Tools ({filterTools().length}/{tools.length})
            </button>
            <button
              onClick={() => setActiveTab('resources')}
              className={`tab ${
                activeTab === 'resources' ? 'tab-active' : 'tab-inactive'
              }`}
            >
              Resources ({filterResources().length}/{resources.length})
            </button>
            <button
              onClick={() => setActiveTab('prompts')}
              className={`tab ${
                activeTab === 'prompts' ? 'tab-active' : 'tab-inactive'
              }`}
            >
              Prompts ({filterPrompts().length}/{prompts.length})
            </button>
            <button
              onClick={() => {
                setActiveTab('compare')
                setComparisonResults(null)
              }}
              className={`tab ${
                activeTab === 'compare' ? 'tab-active' : 'tab-inactive'
              }`}
            >
              <GitCompare size={16} className="mr-1" />
              Compare
            </button>
          </div>
          {batchMode && activeTab === 'tools' && (
            <div className="flex gap-2 mb-2">
              <button
                onClick={selectAllTools}
                className="btn btn-secondary text-xs px-3 py-1"
              >
                Select All
              </button>
              <button
                onClick={deselectAllTools}
                className="btn btn-secondary text-xs px-3 py-1"
              >
                Deselect All
              </button>
              <button
                onClick={generateBatchTests}
                disabled={selectedTools.size === 0}
                className="btn btn-primary text-xs px-3 py-1 flex items-center gap-1.5"
              >
                <Sparkles size={14} />
                <span>Generate Tests ({selectedTools.size})</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 bg-background-subtle">
        {activeTab === 'tools' && (
          <div className="max-w-5xl mx-auto space-y-4">
            {filterTools().length === 0 && searchQuery && (
              <div className="text-center py-20">
                <div className="text-text-tertiary text-lg">No tools found matching "{searchQuery}"</div>
                <p className="text-text-disabled text-sm mt-2">Try a different search term</p>
              </div>
            )}
            {filterTools().map((tool, idx) => (
              <div key={idx} className="card-hover">
                <div
                  className="flex items-start justify-between cursor-pointer group"
                  onClick={() => !batchMode && toggleTool(tool.name)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      {batchMode && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleToolSelection(tool.name)
                          }}
                          className="flex-shrink-0 p-1 hover:bg-surface-hover rounded"
                        >
                          {selectedTools.has(tool.name) ? (
                            <CheckSquare size={20} className="text-primary" />
                          ) : (
                            <Square size={20} className="text-text-tertiary" />
                          )}
                        </button>
                      )}
                      {!batchMode && (
                        <div className="flex-shrink-0 transition-transform duration-200">
                          {expandedTools.has(tool.name) ? (
                            <ChevronDown size={20} className="text-text-secondary" />
                          ) : (
                            <ChevronRight size={20} className="text-text-secondary" />
                          )}
                        </div>
                      )}
                      <h3 className="font-semibold text-lg text-text-primary">{tool.name}</h3>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          copyToClipboard(tool.name, `name-${tool.name}`)
                        }}
                        className="p-1 hover:bg-surface-hover rounded transition-all opacity-0 group-hover:opacity-100"
                        title="Copy tool name"
                      >
                        {copiedId === `name-${tool.name}` ? (
                          <Check size={14} className="text-success" />
                        ) : (
                          <Copy size={14} className="text-text-tertiary hover:text-text-primary" />
                        )}
                      </button>
                      {(() => {
                        const safeName = sanitizeToolName(tool.name)
                        const testInfo = toolTests[safeName]
                        if (testInfo && testInfo.count > 0) {
                          return (
                            <div className="flex items-center gap-1.5 ml-2" title={`${testInfo.count} test files available`}>
                              <TestTube2 size={14} className="text-primary" />
                              <span className="text-xs font-semibold text-primary">{testInfo.count}</span>
                            </div>
                          )
                        }
                        return null
                      })()}
                    </div>
                    <p className="text-text-secondary mt-2 ml-8 line-clamp-2">
                      {tool.description.split('\n')[0]}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      copyToClipboard(JSON.stringify(tool, null, 2), tool.name)
                    }}
                    className="p-2 hover:bg-surface-hover rounded-lg transition-all duration-200 flex-shrink-0 ml-3"
                  >
                    {copiedId === tool.name ? (
                      <Check size={18} className="text-success" />
                    ) : (
                      <Copy size={18} className="text-text-tertiary hover:text-text-primary transition-colors" />
                    )}
                  </button>
                </div>

                {expandedTools.has(tool.name) && (
                  <div className="mt-5 ml-8 pt-5 border-t border-border space-y-5 animate-fade-in">
                    {/* Actions */}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedToolForGeneration(tool)
                        }}
                        className="btn btn-primary text-sm"
                      >
                        <Sparkles size={16} />
                        <span>Generate Tests</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedToolForOptimization(tool)
                        }}
                        className="btn btn-secondary text-sm"
                        title="Optimize tool description for better LLM understanding"
                      >
                        <Wand2 size={16} />
                        <span>Optimize LLM Docs</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          tryInChat(tool)
                        }}
                        className="btn btn-secondary text-sm"
                        title="Try this tool in the chat interface"
                      >
                        <MessageSquare size={16} />
                        <span>Try in Chat</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedToolForDebug(tool)
                        }}
                        className="btn btn-secondary text-sm"
                        title="Debug this tool with trace visualization"
                      >
                        <Bug size={16} />
                        <span>Debug</span>
                      </button>
                    </div>

                    {/* Test Information */}
                    {(() => {
                      const safeName = sanitizeToolName(tool.name)
                      const testInfo = toolTests[safeName]

                      if (testInfo && testInfo.count > 0) {
                        const lastRun = testInfo.lastRun
                        const isRunning = runningTests.has(tool.name)

                        return (
                          <div className="bg-surface-elevated border border-border rounded-lg p-4">
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-2">
                                <TestTube2 size={16} className="text-primary" />
                                <h4 className="text-sm font-semibold text-text-secondary">
                                  Tests for this tool
                                </h4>
                                <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded border border-primary/20">
                                  {testInfo.count} test file{testInfo.count !== 1 ? 's' : ''}
                                </span>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  runToolTests(tool.name)
                                }}
                                disabled={isRunning}
                                className="btn btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5"
                                title="Run all tests for this tool"
                              >
                                {isRunning ? (
                                  <>
                                    <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                    <span>Running...</span>
                                  </>
                                ) : (
                                  <>
                                    <Play size={14} />
                                    <span>Run All Tests</span>
                                  </>
                                )}
                              </button>
                            </div>

                            {lastRun && (
                              <div className="flex items-center gap-4 text-xs">
                                <div className="flex items-center gap-1.5">
                                  <Clock size={12} className="text-text-tertiary" />
                                  <span className="text-text-secondary">
                                    Last run: {new Date(lastRun.timestamp).toLocaleString()}
                                  </span>
                                </div>
                                <div className={`flex items-center gap-1 px-2 py-0.5 rounded ${
                                  lastRun.failed === 0
                                    ? 'bg-success/10 text-success border border-success/20'
                                    : 'bg-error/10 text-error border border-error/20'
                                }`}>
                                  <span className="font-semibold">
                                    {lastRun.passed}/{lastRun.total} passed
                                  </span>
                                </div>
                              </div>
                            )}

                            <div className="mt-3 space-y-1">
                              {testInfo.files.map((file, idx) => (
                                <div
                                  key={idx}
                                  className="text-xs text-text-tertiary font-mono bg-surface hover:bg-surface-hover px-2 py-1 rounded cursor-pointer transition-colors"
                                  title={file.relative_path}
                                >
                                  {file.filename} ({file.test_count} test{file.test_count !== 1 ? 's' : ''})
                                </div>
                              ))}
                            </div>
                          </div>
                        )
                      }

                      return null
                    })()}

                    {/* Full description */}
                    {tool.description.split('\n').length > 1 && (
                      <div>
                        <h4 className="text-sm font-semibold text-text-secondary mb-2">
                          Description
                        </h4>
                        <pre className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
                          {tool.description}
                        </pre>
                      </div>
                    )}

                    {/* Parameters - Smart Display with ParameterCard */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-semibold text-text-secondary">
                          Parameters
                        </h4>
                        {tool.input_schema?.properties && (
                          <button
                            onClick={() => {
                              if (!showCodeViewer.has(tool.name)) {
                                toggleCodeViewer(tool.name)
                              }
                            }}
                            className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-primary transition-colors px-2 py-1 rounded hover:bg-surface-hover"
                            title="Click any parameter to view code exports"
                          >
                            <Code2 size={14} />
                            <span>View as Code</span>
                          </button>
                        )}
                      </div>

                      {tool.input_schema?.properties ? (
                        <div className="space-y-2">
                          {Object.entries(tool.input_schema.properties).map(
                            ([param, info]) => (
                              <div
                                key={param}
                                onClick={() => {
                                  if (!showCodeViewer.has(tool.name)) {
                                    toggleCodeViewer(tool.name)
                                  }
                                }}
                                className="cursor-pointer transition-all hover:scale-[1.01] hover:shadow-sm"
                                title="Click to view code exports"
                              >
                                <ParameterCard
                                  name={param}
                                  type={info.type}
                                  required={tool.input_schema.required?.includes(param)}
                                  description={info.description}
                                  default={info.default}
                                  enum={info.enum}
                                  items={info.items}
                                  properties={info.properties}
                                  minimum={info.minimum}
                                  maximum={info.maximum}
                                  pattern={info.pattern}
                                  format={info.format}
                                  minLength={info.minLength}
                                  maxLength={info.maxLength}
                                  minItems={info.minItems}
                                  maxItems={info.maxItems}
                                />
                              </div>
                            )
                          )}
                        </div>
                      ) : (
                        <p className="text-sm text-text-tertiary italic bg-surface-elevated border border-border rounded-lg p-4">
                          No parameters
                        </p>
                      )}
                    </div>

                    {/* Output Schema */}
                    {tool.output_schema && (
                      <div>
                        <h4 className="text-sm font-semibold text-text-secondary mb-3">
                          Output Schema
                        </h4>
                        {tool.output_schema?.properties ? (
                          <div className="space-y-2">
                            {Object.entries(tool.output_schema.properties).map(
                              ([param, info]) => (
                                <ParameterCard
                                  key={param}
                                  name={param}
                                  type={info.type}
                                  required={tool.output_schema.required?.includes(param)}
                                  description={info.description}
                                  default={info.default}
                                  enum={info.enum}
                                  items={info.items}
                                  properties={info.properties}
                                />
                              )
                            )}
                          </div>
                        ) : (
                          <p className="text-sm text-text-tertiary italic bg-surface-elevated border border-border rounded-lg p-4">
                            Returns: {tool.output_schema.type || 'object'}
                          </p>
                        )}
                      </div>
                    )}

                    {/* IDE-like Code Viewer for Export */}
                    {tool.input_schema && (
                      <div>
                        <div className="mb-3">
                          <button
                            onClick={() => toggleCodeViewer(tool.name)}
                            className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-primary transition-colors px-2 py-1 rounded hover:bg-surface-hover"
                          >
                            {showCodeViewer.has(tool.name) ? (
                              <>
                                <EyeOff size={14} />
                                <span>Hide Code Viewer</span>
                              </>
                            ) : (
                              <>
                                <Code2 size={14} />
                                <span>Show Code Viewer</span>
                              </>
                            )}
                          </button>
                        </div>

                        {showCodeViewer.has(tool.name) && (
                          <div className="animate-fade-in">
                            <SchemaCodeViewer
                              schema={tool.input_schema}
                              toolName={tool.name}
                              profile={activeProfile}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === 'resources' && (
          <div className="max-w-5xl mx-auto space-y-4">
            {filterResources().length === 0 && searchQuery && (
              <div className="text-center py-20">
                <div className="text-text-tertiary text-lg">No resources found matching "{searchQuery}"</div>
                <p className="text-text-disabled text-sm mt-2">Try a different search term</p>
              </div>
            )}
            {filterResources().map((resource, idx) => (
              <div key={idx} className="card-hover">
                <h3 className="font-semibold text-lg text-text-primary">{resource.name}</h3>
                <p className="text-text-secondary mt-2 leading-relaxed">{resource.description}</p>
                <p className="text-sm text-text-tertiary mt-3 font-mono bg-surface-elevated px-3 py-2 rounded-lg border border-border inline-block">
                  {resource.uri}
                </p>
              </div>
            ))}
            {resources.length === 0 && (
              <div className="text-center py-20">
                <div className="text-text-tertiary text-lg">No resources available</div>
                <p className="text-text-disabled text-sm mt-2">Resources will appear here when they are added</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'prompts' && (
          <div className="max-w-5xl mx-auto space-y-4">
            {filterPrompts().length === 0 && searchQuery && (
              <div className="text-center py-20">
                <div className="text-text-tertiary text-lg">No prompts found matching "{searchQuery}"</div>
                <p className="text-text-disabled text-sm mt-2">Try a different search term</p>
              </div>
            )}
            {filterPrompts().map((prompt, idx) => (
              <div key={idx} className="card-hover">
                <h3 className="font-semibold text-lg text-text-primary">{prompt.name}</h3>
                <p className="text-text-secondary mt-2 leading-relaxed">{prompt.description}</p>
              </div>
            ))}
            {prompts.length === 0 && (
              <div className="text-center py-20">
                <div className="text-text-tertiary text-lg">No prompts available</div>
                <p className="text-text-disabled text-sm mt-2">Prompts will appear here when they are added</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Test Generation Modal */}
      {selectedToolForGeneration && (
        <TestGenerationModal
          tool={selectedToolForGeneration}
          onClose={() => setSelectedToolForGeneration(null)}
          onSuccess={handleTestGenerationSuccess}
        />
      )}

      {/* Optimize Docs Modal */}
      {selectedToolForOptimization && (
        <OptimizeDocsModal
          tool={selectedToolForOptimization}
          onClose={() => setSelectedToolForOptimization(null)}
        />
      )}

      {/* Tool Debug Modal */}
      {selectedToolForDebug && (
        <ToolDebugModal
          tool={selectedToolForDebug}
          profile={activeProfile}
          onClose={() => setSelectedToolForDebug(null)}
        />
      )}

      {/* Keyboard Shortcuts Modal */}
      {showShortcuts && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowShortcuts(false)}>
          <div className="bg-surface border border-border rounded-xl shadow-strong p-6 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Keyboard Shortcuts</h2>
              <button
                onClick={() => setShowShortcuts(false)}
                className="text-text-tertiary hover:text-text-primary"
              >
                <span className="text-2xl">&times;</span>
              </button>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-text-secondary">Focus search</span>
                <kbd className="px-2 py-1 bg-surface-elevated border border-border rounded text-sm font-mono">/</kbd>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-text-secondary">Show shortcuts</span>
                <kbd className="px-2 py-1 bg-surface-elevated border border-border rounded text-sm font-mono">?</kbd>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-text-secondary">Copy first visible tool name</span>
                <kbd className="px-2 py-1 bg-surface-elevated border border-border rounded text-sm font-mono">c</kbd>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-text-secondary">Close modals / Clear search</span>
                <kbd className="px-2 py-1 bg-surface-elevated border border-border rounded text-sm font-mono">Esc</kbd>
              </div>
            </div>
            <p className="mt-4 text-xs text-text-tertiary italic">
              Tip: Shortcuts work when you're not typing in a field
            </p>
          </div>
        </div>
      )}

      {/* Smoke Test Results Modal */}
      {showSmokeTestResults && smokeTestReport && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowSmokeTestResults(false)}>
          <div className="bg-surface border border-border rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 border-b border-border flex items-center justify-between bg-surface-elevated">
              <div>
                <h2 className="text-xl font-bold">Smoke Test Results</h2>
                <p className="text-sm text-text-secondary mt-1">{smokeTestReport.server_url}</p>
              </div>
              <button
                onClick={() => setShowSmokeTestResults(false)}
                className="text-text-secondary hover:text-text-primary"
              >
                ✕
              </button>
            </div>

            <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
              {/* Summary */}
              <div className={`p-4 rounded-lg border mb-6 ${
                smokeTestReport.failed === 0
                  ? 'bg-success/10 border-success/30'
                  : smokeTestReport.passed === 0
                  ? 'bg-error/10 border-error/30'
                  : 'bg-warning/10 border-warning/30'
              }`}>
                <div className="flex items-center gap-3 mb-3">
                  <span className={`text-2xl ${
                    smokeTestReport.failed === 0
                      ? 'text-success-light'
                      : smokeTestReport.passed === 0
                      ? 'text-error-light'
                      : 'text-warning-light'
                  }`}>
                    {smokeTestReport.failed === 0 ? '✓' : smokeTestReport.passed === 0 ? '✗' : '⚠'}
                  </span>
                  <div>
                    <h3 className="font-bold text-lg">
                      {smokeTestReport.failed === 0 ? 'All Tests Passed' : `${smokeTestReport.passed}/${smokeTestReport.total_tests} Tests Passed`}
                    </h3>
                    <p className="text-sm text-text-secondary">
                      Success Rate: {smokeTestReport.success_rate.toFixed(1)}% • Duration: {smokeTestReport.duration_ms.toFixed(0)}ms
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mt-4">
                  <div className="bg-surface/50 rounded p-3 border border-border">
                    <p className="text-xs text-text-tertiary uppercase">Total Tests</p>
                    <p className="text-2xl font-bold">{smokeTestReport.total_tests}</p>
                  </div>
                  <div className="bg-success/10 rounded p-3 border border-success/30">
                    <p className="text-xs text-success-light uppercase">Passed</p>
                    <p className="text-2xl font-bold text-success-light">{smokeTestReport.passed}</p>
                  </div>
                  <div className="bg-error/10 rounded p-3 border border-error/30">
                    <p className="text-xs text-error-light uppercase">Failed</p>
                    <p className="text-2xl font-bold text-error-light">{smokeTestReport.failed}</p>
                  </div>
                </div>
              </div>

              {/* Test Results */}
              <div>
                <h4 className="font-bold mb-3">Test Details</h4>
                <div className="space-y-2">
                  {smokeTestReport.results.map((result, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded border ${
                        result.success
                          ? 'bg-success/5 border-success/20'
                          : 'bg-error/5 border-error/20'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3 flex-1">
                          <span className={`text-lg ${result.success ? 'text-success-light' : 'text-error-light'}`}>
                            {result.success ? '✓' : '✗'}
                          </span>
                          <div className="flex-1">
                            <p className="font-medium">{result.test_name}</p>
                            {result.error_message && (
                              <p className="text-sm text-error-light mt-1">{result.error_message}</p>
                            )}
                            {result.details && result.success && (
                              <div className="text-xs text-text-secondary mt-1">
                                {result.details.tool_count !== undefined && (
                                  <span>{result.details.tool_count} tools available</span>
                                )}
                                {result.details.tool && (
                                  <span>Called {result.details.tool} with {Object.keys(result.details.parameters || {}).length} params</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-text-tertiary whitespace-nowrap ml-4">
                          {result.duration_ms.toFixed(0)}ms
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-border bg-surface-elevated flex justify-end gap-2">
              <button
                onClick={() => {
                  const blob = new Blob([JSON.stringify(smokeTestReport, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `smoke-test-${Date.now()}.json`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
                className="btn btn-secondary text-sm"
              >
                Download JSON
              </button>
              <button
                onClick={() => setShowSmokeTestResults(false)}
                className="btn btn-primary text-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MCPExplorer
