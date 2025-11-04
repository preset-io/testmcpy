import React, { useState, useEffect } from 'react'
import Editor from '@monaco-editor/react'
import { Copy, Check } from 'lucide-react'
import { FORMATS } from '../utils/formatConverters'

/**
 * IDE-like code viewer with syntax highlighting and multi-format export
 * Displays JSON Schema parameters in various developer-friendly formats
 */
function SchemaCodeViewer({ schema, toolName = 'tool' }) {
  const [selectedFormat, setSelectedFormat] = useState('json')
  const [code, setCode] = useState('')
  const [copied, setCopied] = useState(false)
  const [useActualValues, setUseActualValues] = useState(false)

  // Update code when format, schema, or useActualValues changes
  useEffect(() => {
    const format = FORMATS.find(f => f.id === selectedFormat)
    if (format && schema) {
      // If format requires backend, fetch from API
      if (format.useBackend) {
        fetchCodeFromBackend(format.id, schema, toolName)
      } else if (selectedFormat === 'curl' && useActualValues) {
        // For curl with actual values, use backend
        fetchCodeFromBackend('curl', schema, toolName, true)
      } else {
        // Use frontend converter
        try {
          const converted = format.convert(schema, toolName)
          setCode(converted)
        } catch (error) {
          console.error(`Error converting to ${selectedFormat}:`, error)
          setCode(`// Error converting to ${selectedFormat}: ${error.message}`)
        }
      }
    }
  }, [selectedFormat, schema, toolName, useActualValues])

  const fetchCodeFromBackend = async (formatId, schema, toolName, withActualValues = false) => {
    try {
      setCode('// Loading...')

      // Get config for actual values if needed (only for curl when user requests it)
      let mcpUrl = null
      let authToken = null

      if (withActualValues && formatId === 'curl') {
        try {
          const configRes = await fetch('/api/config')
          const configData = await configRes.json()
          mcpUrl = configData.MCP_URL?.value
          authToken = configData.MCP_AUTH_TOKEN?.value
        } catch (err) {
          console.warn('Could not fetch config for actual values:', err)
        }
      }

      const response = await fetch('/api/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schema: schema,
          tool_name: toolName,
          format: formatId,
          mcp_url: mcpUrl,
          auth_token: authToken
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const result = await response.json()
      setCode(result.code)
    } catch (error) {
      console.error(`Error fetching ${formatId} from backend:`, error)
      setCode(`// Error generating ${formatId}: ${error.message}`)
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy:', error)
    }
  }

  const currentFormat = FORMATS.find(f => f.id === selectedFormat)

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-surface-elevated">
      {/* Format selector and copy button */}
      <div className="flex items-center justify-between border-b border-border bg-surface px-3 py-2">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-text-secondary">
            <span>Format:</span>
            <select
              value={selectedFormat}
              onChange={(e) => setSelectedFormat(e.target.value)}
              className="px-3 py-1.5 text-xs font-medium rounded border border-border bg-surface-elevated text-text-primary hover:border-primary focus:border-primary focus:ring-2 focus:ring-primary focus:ring-offset-0 focus:outline-none cursor-pointer transition-all duration-200"
            >
              {FORMATS.map(format => (
                <option key={format.id} value={format.id}>
                  {format.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex items-center gap-3">
          {selectedFormat === 'curl' && (
            <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer hover:text-text-primary transition-colors">
              <input
                type="checkbox"
                checked={useActualValues}
                onChange={(e) => setUseActualValues(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-surface text-primary focus:ring-2 focus:ring-primary focus:ring-offset-0 cursor-pointer"
              />
              <span>Use actual values</span>
            </label>
          )}
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-surface-hover rounded transition-all duration-200"
            title={`Copy ${currentFormat?.label} code`}
          >
            {copied ? (
              <>
                <Check size={14} className="text-success" />
                <span className="text-success">Copied!</span>
              </>
            ) : (
              <>
                <Copy size={14} />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Monaco Editor */}
      <div className="relative" style={{ height: '300px' }}>
        <Editor
          height="300px"
          language={currentFormat?.language || 'json'}
          value={code}
          theme="vs-dark"
          options={{
            readOnly: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            lineNumbers: 'on',
            renderLineHighlight: 'none',
            scrollbar: {
              vertical: 'visible',
              horizontal: 'visible',
              useShadows: false,
              verticalScrollbarSize: 10,
              horizontalScrollbarSize: 10,
            },
            overviewRulerLanes: 0,
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 3,
            glyphMargin: false,
            folding: true,
            renderWhitespace: 'none',
            wordWrap: 'on',
            automaticLayout: true,
            padding: { top: 8, bottom: 8 },
          }}
          loading={
            <div className="flex items-center justify-center h-full bg-[#1e1e1e]">
              <div className="text-text-secondary text-sm">Loading editor...</div>
            </div>
          }
        />
      </div>

      {/* Format info */}
      <div className="px-3 py-2 border-t border-border bg-surface text-xs text-text-tertiary">
        {selectedFormat === 'json' && 'JSON Schema format - standard machine-readable format'}
        {selectedFormat === 'yaml' && 'YAML format - human-friendly configuration format'}
        {selectedFormat === 'typescript' && 'TypeScript interface - for type-safe frontend development'}
        {selectedFormat === 'python' && 'Python TypedDict - for type-safe backend development'}
        {selectedFormat === 'protobuf' && 'Protocol Buffers (proto3) - high-performance binary serialization'}
        {selectedFormat === 'thrift' && 'Apache Thrift IDL - cross-language service development'}
        {selectedFormat === 'graphql' && 'GraphQL Input Type - for GraphQL API schemas'}
        {selectedFormat === 'curl' && 'cURL command example - ready to test in terminal'}
        {selectedFormat === 'python_client' && 'Python client code - complete working example for calling this MCP tool'}
        {selectedFormat === 'javascript_client' && 'JavaScript client code - complete working example for calling this MCP tool'}
        {selectedFormat === 'typescript_client' && 'TypeScript client code - type-safe working example for calling this MCP tool'}
      </div>
    </div>
  )
}

export default SchemaCodeViewer