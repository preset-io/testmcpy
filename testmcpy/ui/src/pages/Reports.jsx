import React, { useState, useEffect } from 'react'
import {
  FileText,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Trash2,
  Server,
  Cpu,
  Zap,
  Filter,
  Calendar
} from 'lucide-react'

function Reports() {
  const [activeTab, setActiveTab] = useState('tests') // 'tests' or 'smoke'
  const [testRuns, setTestRuns] = useState([])
  const [smokeReports, setSmokeReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetails, setRunDetails] = useState(null)
  const [loadingDetails, setLoadingDetails] = useState(false)

  useEffect(() => {
    loadAllReports()
  }, [])

  const loadAllReports = async () => {
    setLoading(true)
    await Promise.all([loadTestRuns(), loadSmokeReports()])
    setLoading(false)
  }

  const loadTestRuns = async () => {
    try {
      const res = await fetch('/api/results/list?limit=50')
      if (res.ok) {
        const data = await res.json()
        setTestRuns(data.runs || [])
      }
    } catch (error) {
      console.error('Failed to load test runs:', error)
    }
  }

  const loadSmokeReports = async () => {
    try {
      const res = await fetch('/api/smoke-reports/list?limit=50')
      if (res.ok) {
        const data = await res.json()
        setSmokeReports(data.reports || [])
      }
    } catch (error) {
      console.error('Failed to load smoke reports:', error)
    }
  }

  const loadRunDetails = async (runId, type) => {
    setLoadingDetails(true)
    setSelectedRun({ id: runId, type })
    try {
      const endpoint = type === 'tests'
        ? `/api/results/run/${runId}`
        : `/api/smoke-reports/report/${runId}`
      const res = await fetch(endpoint)
      if (res.ok) {
        const data = await res.json()
        setRunDetails(data)
      }
    } catch (error) {
      console.error('Failed to load run details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const deleteRun = async (runId, type) => {
    if (!confirm('Delete this report?')) return
    try {
      const endpoint = type === 'tests'
        ? `/api/results/run/${runId}`
        : `/api/smoke-reports/report/${runId}`
      await fetch(endpoint, { method: 'DELETE' })
      if (type === 'tests') {
        setTestRuns(testRuns.filter(r => r.run_id !== runId))
      } else {
        setSmokeReports(smokeReports.filter(r => r.report_id !== runId))
      }
      if (selectedRun?.id === runId) {
        setSelectedRun(null)
        setRunDetails(null)
      }
    } catch (error) {
      console.error('Failed to delete:', error)
    }
  }

  const formatDate = (timestamp) => {
    if (!timestamp) return '-'
    const date = new Date(timestamp)
    return date.toLocaleString()
  }

  const formatDuration = (seconds) => {
    if (!seconds) return '0s'
    if (seconds < 0.1) return `${(seconds * 1000).toFixed(0)}ms`
    return `${seconds.toFixed(1)}s`
  }

  const formatCost = (cost) => {
    if (!cost) return '$0.00'
    return `$${cost.toFixed(4)}`
  }

  const getPassRate = (passed, total) => {
    if (!total) return 0
    return (passed / total * 100).toFixed(0)
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <FileText size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-text-primary">Reports</h1>
              <p className="text-sm text-text-tertiary">View all test results and smoke test reports</p>
            </div>
          </div>
          <button
            onClick={loadAllReports}
            className="btn btn-ghost"
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-2 mt-4">
          <button
            onClick={() => setActiveTab('tests')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'tests'
                ? 'bg-primary text-white'
                : 'bg-surface hover:bg-surface-hover text-text-secondary'
            }`}
          >
            <FileText size={16} />
            Test Runs
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === 'tests' ? 'bg-white/20' : 'bg-surface-elevated'
            }`}>
              {testRuns.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('smoke')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'smoke'
                ? 'bg-primary text-white'
                : 'bg-surface hover:bg-surface-hover text-text-secondary'
            }`}
          >
            <Zap size={16} />
            Smoke Tests
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === 'smoke' ? 'bg-white/20' : 'bg-surface-elevated'
            }`}>
              {smokeReports.length}
            </span>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* List Panel */}
        <div className="w-96 flex-shrink-0 border-r border-border overflow-auto bg-surface-elevated">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : activeTab === 'tests' ? (
            // Test Runs List
            testRuns.length === 0 ? (
              <div className="p-8 text-center">
                <FileText size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">No test runs found</p>
                <p className="text-text-disabled text-sm mt-1">Run some tests to see results here</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {testRuns.map((run) => (
                  <div
                    key={run.run_id}
                    className={`p-4 cursor-pointer transition-colors group ${
                      selectedRun?.id === run.run_id
                        ? 'bg-primary/10 border-l-2 border-l-primary'
                        : 'hover:bg-surface border-l-2 border-l-transparent'
                    }`}
                    onClick={() => loadRunDetails(run.run_id, 'tests')}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {run.failed === 0 ? (
                            <CheckCircle size={14} className="text-success flex-shrink-0" />
                          ) : (
                            <XCircle size={14} className="text-error flex-shrink-0" />
                          )}
                          <span className="font-medium text-text-primary truncate">
                            {run.test_file}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            run.failed === 0 ? 'bg-success/20 text-success' : 'bg-error/20 text-error'
                          }`}>
                            {run.passed}/{run.total_tests} passed
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-xs text-text-disabled">
                          <span className="flex items-center gap-1">
                            <Cpu size={10} />
                            {run.model?.split('-').slice(-2).join('-') || run.model}
                          </span>
                          <span>{formatCost(run.total_cost)}</span>
                        </div>
                        <div className="text-xs text-text-disabled mt-1">
                          {formatDate(run.timestamp)}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          deleteRun(run.run_id, 'tests')
                        }}
                        className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 size={14} className="text-error" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            // Smoke Reports List
            smokeReports.length === 0 ? (
              <div className="p-8 text-center">
                <Zap size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">No smoke test reports found</p>
                <p className="text-text-disabled text-sm mt-1">Run a smoke test to see results here</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {smokeReports.map((report) => (
                  <div
                    key={report.report_id}
                    className={`p-4 cursor-pointer transition-colors group ${
                      selectedRun?.id === report.report_id
                        ? 'bg-primary/10 border-l-2 border-l-primary'
                        : 'hover:bg-surface border-l-2 border-l-transparent'
                    }`}
                    onClick={() => loadRunDetails(report.report_id, 'smoke')}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {report.failed === 0 ? (
                            <CheckCircle size={14} className="text-success flex-shrink-0" />
                          ) : (
                            <XCircle size={14} className="text-error flex-shrink-0" />
                          )}
                          <span className="font-medium text-text-primary truncate">
                            {report.profile_id || 'Smoke Test'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            report.failed === 0 ? 'bg-success/20 text-success' : 'bg-error/20 text-error'
                          }`}>
                            {report.passed}/{report.total_tests} passed
                          </span>
                          <span className="text-xs text-text-tertiary">
                            {report.success_rate?.toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-xs text-text-disabled">
                          <span className="flex items-center gap-1">
                            <Server size={10} />
                            {report.server_url?.split('/').pop() || 'MCP Server'}
                          </span>
                          <span>{formatDuration(report.duration_ms / 1000)}</span>
                        </div>
                        <div className="text-xs text-text-disabled mt-1">
                          {formatDate(report.timestamp)}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          deleteRun(report.report_id, 'smoke')
                        }}
                        className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 size={14} className="text-error" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        {/* Details Panel */}
        <div className="flex-1 overflow-auto bg-background">
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : !runDetails ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <FileText size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">Select a report to view details</p>
              </div>
            </div>
          ) : selectedRun?.type === 'tests' ? (
            // Test Run Details
            <div className="p-6">
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-text-primary">{runDetails.metadata?.test_file}</h2>
                <div className="flex items-center gap-4 mt-2 text-sm text-text-secondary">
                  <span className="flex items-center gap-1">
                    <Cpu size={14} />
                    {runDetails.metadata?.provider} / {runDetails.metadata?.model}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={14} />
                    {formatDuration(runDetails.metadata?.total_duration)}
                  </span>
                  <span className="flex items-center gap-1">
                    <DollarSign size={14} />
                    {formatCost(runDetails.metadata?.total_cost)}
                  </span>
                </div>
              </div>

              {/* Summary */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="p-4 rounded-lg bg-surface border border-border">
                  <p className="text-xs text-text-tertiary uppercase">Total Tests</p>
                  <p className="text-2xl font-bold">{runDetails.metadata?.total_tests}</p>
                </div>
                <div className="p-4 rounded-lg bg-success/10 border border-success/30">
                  <p className="text-xs text-success uppercase">Passed</p>
                  <p className="text-2xl font-bold text-success">{runDetails.metadata?.passed}</p>
                </div>
                <div className="p-4 rounded-lg bg-error/10 border border-error/30">
                  <p className="text-xs text-error uppercase">Failed</p>
                  <p className="text-2xl font-bold text-error">{runDetails.metadata?.failed}</p>
                </div>
              </div>

              {/* Individual Results */}
              <h3 className="font-semibold mb-3">Test Results</h3>
              <div className="space-y-2">
                {runDetails.results?.map((result, idx) => (
                  <TestResultCard key={idx} result={result} />
                ))}
              </div>
            </div>
          ) : (
            // Smoke Test Details
            <div className="p-6">
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-text-primary">Smoke Test Report</h2>
                <div className="flex items-center gap-4 mt-2 text-sm text-text-secondary">
                  <span className="flex items-center gap-1">
                    <Server size={14} />
                    {runDetails.server_url}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={14} />
                    {formatDuration(runDetails.duration_ms / 1000)}
                  </span>
                </div>
              </div>

              {/* Summary */}
              <div className={`p-4 rounded-lg border mb-6 ${
                runDetails.failed === 0
                  ? 'bg-success/10 border-success/30'
                  : 'bg-error/10 border-error/30'
              }`}>
                <div className="flex items-center gap-3">
                  <span className={`text-2xl ${runDetails.failed === 0 ? 'text-success' : 'text-error'}`}>
                    {runDetails.failed === 0 ? '✓' : '✗'}
                  </span>
                  <div>
                    <h3 className="font-bold">
                      {runDetails.failed === 0 ? 'All Tests Passed' : `${runDetails.passed}/${runDetails.total_tests} Passed`}
                    </h3>
                    <p className="text-sm text-text-secondary">
                      Success Rate: {runDetails.success_rate?.toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>

              {/* Individual Results */}
              <h3 className="font-semibold mb-3">Test Details</h3>
              <div className="space-y-2">
                {runDetails.results?.map((result, idx) => (
                  <SmokeTestResultCard key={idx} result={result} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Test Result Card Component
function TestResultCard({ result }) {
  const [expanded, setExpanded] = useState(!result.passed)

  return (
    <div className={`border rounded-lg overflow-hidden ${
      result.passed ? 'border-border' : 'border-error/30'
    }`}>
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {result.passed ? (
            <CheckCircle size={16} className="text-success" />
          ) : (
            <XCircle size={16} className="text-error" />
          )}
          <span className="font-medium">{result.test_name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-tertiary">
          <span>{result.duration?.toFixed(2)}s</span>
          {result.cost > 0 && <span>${result.cost?.toFixed(4)}</span>}
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 border-t border-border bg-surface-elevated">
          {result.reason && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-1">Result</p>
              <p className="text-sm">{result.reason}</p>
            </div>
          )}

          {result.error && (
            <div className="mt-3 p-2 bg-error/10 border border-error/30 rounded">
              <p className="text-xs font-medium text-error mb-1">Error</p>
              <p className="text-sm text-error">{result.error}</p>
            </div>
          )}

          {result.evaluations && result.evaluations.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-2">Evaluations</p>
              <div className="space-y-1">
                {result.evaluations.map((evalItem, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-sm">
                    {evalItem.passed ? (
                      <CheckCircle size={12} className="text-success" />
                    ) : (
                      <XCircle size={12} className="text-error" />
                    )}
                    <span className={evalItem.passed ? 'text-text-secondary' : 'text-error'}>
                      {evalItem.evaluator || evalItem.name || 'Unknown Evaluator'}
                    </span>
                    {evalItem.score !== undefined && (
                      <span className="text-xs text-text-tertiary">
                        ({(evalItem.score * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Smoke Test Result Card Component
function SmokeTestResultCard({ result }) {
  const [expanded, setExpanded] = useState(!result.success)

  return (
    <div className={`border rounded-lg overflow-hidden ${
      result.success ? 'border-border' : 'border-error/30'
    }`}>
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {result.success ? (
            <CheckCircle size={16} className="text-success" />
          ) : (
            <XCircle size={16} className="text-error" />
          )}
          <span className="font-medium">{result.test_name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-tertiary">
          <span>{result.duration_ms?.toFixed(0)}ms</span>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 border-t border-border bg-surface-elevated">
          {result.error_message && (
            <div className="mt-3 p-2 bg-error/10 border border-error/30 rounded">
              <p className="text-xs font-medium text-error mb-1">Error</p>
              <p className="text-sm text-error">{result.error_message}</p>
            </div>
          )}

          {result.tool_input && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-1">Input</p>
              <pre className="text-xs bg-surface p-2 rounded border border-border overflow-x-auto max-h-32">
                {JSON.stringify(result.tool_input, null, 2)}
              </pre>
            </div>
          )}

          {result.tool_output !== undefined && result.tool_output !== null && (
            <div className="mt-3">
              <p className="text-xs font-medium text-text-secondary mb-1">Output</p>
              <pre className="text-xs bg-surface p-2 rounded border border-border overflow-x-auto max-h-48">
                {typeof result.tool_output === 'string'
                  ? result.tool_output.substring(0, 2000)
                  : JSON.stringify(result.tool_output, null, 2)?.substring(0, 2000)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default Reports
