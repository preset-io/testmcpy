import React, { useState, useEffect } from 'react'
import { RefreshCw, Info, Copy, Check, Terminal } from 'lucide-react'

function Configuration() {
  const [config, setConfig] = useState({})
  const [loading, setLoading] = useState(true)
  const [copiedCommand, setCopiedCommand] = useState(null)

  useEffect(() => {
    loadConfig()
  }, [])

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

  const loadConfig = async () => {
    setLoading(true)
    try {
      const res = await fetchWithRetry('/api/config')
      const data = await res.json()
      setConfig(data)
    } catch (error) {
      console.error('Failed to load config:', error)
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = async (text, commandKey) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedCommand(commandKey)
      setTimeout(() => setCopiedCommand(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const getMcpUrl = () => {
    return config.MCP_URL?.value || 'https://your-workspace.preset.io/mcp'
  }

  const getAuthToken = () => {
    const token = config.MCP_AUTH_TOKEN?.value
    if (token && token !== 'not set') {
      // Mask the token for display
      return token.length > 30 ? `${token.substring(0, 20)}...${token.substring(token.length - 8)}` : token
    }
    return 'YOUR_BEARER_TOKEN'
  }

  const getFullAuthToken = () => {
    const token = config.MCP_AUTH_TOKEN?.value
    return (token && token !== 'not set') ? token : 'YOUR_BEARER_TOKEN'
  }

  const configGroups = {
    'MCP Settings': ['MCP_URL', 'MCP_AUTH_TOKEN', 'MCP_AUTH_API_URL', 'MCP_AUTH_API_TOKEN', 'MCP_AUTH_API_SECRET'],
    'LLM Provider': ['DEFAULT_PROVIDER', 'DEFAULT_MODEL'],
    'Anthropic': ['ANTHROPIC_API_KEY', 'ANTHROPIC_MODEL'],
    'OpenAI': ['OPENAI_API_KEY', 'OPENAI_BASE_URL'],
    'Ollama': ['OLLAMA_BASE_URL'],
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-text-secondary">Loading configuration...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-8 border-b border-border bg-surface-elevated">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Configuration</h1>
            <p className="text-text-secondary mt-2 text-base">
              View current testmcpy configuration settings
            </p>
          </div>
          <button
            onClick={loadConfig}
            className="btn btn-secondary"
          >
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Config Groups */}
      <div className="flex-1 overflow-auto p-8 bg-background-subtle">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Info Banner */}
          <div className="bg-info/10 border border-info/30 rounded-xl p-5 flex gap-4">
            <Info size={22} className="text-info-light flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="text-info-light font-semibold mb-2">
                Configuration Sources
              </p>
              <p className="text-text-secondary leading-relaxed">
                MCP servers are configured via <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs">.mcp_services.yaml</code>.
                LLM provider settings (API keys, models) are loaded from environment variables and command-line options.
              </p>
            </div>
          </div>

          {/* Config Groups */}
          {Object.entries(configGroups).map(([groupName, keys]) => {
            const groupConfig = keys.reduce((acc, key) => {
              if (config[key]) {
                acc[key] = config[key]
              }
              return acc
            }, {})

            if (Object.keys(groupConfig).length === 0) return null

            return (
              <div key={groupName} className="card">
                <h3 className="text-xl font-semibold mb-5 text-primary-light">
                  {groupName}
                </h3>
                <div className="space-y-4">
                  {Object.entries(groupConfig).map(([key, data]) => (
                    <div
                      key={key}
                      className="flex items-start justify-between gap-6 pb-4 border-b border-border last:border-0 last:pb-0"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-sm text-text-secondary mb-2 font-medium">
                          {key}
                        </div>
                        <div className="text-sm">
                          {data.value ? (
                            <span className="text-text-primary break-all">
                              {data.value}
                            </span>
                          ) : (
                            <span className="text-text-tertiary italic">not set</span>
                          )}
                        </div>
                      </div>
                      <div className="badge badge-info whitespace-nowrap">
                        {data.source}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}

          {/* Other Settings */}
          {(() => {
            const allGroupKeys = Object.values(configGroups).flat()
            const otherConfig = Object.entries(config).reduce(
              (acc, [key, data]) => {
                if (!allGroupKeys.includes(key)) {
                  acc[key] = data
                }
                return acc
              },
              {}
            )

            if (Object.keys(otherConfig).length === 0) return null

            return (
              <div className="card">
                <h3 className="text-xl font-semibold mb-5 text-primary-light">
                  Other Settings
                </h3>
                <div className="space-y-4">
                  {Object.entries(otherConfig).map(([key, data]) => (
                    <div
                      key={key}
                      className="flex items-start justify-between gap-6 pb-4 border-b border-border last:border-0 last:pb-0"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-sm text-text-secondary mb-2 font-medium">
                          {key}
                        </div>
                        <div className="text-sm">
                          {data.value ? (
                            <span className="text-text-primary break-all">
                              {data.value}
                            </span>
                          ) : (
                            <span className="text-text-tertiary italic">not set</span>
                          )}
                        </div>
                      </div>
                      <div className="badge badge-info whitespace-nowrap">
                        {data.source}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}

          {/* LLM Client Configuration */}
          <div className="card">
            <div className="flex items-center gap-3 mb-5">
              <Terminal size={24} className="text-primary-light" />
              <h3 className="text-xl font-semibold text-primary-light">
                Connect Your LLM Client
              </h3>
            </div>
            <p className="text-text-secondary mb-6 leading-relaxed">
              Configure your LLM client (Claude Desktop, Claude Code, or ChatGPT Desktop) to connect to the same MCP server that testmcpy uses.
              This allows your LLM to access the same tools you're testing here.
            </p>

            {/* Quick Commands */}
            <div className="space-y-4">
              {/* Claude Desktop */}
              <div className="bg-background-subtle rounded-lg p-4 border border-border">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-semibold text-text-primary flex items-center gap-2">
                    <span className="text-primary">•</span>
                    Claude Desktop
                  </h4>
                  <button
                    onClick={() => copyToClipboard(`testmcpy config-mcp claude-desktop${getFullAuthToken() !== 'YOUR_BEARER_TOKEN' ? ' --token "' + getFullAuthToken() + '"' : ''}`, 'claude-desktop')}
                    className="btn btn-sm btn-secondary"
                  >
                    {copiedCommand === 'claude-desktop' ? (
                      <>
                        <Check size={14} />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
                <div className="bg-black/40 rounded p-3 font-mono text-xs text-green-400 overflow-x-auto">
                  testmcpy config-mcp claude-desktop{getFullAuthToken() !== 'YOUR_BEARER_TOKEN' && ' --token "' + getAuthToken() + '"'}
                </div>
              </div>

              {/* Claude Code */}
              <div className="bg-background-subtle rounded-lg p-4 border border-border">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-semibold text-text-primary flex items-center gap-2">
                    <span className="text-primary">•</span>
                    Claude Code
                  </h4>
                  <button
                    onClick={() => copyToClipboard(`testmcpy config-mcp claude-code${getFullAuthToken() !== 'YOUR_BEARER_TOKEN' ? ' --token "' + getFullAuthToken() + '"' : ''}`, 'claude-code')}
                    className="btn btn-sm btn-secondary"
                  >
                    {copiedCommand === 'claude-code' ? (
                      <>
                        <Check size={14} />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
                <div className="bg-black/40 rounded p-3 font-mono text-xs text-green-400 overflow-x-auto">
                  testmcpy config-mcp claude-code{getFullAuthToken() !== 'YOUR_BEARER_TOKEN' && ' --token "' + getAuthToken() + '"'}
                </div>
              </div>

              {/* ChatGPT Desktop */}
              <div className="bg-background-subtle rounded-lg p-4 border border-border">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-semibold text-text-primary flex items-center gap-2">
                    <span className="text-primary">•</span>
                    ChatGPT Desktop
                  </h4>
                  <button
                    onClick={() => copyToClipboard(`testmcpy config-mcp chatgpt-desktop${getFullAuthToken() !== 'YOUR_BEARER_TOKEN' ? ' --token "' + getFullAuthToken() + '"' : ''}`, 'chatgpt-desktop')}
                    className="btn btn-sm btn-secondary"
                  >
                    {copiedCommand === 'chatgpt-desktop' ? (
                      <>
                        <Check size={14} />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
                <div className="bg-black/40 rounded p-3 font-mono text-xs text-green-400 overflow-x-auto">
                  testmcpy config-mcp chatgpt-desktop{getFullAuthToken() !== 'YOUR_BEARER_TOKEN' && ' --token "' + getAuthToken() + '"'}
                </div>
              </div>
            </div>

            {/* Configuration Details */}
            <div className="mt-6 bg-info/10 border border-info/30 rounded-lg p-4">
              <div className="flex gap-3">
                <Info size={18} className="text-info-light flex-shrink-0 mt-0.5" />
                <div className="text-sm text-text-secondary space-y-2">
                  <p>
                    <strong className="text-info-light">MCP URL:</strong> <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs">{getMcpUrl()}</code>
                  </p>
                  <p>
                    <strong className="text-info-light">Auth Token:</strong> <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs">{getAuthToken()}</code>
                  </p>
                  <p className="pt-2">
                    These commands will automatically configure your LLM client to connect to the same MCP server.
                    After running the command, restart your LLM client to see the changes.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Help Text */}
          <div className="bg-surface border border-border rounded-xl p-6">
            <h4 className="text-sm font-semibold text-text-primary mb-3">
              How to modify these settings
            </h4>
            <ul className="space-y-2.5 text-sm text-text-secondary">
              <li className="flex items-start gap-3">
                <span className="text-primary mt-0.5">•</span>
                <span><strong>MCP Servers:</strong> Configure via the Profiles selector in the sidebar or edit <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs text-primary-light">.mcp_services.yaml</code></span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-primary mt-0.5">•</span>
                <span><strong>LLM API Keys:</strong> Set environment variables (e.g., <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs text-primary-light">ANTHROPIC_API_KEY</code>)</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-primary mt-0.5">•</span>
                <span><strong>Model Selection:</strong> Use command-line flags like <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs text-primary-light">--model</code> or set <code className="bg-background-subtle px-2 py-0.5 rounded font-mono text-xs text-primary-light">DEFAULT_MODEL</code> env var</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Configuration
