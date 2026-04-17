import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Heart,
  Server,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  RefreshCw,
  Wrench,
  Wifi,
  WifiOff,
} from 'lucide-react'

function formatMs(ms) {
  if (!ms && ms !== 0) return '-'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

function formatTime(isoStr) {
  if (!isoStr) return '-'
  return new Date(isoStr).toLocaleTimeString()
}

function getStatusColor(status) {
  switch (status) {
    case 'healthy': return 'text-success'
    case 'timeout': return 'text-warning'
    case 'unreachable':
    case 'error': return 'text-error'
    default: return 'text-text-tertiary'
  }
}

function getStatusBg(status) {
  switch (status) {
    case 'healthy': return 'bg-success/10 border-success/30'
    case 'timeout': return 'bg-warning/10 border-warning/30'
    case 'unreachable':
    case 'error': return 'bg-error/10 border-error/30'
    default: return 'bg-surface border-border'
  }
}

function getStatusIcon(status) {
  switch (status) {
    case 'healthy': return <CheckCircle size={20} className="text-success" />
    case 'timeout': return <AlertTriangle size={20} className="text-warning" />
    case 'unreachable': return <WifiOff size={20} className="text-error" />
    case 'error': return <XCircle size={20} className="text-error" />
    default: return <Loader2 size={20} className="text-text-tertiary animate-spin" />
  }
}

const AUTO_REFRESH_INTERVAL = 30000

function MCPHealth() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const intervalRef = useRef(null)

  const checkHealth = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/health/mcp')
      if (!res.ok) throw new Error(`Failed: ${res.status}`)
      const data = await res.json()
      setHealth(data)
    } catch (err) {
      setError(err.message)
    } finally {
      if (showSpinner) setLoading(false)
    }
  }, [])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => checkHealth(false), AUTO_REFRESH_INTERVAL)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, checkHealth])

  const servers = health?.servers || []

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Heart size={24} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-semibold text-text-primary">MCP Server Health</h1>
              <p className="text-sm text-text-tertiary">Monitor availability of configured MCP servers</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-text-tertiary cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded border-border"
              />
              Auto-refresh (30s)
            </label>
            <button
              onClick={() => checkHealth()}
              className="btn btn-ghost"
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              <span>Check Now</span>
            </button>
          </div>
        </div>

        {/* Summary bar */}
        {health && (
          <div className="flex items-center gap-4 mt-3 text-sm">
            <span className="text-text-secondary">{health.total} server(s)</span>
            <span className="flex items-center gap-1 text-success">
              <Wifi size={14} /> {health.healthy} healthy
            </span>
            {health.unhealthy > 0 && (
              <span className="flex items-center gap-1 text-error">
                <WifiOff size={14} /> {health.unhealthy} unhealthy
              </span>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 md:p-6">
        {error && (
          <div className="p-4 bg-error/10 border border-error/30 rounded-lg text-error text-sm mb-4">
            {error}
          </div>
        )}

        {loading && !health ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <span className="text-text-tertiary text-sm">Pinging MCP servers...</span>
            </div>
          </div>
        ) : servers.length === 0 ? (
          <div className="text-center py-16">
            <Server size={48} className="mx-auto mb-3 text-text-disabled opacity-50" />
            <p className="text-text-tertiary">No MCP servers configured</p>
            <p className="text-text-disabled text-sm mt-1">Add servers in MCP Profiles to monitor them</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {servers.map((server, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-xl border transition-colors ${getStatusBg(server.status)}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(server.status)}
                    <div>
                      <div className="font-semibold text-text-primary text-sm">{server.server_name}</div>
                      <div className="text-xs text-text-tertiary">{server.profile_name}</div>
                    </div>
                  </div>
                  <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded ${getStatusColor(server.status)} bg-surface/50`}>
                    {server.status}
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-center gap-2 text-text-secondary">
                    <Server size={12} className="text-text-tertiary flex-shrink-0" />
                    <span className="truncate">{server.server_url}</span>
                  </div>

                  {server.response_time_ms != null && (
                    <div className="flex items-center gap-2 text-text-secondary">
                      <Clock size={12} className="text-text-tertiary" />
                      Response: {formatMs(server.response_time_ms)}
                    </div>
                  )}

                  {server.tool_count != null && (
                    <div className="flex items-center gap-2 text-text-secondary">
                      <Wrench size={12} className="text-text-tertiary" />
                      {server.tool_count} tools available
                    </div>
                  )}

                  {server.error && (
                    <div className="p-2 bg-error/10 rounded text-error text-xs mt-2 break-words">
                      {server.error}
                    </div>
                  )}

                  <div className="text-text-disabled text-[10px] mt-1">
                    Checked: {formatTime(server.checked_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default MCPHealth
