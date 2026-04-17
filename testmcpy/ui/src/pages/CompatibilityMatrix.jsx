import React, { useState, useEffect } from 'react'
import { Grid3X3, Play, AlertCircle, Check, X, Minus, RefreshCw } from 'lucide-react'
import MCPProfileSelector from '../components/MCPProfileSelector'

function CompatibilityMatrix() {
  const [selectedProfiles, setSelectedProfiles] = useState([])
  const [toolNames, setToolNames] = useState('')
  const [autoDiscover, setAutoDiscover] = useState(true)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Auto-discover tools from the first selected profile
  const discoverTools = async () => {
    if (selectedProfiles.length === 0) return

    try {
      const params = new URLSearchParams()
      params.append('profiles', selectedProfiles[0])
      const res = await fetch(`/api/mcp/tools?${params.toString()}`)
      if (res.ok) {
        const tools = await res.json()
        const names = tools.map(t => t.name).join('\n')
        setToolNames(names)
      }
    } catch (err) {
      console.error('Failed to discover tools:', err)
    }
  }

  useEffect(() => {
    if (autoDiscover && selectedProfiles.length > 0) {
      discoverTools()
    }
  }, [selectedProfiles, autoDiscover])

  const runMatrix = async () => {
    const names = toolNames.split('\n').map(s => s.trim()).filter(s => s)
    if (selectedProfiles.length < 2) {
      setError('Select at least 2 MCP profiles')
      return
    }
    if (names.length === 0) {
      setError('Enter at least 1 tool name')
      return
    }

    setLoading(true)
    setError(null)
    setResults(null)

    try {
      const res = await fetch('/api/compatibility/matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profiles: selectedProfiles,
          tool_names: names,
        }),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Matrix test failed')
      }

      const data = await res.json()
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pass':
        return <Check size={16} className="text-success" />
      case 'fail':
        return <X size={16} className="text-error" />
      case 'missing':
        return <Minus size={16} className="text-text-tertiary" />
      case 'error':
        return <AlertCircle size={16} className="text-warning" />
      default:
        return <Minus size={16} className="text-text-disabled" />
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'pass': return 'bg-success/10 border-success/30'
      case 'fail': return 'bg-error/10 border-error/30'
      case 'missing': return 'bg-surface border-border'
      case 'error': return 'bg-warning/10 border-warning/30'
      default: return 'bg-surface border-border'
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center gap-3">
          <Grid3X3 size={24} className="text-primary" />
          <div>
            <h1 className="text-xl md:text-2xl font-bold">Compatibility Matrix</h1>
            <p className="text-text-secondary mt-1 text-sm md:text-base">
              Test tools across multiple MCP servers and compare schemas
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 bg-background-subtle">
        <div className="max-w-6xl mx-auto">
          {/* Configuration */}
          <div className="bg-surface-elevated border border-border rounded-lg p-6 mb-6">
            <h3 className="font-bold text-lg mb-4">Configuration</h3>

            <div className="mb-4">
              <label className="block text-sm font-medium mb-1">
                MCP Profiles (select 2 or more)
              </label>
              <MCPProfileSelector
                selectedProfiles={selectedProfiles}
                onChange={setSelectedProfiles}
                multiple={true}
              />
              {selectedProfiles.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {selectedProfiles.map((p, idx) => (
                    <span key={idx} className="px-2 py-0.5 text-xs bg-primary/10 text-primary rounded border border-primary/20">
                      {p.split(':')[1] || p}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium">Tool Names (one per line)</label>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                    <input
                      type="checkbox"
                      checked={autoDiscover}
                      onChange={(e) => setAutoDiscover(e.target.checked)}
                      className="w-3.5 h-3.5"
                    />
                    Auto-discover from first profile
                  </label>
                  {selectedProfiles.length > 0 && (
                    <button
                      onClick={discoverTools}
                      className="text-xs text-primary hover:underline flex items-center gap-1"
                    >
                      <RefreshCw size={12} />
                      Refresh
                    </button>
                  )}
                </div>
              </div>
              <textarea
                value={toolNames}
                onChange={(e) => setToolNames(e.target.value)}
                className="input w-full font-mono text-sm"
                rows={6}
                placeholder="list_charts&#10;get_chart_info&#10;execute_sql"
              />
              <p className="text-text-tertiary text-xs mt-1">
                {toolNames.split('\n').filter(s => s.trim()).length} tool(s) configured
              </p>
            </div>

            {error && (
              <div className="bg-error/10 border border-error/30 rounded p-3 mb-4 flex items-center gap-2">
                <AlertCircle size={16} className="text-error flex-shrink-0" />
                <span className="text-sm text-error">{error}</span>
              </div>
            )}

            <button
              onClick={runMatrix}
              disabled={loading || selectedProfiles.length < 2}
              className="btn btn-primary flex items-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Running Matrix...
                </>
              ) : (
                <>
                  <Play size={16} />
                  Run Compatibility Matrix
                </>
              )}
            </button>
          </div>

          {/* Results */}
          {results && (
            <div className="bg-surface-elevated border border-border rounded-lg p-6">
              <h3 className="font-bold text-lg mb-4">Results</h3>

              {/* Matrix Grid */}
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <th className="text-left text-sm font-medium p-2 border-b border-border min-w-[200px]">
                        Tool
                      </th>
                      {results.profiles.map((profile) => (
                        <th key={profile} className="text-center text-xs font-medium p-2 border-b border-border min-w-[120px]">
                          <div className="truncate" title={profile}>
                            {profile.split(':')[1] || profile}
                          </div>
                          <div className="text-text-tertiary font-normal truncate">
                            {profile.split(':')[0]}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {results.tool_names.map((toolName) => (
                      <tr key={toolName} className="hover:bg-surface-hover">
                        <td className="text-sm font-mono p-2 border-b border-border">
                          {toolName}
                        </td>
                        {results.profiles.map((profile) => {
                          const cell = results.matrix[toolName]?.[profile] || { status: 'unknown' }
                          return (
                            <td key={profile} className="p-2 border-b border-border text-center">
                              <div
                                className={`inline-flex items-center justify-center gap-1.5 px-2 py-1 rounded border ${getStatusColor(cell.status)}`}
                                title={cell.error || cell.status}
                              >
                                {getStatusIcon(cell.status)}
                                <span className="text-xs capitalize">{cell.status}</span>
                              </div>
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Legend */}
              <div className="mt-4 pt-4 border-t border-border flex flex-wrap gap-4 text-xs text-text-secondary">
                <div className="flex items-center gap-1.5">
                  <Check size={14} className="text-success" />
                  <span>Pass - tool exists and schema matches</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <X size={14} className="text-error" />
                  <span>Fail - schema mismatch</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Minus size={14} className="text-text-tertiary" />
                  <span>Missing - tool not found</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <AlertCircle size={14} className="text-warning" />
                  <span>Error - connection issue</span>
                </div>
              </div>

              <div className="mt-3 text-xs text-text-tertiary">
                Reference profile: <span className="font-medium">{results.reference_profile}</span> (schemas compared against this)
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default CompatibilityMatrix
