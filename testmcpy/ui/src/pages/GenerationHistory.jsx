import React, { useState, useEffect, useMemo } from 'react'
import {
  History,
  Clock,
  DollarSign,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  FileText,
  Cpu,
  RefreshCw,
  Filter,
  X,
  Eye,
  Trash2,
  Copy,
  Code2,
  MessageSquare,
  Sparkles,
  AlertTriangle,
  Terminal,
  Wrench
} from 'lucide-react'
import Editor from '@monaco-editor/react'

function GenerationHistory() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)
  const [logDetails, setLogDetails] = useState(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [expandedSection, setExpandedSection] = useState('logs') // 'logs', 'analysis', 'prompts', 'yaml'

  // Filters
  const [filterTool, setFilterTool] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterModel, setFilterModel] = useState('')

  useEffect(() => {
    loadLogs()
  }, [])

  const loadLogs = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/generation-logs/list?limit=100')
      if (!res.ok) throw new Error('Failed to load generation logs')
      const data = await res.json()
      setLogs(data.logs || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const loadLogDetails = async (logId) => {
    setLoadingDetails(true)
    try {
      const res = await fetch(`/api/generation-logs/log/${logId}`)
      if (!res.ok) throw new Error('Failed to load log details')
      const data = await res.json()
      setLogDetails(data)
      setSelectedLog(logId)
      setExpandedSection('logs')
    } catch (err) {
      console.error('Failed to load log details:', err)
    } finally {
      setLoadingDetails(false)
    }
  }

  const deleteLog = async (logId) => {
    if (!confirm('Delete this generation log?')) return
    try {
      await fetch(`/api/generation-logs/log/${logId}`, { method: 'DELETE' })
      setLogs(logs.filter(l => l.log_id !== logId))
      if (selectedLog === logId) {
        setSelectedLog(null)
        setLogDetails(null)
      }
    } catch (err) {
      console.error('Failed to delete log:', err)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
  }

  // Get unique values for filters
  const filterOptions = useMemo(() => {
    const tools = [...new Set(logs.map(l => l.tool_name))].filter(Boolean)
    const models = [...new Set(logs.map(l => l.model))].filter(Boolean)
    return { tools, models }
  }, [logs])

  // Apply filters
  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      if (filterTool && log.tool_name !== filterTool) return false
      if (filterModel && log.model !== filterModel) return false
      if (filterStatus === 'success' && !log.success) return false
      if (filterStatus === 'failed' && log.success) return false
      return true
    })
  }, [logs, filterTool, filterModel, filterStatus])

  // Summary stats
  const stats = useMemo(() => {
    if (filteredLogs.length === 0) return null

    const totalRuns = filteredLogs.length
    const successCount = filteredLogs.filter(l => l.success).length
    const failedCount = totalRuns - successCount
    const totalCost = filteredLogs.reduce((sum, l) => sum + (l.total_cost || 0), 0)
    const totalTests = filteredLogs.reduce((sum, l) => sum + (l.test_count || 0), 0)

    return {
      totalRuns,
      successCount,
      failedCount,
      totalCost,
      totalTests,
      successRate: totalRuns > 0 ? (successCount / totalRuns * 100) : 0
    }
  }, [filteredLogs])

  const formatTimestamp = (ts) => {
    if (!ts) return '-'
    const date = new Date(ts)
    return date.toLocaleString()
  }

  const formatCost = (cost) => {
    if (!cost) return '$0.0000'
    return `$${cost.toFixed(4)}`
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <History size={24} className="text-purple-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-text-primary">Generation History</h1>
              <p className="text-sm text-text-tertiary">View all test generation runs with prompts and responses</p>
            </div>
          </div>
          <button
            onClick={loadLogs}
            className="btn btn-ghost"
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="flex-shrink-0 px-6 py-3 border-b border-border bg-surface">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <History size={16} className="text-text-tertiary" />
              <span className="text-sm text-text-tertiary">Runs:</span>
              <span className="font-semibold text-text-primary">{stats.totalRuns}</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle2 size={16} className="text-green-400" />
              <span className="text-sm text-text-tertiary">Success:</span>
              <span className="font-semibold text-green-400">{stats.successCount}</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle size={16} className="text-red-400" />
              <span className="text-sm text-text-tertiary">Failed:</span>
              <span className="font-semibold text-red-400">{stats.failedCount}</span>
            </div>
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-blue-400" />
              <span className="text-sm text-text-tertiary">Tests Generated:</span>
              <span className="font-semibold text-blue-400">{stats.totalTests}</span>
            </div>
            <div className="flex items-center gap-2">
              <DollarSign size={16} className="text-yellow-400" />
              <span className="text-sm text-text-tertiary">Total Cost:</span>
              <span className="font-semibold text-yellow-400">{formatCost(stats.totalCost)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-border bg-surface-elevated/50">
        <div className="flex items-center gap-4">
          <Filter size={16} className="text-text-tertiary" />

          <select
            value={filterTool}
            onChange={(e) => setFilterTool(e.target.value)}
            className="input text-sm py-1.5"
          >
            <option value="">All Tools</option>
            {filterOptions.tools.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <select
            value={filterModel}
            onChange={(e) => setFilterModel(e.target.value)}
            className="input text-sm py-1.5"
          >
            <option value="">All Models</option>
            {filterOptions.models.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="input text-sm py-1.5"
          >
            <option value="">All Status</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
          </select>

          {(filterTool || filterModel || filterStatus) && (
            <button
              onClick={() => {
                setFilterTool('')
                setFilterModel('')
                setFilterStatus('')
              }}
              className="btn btn-ghost text-sm py-1"
            >
              <X size={14} />
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Log List */}
        <div className="w-96 flex-shrink-0 border-r border-border overflow-auto bg-surface-elevated">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : error ? (
            <div className="p-4 text-center text-error">
              <AlertTriangle size={32} className="mx-auto mb-2" />
              <p>{error}</p>
            </div>
          ) : filteredLogs.length === 0 ? (
            <div className="p-8 text-center">
              <History size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
              <p className="text-text-tertiary">No generation logs found</p>
              <p className="text-text-disabled text-sm mt-1">Generate tests to see history here</p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filteredLogs.map(log => (
                <div
                  key={log.log_id}
                  className={`p-4 cursor-pointer transition-colors group ${
                    selectedLog === log.log_id
                      ? 'bg-primary/10 border-l-2 border-l-primary'
                      : 'hover:bg-surface border-l-2 border-l-transparent'
                  }`}
                  onClick={() => loadLogDetails(log.log_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {log.success ? (
                          <CheckCircle2 size={14} className="text-green-400 flex-shrink-0" />
                        ) : (
                          <XCircle size={14} className="text-red-400 flex-shrink-0" />
                        )}
                        <span className="font-medium text-text-primary truncate">
                          {log.tool_name}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs px-1.5 py-0.5 rounded bg-surface text-text-tertiary">
                          {log.coverage_level}
                        </span>
                        <span className="text-xs text-text-tertiary">
                          {log.test_count || 0} tests
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-2 text-xs text-text-disabled">
                        <span className="flex items-center gap-1">
                          <Cpu size={10} />
                          {log.model?.split('-').slice(-2).join('-') || log.model}
                        </span>
                        <span>{formatCost(log.total_cost)}</span>
                      </div>
                      <div className="text-xs text-text-disabled mt-1">
                        {formatTimestamp(log.timestamp)}
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteLog(log.log_id)
                      }}
                      className="p-1 hover:bg-error/20 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Trash2 size={14} className="text-error" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Log Details */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin text-primary" size={32} />
            </div>
          ) : !logDetails ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Eye size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
                <p className="text-text-tertiary">Select a log to view details</p>
              </div>
            </div>
          ) : (
            <>
              {/* Detail Header */}
              <div className="flex-shrink-0 px-6 py-4 border-b border-border bg-surface-elevated">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <Wrench size={18} className="text-primary" />
                      <h2 className="text-lg font-semibold text-text-primary">
                        {logDetails.metadata?.tool_name}
                      </h2>
                      {logDetails.metadata?.success ? (
                        <span className="px-2 py-0.5 text-xs rounded bg-green-500/20 text-green-400">Success</span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded bg-red-500/20 text-red-400">Failed</span>
                      )}
                    </div>
                    <p className="text-sm text-text-tertiary mt-1">
                      {logDetails.metadata?.coverage_level} coverage | {logDetails.metadata?.test_count || 0} tests | {formatCost(logDetails.metadata?.total_cost)}
                    </p>
                  </div>
                  <div className="text-sm text-text-tertiary">
                    {formatTimestamp(logDetails.metadata?.timestamp)}
                  </div>
                </div>

                {/* Section Tabs */}
                <div className="flex items-center gap-2 mt-4">
                  <button
                    onClick={() => setExpandedSection('logs')}
                    className={`px-3 py-1.5 text-sm rounded-lg flex items-center gap-2 transition-colors ${
                      expandedSection === 'logs'
                        ? 'bg-primary text-white'
                        : 'bg-surface hover:bg-surface-hover text-text-secondary'
                    }`}
                  >
                    <Terminal size={14} />
                    Logs ({logDetails.logs?.length || 0})
                  </button>
                  <button
                    onClick={() => setExpandedSection('prompts')}
                    className={`px-3 py-1.5 text-sm rounded-lg flex items-center gap-2 transition-colors ${
                      expandedSection === 'prompts'
                        ? 'bg-primary text-white'
                        : 'bg-surface hover:bg-surface-hover text-text-secondary'
                    }`}
                  >
                    <MessageSquare size={14} />
                    LLM Calls ({logDetails.llm_calls?.length || 0})
                  </button>
                  <button
                    onClick={() => setExpandedSection('analysis')}
                    className={`px-3 py-1.5 text-sm rounded-lg flex items-center gap-2 transition-colors ${
                      expandedSection === 'analysis'
                        ? 'bg-primary text-white'
                        : 'bg-surface hover:bg-surface-hover text-text-secondary'
                    }`}
                  >
                    <Sparkles size={14} />
                    Analysis
                  </button>
                  <button
                    onClick={() => setExpandedSection('yaml')}
                    className={`px-3 py-1.5 text-sm rounded-lg flex items-center gap-2 transition-colors ${
                      expandedSection === 'yaml'
                        ? 'bg-primary text-white'
                        : 'bg-surface hover:bg-surface-hover text-text-secondary'
                    }`}
                  >
                    <Code2 size={14} />
                    Generated YAML
                  </button>
                </div>
              </div>

              {/* Section Content */}
              <div className="flex-1 overflow-auto p-4">
                {/* Logs Section */}
                {expandedSection === 'logs' && (
                  <div className="space-y-1 font-mono text-sm bg-gray-950 rounded-lg p-4">
                    {logDetails.logs?.map((log, idx) => (
                      <div
                        key={idx}
                        className={`py-0.5 ${
                          log.includes('ERROR') || log.includes('Failed') ? 'text-red-400' :
                          log.includes('✓') || log.includes('Complete') ? 'text-green-400' :
                          log.includes('Sending') || log.includes('Analyzing') ? 'text-yellow-400' :
                          log.includes('Tool:') || log.includes('Using') ? 'text-blue-400' :
                          'text-gray-300'
                        }`}
                      >
                        {log}
                      </div>
                    ))}
                    {(!logDetails.logs || logDetails.logs.length === 0) && (
                      <div className="text-gray-500 text-center py-4">No logs recorded</div>
                    )}
                  </div>
                )}

                {/* LLM Calls Section */}
                {expandedSection === 'prompts' && (
                  <div className="space-y-6">
                    {logDetails.llm_calls?.map((call, idx) => (
                      <div key={idx} className="border border-border rounded-lg overflow-hidden">
                        <div className="px-4 py-3 bg-surface-elevated flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className="px-2 py-1 text-xs font-medium rounded bg-blue-500/20 text-blue-400 uppercase">
                              {call.step}
                            </span>
                            <span className="text-sm text-text-secondary">
                              {call.duration?.toFixed(1)}s | {formatCost(call.cost)}
                            </span>
                          </div>
                          <span className="text-xs text-text-tertiary">{formatTimestamp(call.timestamp)}</span>
                        </div>

                        {/* Prompt */}
                        <div className="border-t border-border">
                          <div className="px-4 py-2 bg-surface flex items-center justify-between">
                            <span className="text-xs font-medium text-text-tertiary uppercase">Prompt</span>
                            <button
                              onClick={() => copyToClipboard(call.prompt)}
                              className="p-1 hover:bg-surface-hover rounded"
                              title="Copy prompt"
                            >
                              <Copy size={12} className="text-text-tertiary" />
                            </button>
                          </div>
                          <div className="max-h-64 overflow-auto">
                            <pre className="p-4 text-xs text-text-secondary whitespace-pre-wrap bg-gray-950">{call.prompt}</pre>
                          </div>
                        </div>

                        {/* Response */}
                        <div className="border-t border-border">
                          <div className="px-4 py-2 bg-surface flex items-center justify-between">
                            <span className="text-xs font-medium text-text-tertiary uppercase">Response</span>
                            <button
                              onClick={() => copyToClipboard(call.response)}
                              className="p-1 hover:bg-surface-hover rounded"
                              title="Copy response"
                            >
                              <Copy size={12} className="text-text-tertiary" />
                            </button>
                          </div>
                          <div className="max-h-64 overflow-auto">
                            <pre className="p-4 text-xs text-text-secondary whitespace-pre-wrap bg-gray-950">{call.response}</pre>
                          </div>
                        </div>
                      </div>
                    ))}
                    {(!logDetails.llm_calls || logDetails.llm_calls.length === 0) && (
                      <div className="text-center py-8 text-text-tertiary">No LLM calls recorded</div>
                    )}
                  </div>
                )}

                {/* Analysis Section */}
                {expandedSection === 'analysis' && (
                  <div className="space-y-4">
                    {logDetails.analysis ? (
                      <>
                        {/* Test Scenarios */}
                        {logDetails.analysis.test_scenarios && (
                          <div className="border border-border rounded-lg p-4">
                            <h3 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                              <FileText size={14} />
                              Test Scenarios ({logDetails.analysis.test_scenarios.length})
                            </h3>
                            <div className="space-y-2">
                              {logDetails.analysis.test_scenarios.map((scenario, idx) => (
                                <div key={idx} className="flex items-start gap-3 p-3 bg-surface rounded-lg">
                                  <span className={`px-1.5 py-0.5 text-[10px] rounded uppercase ${
                                    scenario.priority === 'high' ? 'bg-red-500/20 text-red-400' :
                                    scenario.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                    'bg-blue-500/20 text-blue-400'
                                  }`}>
                                    {scenario.priority}
                                  </span>
                                  <div>
                                    <p className="text-sm font-medium text-text-primary">{scenario.name}</p>
                                    <p className="text-xs text-text-tertiary mt-1">{scenario.description}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Key Parameters */}
                        {logDetails.analysis.key_parameters?.length > 0 && (
                          <div className="border border-border rounded-lg p-4">
                            <h3 className="text-sm font-medium text-text-primary mb-3">Key Parameters</h3>
                            <div className="flex flex-wrap gap-2">
                              {logDetails.analysis.key_parameters.map((param, idx) => (
                                <span key={idx} className="px-2 py-1 text-xs rounded bg-surface text-text-secondary">
                                  {param}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Edge Cases */}
                        {logDetails.analysis.edge_cases?.length > 0 && (
                          <div className="border border-border rounded-lg p-4">
                            <h3 className="text-sm font-medium text-text-primary mb-3">Edge Cases</h3>
                            <ul className="list-disc list-inside space-y-1 text-sm text-text-secondary">
                              {logDetails.analysis.edge_cases.map((edge, idx) => (
                                <li key={idx}>{edge}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Validation Points */}
                        {logDetails.analysis.validation_points?.length > 0 && (
                          <div className="border border-border rounded-lg p-4">
                            <h3 className="text-sm font-medium text-text-primary mb-3">Validation Points</h3>
                            <ul className="list-disc list-inside space-y-1 text-sm text-text-secondary">
                              {logDetails.analysis.validation_points.map((point, idx) => (
                                <li key={idx}>{point}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-8 text-text-tertiary">No analysis data available</div>
                    )}
                  </div>
                )}

                {/* Generated YAML Section */}
                {expandedSection === 'yaml' && (
                  <div className="h-full">
                    {logDetails.generated_yaml ? (
                      <div className="h-full border border-border rounded-lg overflow-hidden">
                        <div className="px-4 py-2 bg-surface-elevated flex items-center justify-between">
                          <span className="text-sm font-medium text-text-primary">Generated Test File</span>
                          <button
                            onClick={() => copyToClipboard(logDetails.generated_yaml)}
                            className="btn btn-ghost text-xs py-1"
                          >
                            <Copy size={12} />
                            Copy
                          </button>
                        </div>
                        <Editor
                          height="500px"
                          defaultLanguage="yaml"
                          theme="vs-dark"
                          value={logDetails.generated_yaml}
                          options={{
                            readOnly: true,
                            minimap: { enabled: false },
                            fontSize: 13,
                            lineNumbers: 'on',
                            scrollBeyondLastLine: false,
                          }}
                        />
                      </div>
                    ) : (
                      <div className="text-center py-8 text-text-tertiary">No YAML generated</div>
                    )}
                  </div>
                )}

                {/* Error Display */}
                {logDetails.metadata?.error && (
                  <div className="mt-4 p-4 border border-red-500/30 rounded-lg bg-red-500/10">
                    <div className="flex items-center gap-2 text-red-400 mb-2">
                      <AlertTriangle size={16} />
                      <span className="font-medium">Error</span>
                    </div>
                    <pre className="text-sm text-red-300 whitespace-pre-wrap">{logDetails.metadata.error}</pre>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default GenerationHistory
