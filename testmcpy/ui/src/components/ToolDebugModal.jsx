import React, { useState, useEffect } from 'react'
import {
  X,
  Play,
  Loader,
  CheckCircle,
  XCircle,
  Clock,
  Copy,
  Check,
  Download,
  AlertCircle,
  ArrowRight,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import ReactJson from '@microlink/react-json-view'

/**
 * TraceVisualization - Timeline showing tool execution steps
 */
function TraceVisualization({ trace, currentStep }) {
  if (!trace || trace.steps.length === 0) return null

  const steps = [
    { label: 'Request Prepared', icon: ArrowRight },
    { label: 'MCP Processing', icon: Loader },
    { label: 'Response Received', icon: CheckCircle },
  ]

  const getStepStatus = (index) => {
    if (currentStep === -1) return 'pending'
    if (index === currentStep) return 'current'
    if (index < currentStep) return 'complete'
    return 'pending'
  }

  return (
    <div className="bg-surface-elevated rounded-lg border border-border p-4">
      <h4 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2">
        <Clock size={16} className="text-primary" />
        Execution Timeline
      </h4>

      <div className="relative">
        {steps.map((step, idx) => {
          const status = getStepStatus(idx)
          const Icon = step.icon
          const isLast = idx === steps.length - 1

          return (
            <div key={idx} className="relative pb-6">
              {!isLast && (
                <div
                  className={`absolute left-4 top-8 bottom-0 w-0.5 transition-colors ${
                    status === 'complete' ? 'bg-success' : 'bg-border'
                  }`}
                />
              )}

              <div className="flex items-start gap-3">
                <div
                  className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                    status === 'complete'
                      ? 'bg-success text-white'
                      : status === 'current'
                      ? 'bg-primary text-white animate-pulse'
                      : 'bg-surface border border-border text-text-disabled'
                  }`}
                >
                  {status === 'current' ? (
                    <Loader className="animate-spin" size={16} />
                  ) : (
                    <Icon size={16} />
                  )}
                </div>

                <div className="flex-1 pt-1">
                  <div
                    className={`text-sm font-medium ${
                      status === 'complete'
                        ? 'text-success'
                        : status === 'current'
                        ? 'text-primary'
                        : 'text-text-disabled'
                    }`}
                  >
                    {step.label}
                  </div>
                  {trace.steps[idx] && (
                    <div className="text-xs text-text-tertiary mt-1">
                      {trace.steps[idx].timestamp.toFixed(0)}ms
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {trace.total_time && (
        <div className="mt-2 pt-3 border-t border-border">
          <div className="text-sm text-text-secondary flex items-center gap-2">
            <Clock size={14} />
            <span className="font-semibold">Total Time:</span>
            <span className="text-primary">{trace.total_time.toFixed(0)}ms</span>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Parameter form generator based on JSON schema
 */
function ParameterForm({ schema, values, onChange }) {
  if (!schema?.properties) {
    return (
      <div className="text-sm text-text-tertiary italic p-4 bg-surface-elevated rounded-lg border border-border">
        No parameters required
      </div>
    )
  }

  const handleChange = (paramName, value) => {
    onChange({ ...values, [paramName]: value })
  }

  const renderInput = (paramName, paramInfo) => {
    const type = paramInfo.type
    const value = values[paramName] ?? paramInfo.default ?? ''
    const required = schema.required?.includes(paramName)

    // String input
    if (type === 'string') {
      if (paramInfo.enum) {
        return (
          <select
            value={value}
            onChange={(e) => handleChange(paramName, e.target.value)}
            className="input w-full"
            required={required}
          >
            <option value="">Select...</option>
            {paramInfo.enum.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        )
      }

      return (
        <input
          type="text"
          value={value}
          onChange={(e) => handleChange(paramName, e.target.value)}
          placeholder={paramInfo.description || `Enter ${paramName}`}
          className="input w-full"
          required={required}
        />
      )
    }

    // Number input
    if (type === 'number' || type === 'integer') {
      return (
        <input
          type="number"
          value={value}
          onChange={(e) => handleChange(paramName, parseFloat(e.target.value))}
          placeholder={paramInfo.description || `Enter ${paramName}`}
          min={paramInfo.minimum}
          max={paramInfo.maximum}
          className="input w-full"
          required={required}
        />
      )
    }

    // Boolean input
    if (type === 'boolean') {
      return (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={value === true}
            onChange={(e) => handleChange(paramName, e.target.checked)}
            className="w-4 h-4 rounded border-border bg-surface"
          />
          <span className="text-sm text-text-secondary">
            {value ? 'True' : 'False'}
          </span>
        </div>
      )
    }

    // Object/Array - use JSON editor
    if (type === 'object' || type === 'array') {
      const jsonValue = typeof value === 'string' ? value : JSON.stringify(value || (type === 'array' ? [] : {}), null, 2)

      return (
        <textarea
          value={jsonValue}
          onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value)
              handleChange(paramName, parsed)
            } catch {
              // Invalid JSON - keep as string for now
              handleChange(paramName, e.target.value)
            }
          }}
          placeholder={`Enter JSON ${type}`}
          rows={6}
          className="input w-full font-mono text-sm"
          required={required}
        />
      )
    }

    // Fallback
    return (
      <input
        type="text"
        value={value}
        onChange={(e) => handleChange(paramName, e.target.value)}
        placeholder={paramInfo.description || `Enter ${paramName}`}
        className="input w-full"
        required={required}
      />
    )
  }

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(([paramName, paramInfo]) => {
        const required = schema.required?.includes(paramName)

        return (
          <div key={paramName}>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              {paramName}
              {required && (
                <span className="ml-1.5 text-xs text-error">*</span>
              )}
            </label>

            {paramInfo.description && (
              <p className="text-xs text-text-tertiary mb-2">
                {paramInfo.description}
              </p>
            )}

            {renderInput(paramName, paramInfo)}
          </div>
        )
      })}
    </div>
  )
}

/**
 * Main ToolDebugModal component
 */
function ToolDebugModal({ tool, profile, onClose }) {
  const [parameters, setParameters] = useState({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [currentStep, setCurrentStep] = useState(-1)
  const [expandedSections, setExpandedSections] = useState(new Set(['response']))
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    // Pre-fill with default values from schema
    if (tool.input_schema?.properties) {
      const defaults = {}
      Object.entries(tool.input_schema.properties).forEach(([key, info]) => {
        if (info.default !== undefined) {
          defaults[key] = info.default
        }
      })
      setParameters(defaults)
    }
  }, [tool])

  const handleCallTool = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    setCurrentStep(0)

    try {
      // Simulate step progression
      setTimeout(() => setCurrentStep(1), 300)

      const response = await fetch(`/api/tools/${encodeURIComponent(tool.name)}/debug`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          parameters,
          profile,
        }),
      })

      setCurrentStep(2)

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to call tool')
      }

      setResult(data)
      setExpandedSections(new Set(['response', 'trace']))
    } catch (err) {
      console.error('Tool debug error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
      setTimeout(() => setCurrentStep(-1), 500)
    }
  }

  const handleCopyResponse = () => {
    if (result?.response) {
      navigator.clipboard.writeText(JSON.stringify(result.response, null, 2))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadTrace = () => {
    if (!result) return

    const trace = {
      tool: tool.name,
      parameters,
      timestamp: new Date().toISOString(),
      ...result,
    }

    const blob = new Blob([JSON.stringify(trace, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tool-debug-${tool.name}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const toggleSection = (section) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl border border-border shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-border">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-text-primary flex items-center gap-2">
              <Play className="text-primary" size={24} />
              Debug Tool
            </h2>
            <p className="text-sm text-text-secondary mt-1 font-mono">
              {tool.name}
            </p>
            {tool.description && (
              <p className="text-sm text-text-tertiary mt-2">
                {tool.description.split('\n')[0]}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors flex-shrink-0"
          >
            <X size={20} className="text-text-tertiary" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6 space-y-6">
          {/* Parameter Form */}
          <div>
            <h3 className="text-sm font-semibold text-text-secondary mb-3">
              Parameters
            </h3>
            <ParameterForm
              schema={tool.input_schema}
              values={parameters}
              onChange={setParameters}
            />
          </div>

          {/* Call Button */}
          <div className="flex gap-2">
            <button
              onClick={handleCallTool}
              disabled={loading}
              className="btn btn-primary flex items-center gap-2"
            >
              {loading ? (
                <>
                  <Loader className="animate-spin" size={18} />
                  Calling Tool...
                </>
              ) : (
                <>
                  <Play size={18} />
                  Call Tool
                </>
              )}
            </button>

            {result && (
              <>
                <button
                  onClick={handleCopyResponse}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  {copied ? (
                    <>
                      <Check size={18} className="text-success" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy size={18} />
                      Copy Response
                    </>
                  )}
                </button>
                <button
                  onClick={handleDownloadTrace}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <Download size={18} />
                  Download Trace
                </button>
              </>
            )}
          </div>

          {/* Error Display */}
          {error && (
            <div className="bg-error/10 border border-error/30 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="text-error flex-shrink-0 mt-0.5" size={20} />
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-error mb-1">
                    Error
                  </h4>
                  <p className="text-sm text-error/90 font-mono">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Trace Visualization */}
          {(loading || result) && (
            <TraceVisualization
              trace={result || { steps: [], total_time: 0 }}
              currentStep={currentStep}
            />
          )}

          {/* Response Display */}
          {result && (
            <div>
              <button
                onClick={() => toggleSection('response')}
                className="w-full flex items-center justify-between p-3 bg-surface-elevated rounded-lg border border-border hover:bg-surface-hover transition-colors mb-2"
              >
                <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
                  {result.success ? (
                    <CheckCircle className="text-success" size={18} />
                  ) : (
                    <XCircle className="text-error" size={18} />
                  )}
                  Response
                </h3>
                {expandedSections.has('response') ? (
                  <ChevronDown size={18} className="text-text-tertiary" />
                ) : (
                  <ChevronRight size={18} className="text-text-tertiary" />
                )}
              </button>

              {expandedSections.has('response') && (
                <div className="bg-black/40 rounded-lg p-4 border border-border">
                  <ReactJson
                    src={result.response}
                    theme="monokai"
                    collapsed={3}
                    displayDataTypes={false}
                    displayObjectSize={true}
                    enableClipboard={true}
                    name="response"
                    indentWidth={2}
                    iconStyle="triangle"
                    style={{
                      backgroundColor: 'transparent',
                      fontSize: '13px',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                    }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Request Details */}
          {result && (
            <div>
              <button
                onClick={() => toggleSection('request')}
                className="w-full flex items-center justify-between p-3 bg-surface-elevated rounded-lg border border-border hover:bg-surface-hover transition-colors mb-2"
              >
                <h3 className="text-sm font-semibold text-text-secondary">
                  Request Details
                </h3>
                {expandedSections.has('request') ? (
                  <ChevronDown size={18} className="text-text-tertiary" />
                ) : (
                  <ChevronRight size={18} className="text-text-tertiary" />
                )}
              </button>

              {expandedSections.has('request') && (
                <div className="bg-surface-elevated rounded-lg p-4 border border-border space-y-3">
                  <div>
                    <div className="text-xs font-semibold text-text-tertiary mb-1">
                      Tool Name
                    </div>
                    <div className="text-sm font-mono text-text-primary">
                      {tool.name}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-text-tertiary mb-1">
                      Parameters
                    </div>
                    <pre className="text-sm font-mono text-text-primary bg-black/40 p-3 rounded border border-border overflow-auto">
                      {JSON.stringify(parameters, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ToolDebugModal
