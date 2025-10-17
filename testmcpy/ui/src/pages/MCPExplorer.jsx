import React, { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'

function MCPExplorer() {
  const [tools, setTools] = useState([])
  const [resources, setResources] = useState([])
  const [prompts, setPrompts] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedTools, setExpandedTools] = useState(new Set())
  const [copiedId, setCopiedId] = useState(null)
  const [activeTab, setActiveTab] = useState('tools')

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [toolsRes, resourcesRes, promptsRes] = await Promise.all([
        fetch('/api/mcp/tools'),
        fetch('/api/mcp/resources'),
        fetch('/api/mcp/prompts'),
      ])

      setTools(await toolsRes.json())
      setResources(await resourcesRes.json())
      setPrompts(await promptsRes.json())
    } catch (error) {
      console.error('Failed to load MCP data:', error)
    } finally {
      setLoading(false)
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-text-secondary">Loading MCP data...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-8 border-b border-border bg-surface-elevated">
        <h1 className="text-3xl font-bold">MCP Explorer</h1>
        <p className="text-text-secondary mt-2 text-base">
          Browse tools, resources, and prompts from your MCP service
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-8 pt-6 border-b border-border bg-surface-elevated/50">
        <button
          onClick={() => setActiveTab('tools')}
          className={`tab ${
            activeTab === 'tools' ? 'tab-active' : 'tab-inactive'
          }`}
        >
          Tools ({tools.length})
        </button>
        <button
          onClick={() => setActiveTab('resources')}
          className={`tab ${
            activeTab === 'resources' ? 'tab-active' : 'tab-inactive'
          }`}
        >
          Resources ({resources.length})
        </button>
        <button
          onClick={() => setActiveTab('prompts')}
          className={`tab ${
            activeTab === 'prompts' ? 'tab-active' : 'tab-inactive'
          }`}
        >
          Prompts ({prompts.length})
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-8 bg-background-subtle">
        {activeTab === 'tools' && (
          <div className="max-w-5xl mx-auto space-y-4">
            {tools.map((tool, idx) => (
              <div key={idx} className="card-hover">
                <div
                  className="flex items-start justify-between cursor-pointer group"
                  onClick={() => toggleTool(tool.name)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <div className="flex-shrink-0 transition-transform duration-200">
                        {expandedTools.has(tool.name) ? (
                          <ChevronDown size={20} className="text-text-secondary" />
                        ) : (
                          <ChevronRight size={20} className="text-text-secondary" />
                        )}
                      </div>
                      <h3 className="font-semibold text-lg text-text-primary">{tool.name}</h3>
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

                    {/* Parameters */}
                    <div>
                      <h4 className="text-sm font-semibold text-text-secondary mb-3">
                        Parameters
                      </h4>
                      {tool.input_schema?.properties ? (
                        <div className="space-y-3">
                          {Object.entries(tool.input_schema.properties).map(
                            ([param, info]) => (
                              <div
                                key={param}
                                className="bg-surface-elevated border border-border rounded-lg p-4 hover:border-border-subtle transition-colors"
                              >
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-mono text-sm font-medium text-primary-light">
                                    {param}
                                  </span>
                                  <span className="badge badge-warning">
                                    {info.type}
                                  </span>
                                  {tool.input_schema.required?.includes(param) && (
                                    <span className="badge badge-error">
                                      required
                                    </span>
                                  )}
                                </div>
                                {info.description && (
                                  <p className="text-sm text-text-secondary mt-2 leading-relaxed">
                                    {info.description}
                                  </p>
                                )}
                              </div>
                            )
                          )}
                        </div>
                      ) : (
                        <p className="text-sm text-text-tertiary italic">No parameters</p>
                      )}
                    </div>

                    {/* Full Schema */}
                    <div>
                      <h4 className="text-sm font-semibold text-text-secondary mb-3">
                        Input Schema (JSON)
                      </h4>
                      <pre className="code-block text-text-primary">
                        {JSON.stringify(tool.input_schema, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === 'resources' && (
          <div className="max-w-5xl mx-auto space-y-4">
            {resources.map((resource, idx) => (
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
            {prompts.map((prompt, idx) => (
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
    </div>
  )
}

export default MCPExplorer
