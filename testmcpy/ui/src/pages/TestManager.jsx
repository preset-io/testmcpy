import React, { useState, useEffect } from 'react'
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
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import TestStatusIndicator from '../components/TestStatusIndicator'
import TestResultPanel from '../components/TestResultPanel'

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
  const [models, setModels] = useState({})
  const [selectedProvider, setSelectedProvider] = useState('anthropic')
  const [selectedModel, setSelectedModel] = useState('claude-haiku-4-5')
  const [runningTests, setRunningTests] = useState({
    current: null,
    total: 0,
    completed: 0,
    status: 'idle'
  })

  useEffect(() => {
    loadTestFiles()
    loadModels()
  }, [])

  // Load previously selected test file after test data is loaded
  useEffect(() => {
    if (testData.files || testData.folders) {
      const savedPath = localStorage.getItem('selectedTestFile')
      if (savedPath) {
        loadTestFile(savedPath)
      }
    }
  }, [testData])

  const loadModels = async () => {
    try {
      const res = await fetch('/api/models')
      const data = await res.json()
      setModels(data)
    } catch (error) {
      console.error('Failed to load models:', error)
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

    // Initialize running tests state
    const totalTests = selectedFile.test_count || 1
    setRunningTests({
      current: 'Initializing...',
      total: totalTests,
      completed: 0,
      status: 'running'
    })

    try {
      const res = await fetch('/api/tests/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_path: selectedFile.path,
          model: selectedModel,
          provider: selectedProvider,
        }),
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      console.log('Test results received:', data)
      setTestResults(data)
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
    <div className="h-full flex">
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
                <select
                  value={selectedProvider}
                  onChange={(e) => {
                    setSelectedProvider(e.target.value)
                    const providerModels = models[e.target.value]
                    if (providerModels && providerModels.length > 0) {
                      setSelectedModel(providerModels[0].id)
                    }
                  }}
                  className="input text-sm min-w-[120px]"
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
                  className="input text-sm min-w-[160px]"
                >
                  {(models[selectedProvider] || []).map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={runTests}
                  disabled={running}
                  className="btn btn-primary"
                >
                  <Play size={16} />
                  <span>{running ? 'Running...' : 'Run Tests'}</span>
                </button>
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
                  options={{
                    readOnly: !editMode,
                    minimap: { enabled: false },
                    fontSize: 14,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
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
  )
}

export default TestManager
