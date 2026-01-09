import React, { useState, useEffect, useRef } from 'react'
import { X, Loader, CheckCircle, AlertCircle, Sparkles, Terminal } from 'lucide-react'

function TestGenerationModal({ tool, onClose, onSuccess }) {
  const [step, setStep] = useState('configure') // 'configure', 'analyzing', 'generating', 'success', 'error'
  const [coverageLevel, setCoverageLevel] = useState('mid')
  const [customInstructions, setCustomInstructions] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [generatedFile, setGeneratedFile] = useState(null)
  const [error, setError] = useState(null)
  const [logs, setLogs] = useState([])
  const logsEndRef = useRef(null)

  // LLM Profile state
  const [llmProfiles, setLlmProfiles] = useState([])
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [selectedProvider, setSelectedProvider] = useState(null) // format: "provider:model"

  useEffect(() => {
    loadLlmProfiles()
  }, [])

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  const loadLlmProfiles = async () => {
    try {
      const res = await fetch('/api/llm/profiles')
      const data = await res.json()
      setLlmProfiles(data.profiles || [])

      // Helper to set provider from profile
      const setProviderFromProfile = (profile) => {
        if (profile?.providers?.length > 0) {
          const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
          setSelectedProvider(`${defaultProv.provider}:${defaultProv.model}`)
        }
      }

      // Priority: Use global profile selection from sidebar, then API default
      const globalProfile = localStorage.getItem('selectedLLMProfile')

      let profileToUse = null
      if (globalProfile && data.profiles?.find(p => p.profile_id === globalProfile)) {
        profileToUse = data.profiles.find(p => p.profile_id === globalProfile)
      } else if (data.default && data.profiles?.find(p => p.profile_id === data.default)) {
        profileToUse = data.profiles.find(p => p.profile_id === data.default)
      } else if (data.profiles?.length > 0) {
        profileToUse = data.profiles[0]
      }

      if (profileToUse) {
        setSelectedProfile(profileToUse.profile_id)
        // Always use the profile's default provider (the one with default: true)
        setProviderFromProfile(profileToUse)
      }
    } catch (error) {
      console.error('Failed to load LLM profiles:', error)
    }
  }

  const handleProfileChange = (profileId) => {
    setSelectedProfile(profileId)
    // Set default provider for the new profile
    const profile = llmProfiles.find(p => p.profile_id === profileId)
    if (profile?.providers?.length > 0) {
      const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
      setSelectedProvider(`${defaultProv.provider}:${defaultProv.model}`)
    }
  }

  const handleProviderChange = (providerKey) => {
    setSelectedProvider(providerKey)
  }

  // Get the current provider config for display
  const getCurrentProviderInfo = () => {
    if (!selectedProvider) return null
    const [provider, model] = selectedProvider.split(':')
    const profile = llmProfiles.find(p => p.profile_id === selectedProfile)
    const providerInfo = profile?.providers?.find(p => `${p.provider}:${p.model}` === selectedProvider)
    return {
      provider,
      model,
      name: providerInfo?.name || model,
      isCliTool: ['claude-cli', 'codex-cli', 'claude-code', 'codex'].includes(provider),
      isSdk: provider === 'claude-sdk',
      isApi: ['anthropic', 'openai', 'gemini', 'google'].includes(provider),
    }
  }

  const coverageOptions = [
    {
      level: 'basic',
      name: 'Basic Coverage',
      description: '1-2 simple tests covering common scenarios',
      testCount: '1-2 tests',
    },
    {
      level: 'mid',
      name: 'Mid Coverage',
      description: '3-5 tests covering common scenarios and some edge cases',
      testCount: '3-5 tests',
    },
    {
      level: 'comprehensive',
      name: 'Comprehensive Coverage',
      description: '8-12 tests covering edge cases, errors, and parameter variations',
      testCount: '8-12 tests',
    },
  ]

  const handleGenerate = async () => {
    if (!selectedProvider) {
      setError('No LLM provider selected')
      setStep('error')
      return
    }

    const [provider, model] = selectedProvider.split(':')

    try {
      setStep('analyzing')
      setError(null)
      setLogs([]) // Clear previous logs

      // Use streaming endpoint
      const response = await fetch('/api/tests/generate/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: tool.name,
          tool_description: tool.description,
          tool_schema: tool.input_schema,
          coverage_level: coverageLevel,
          custom_instructions: customInstructions || null,
          model: model,
          provider: provider,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to generate tests')
      }

      // Read the streaming response
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE events
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.type === 'log') {
                setLogs(prev => [...prev, { type: 'log', message: data.message, timestamp: new Date().toISOString() }])
              } else if (data.type === 'complete') {
                setAnalysis(data.result.analysis)
                setGeneratedFile(data.result)
                setLogs(prev => [...prev, { type: 'success', message: 'Generation complete!', timestamp: new Date().toISOString() }])
                setStep('success')

                // Notify parent of success
                if (onSuccess) {
                  onSuccess(data.result)
                }
              } else if (data.type === 'error') {
                setLogs(prev => [...prev, { type: 'error', message: data.message, timestamp: new Date().toISOString() }])
                setError(data.message)
                setStep('error')
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line)
            }
          }
        }
      }
    } catch (err) {
      console.error('Error generating tests:', err)
      setError(err.message)
      setStep('error')
    }
  }

  const handleClose = () => {
    if (step === 'analyzing' || step === 'generating') {
      // Don't allow closing during generation
      return
    }
    onClose()
  }

  const providerInfo = getCurrentProviderInfo()
  const currentProfile = llmProfiles.find(p => p.profile_id === selectedProfile)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface border border-border rounded-xl shadow-strong max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
              <Sparkles size={20} className="text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text-primary">Generate Tests</h2>
              <p className="text-sm text-text-secondary mt-0.5">
                AI-powered test generation for <span className="font-mono text-primary">{tool.name}</span>
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={step === 'analyzing' || step === 'generating'}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X size={20} className="text-text-secondary" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {step === 'configure' && (
            <div className="space-y-6">
              {/* LLM Configuration */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-3">
                  LLM Provider
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-text-secondary mb-1.5">Profile</label>
                    <select
                      value={selectedProfile || ''}
                      onChange={(e) => handleProfileChange(e.target.value)}
                      className="input text-sm w-full"
                    >
                      {llmProfiles.map((profile) => (
                        <option key={profile.profile_id} value={profile.profile_id}>
                          {profile.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1.5">Provider / Model</label>
                    <select
                      value={selectedProvider || ''}
                      onChange={(e) => handleProviderChange(e.target.value)}
                      className="input text-sm w-full"
                    >
                      {currentProfile?.providers?.map((prov) => {
                        const provKey = `${prov.provider}:${prov.model}`
                        const isCliTool = ['claude-cli', 'codex-cli', 'claude-code', 'codex'].includes(prov.provider)
                        const isSdk = prov.provider === 'claude-sdk'
                        const isApi = ['anthropic', 'openai', 'gemini', 'google'].includes(prov.provider)
                        return (
                          <option key={provKey} value={provKey}>
                            {prov.name || prov.model} ({prov.provider}) {isCliTool ? '[CLI]' : isSdk ? '[SDK]' : isApi ? '[API]' : ''}
                          </option>
                        )
                      })}
                    </select>
                  </div>
                </div>
                {/* Status indicator */}
                <div className="mt-2">
                  {providerInfo?.isCliTool && (
                    <p className="text-xs text-success flex items-center gap-1">
                      <CheckCircle size={12} />
                      Using CLI tool - no API credits required
                    </p>
                  )}
                  {providerInfo?.isSdk && (
                    <p className="text-xs text-amber-400 flex items-center gap-1">
                      <AlertCircle size={12} />
                      SDK uses API credits
                    </p>
                  )}
                  {providerInfo?.isApi && (
                    <p className="text-xs text-amber-400 flex items-center gap-1">
                      <AlertCircle size={12} />
                      API provider uses credits
                    </p>
                  )}
                </div>
              </div>

              {/* Coverage Level Selection */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-3">
                  Coverage Level
                </label>
                <div className="space-y-2">
                  {coverageOptions.map((option) => (
                    <button
                      key={option.level}
                      onClick={() => setCoverageLevel(option.level)}
                      className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                        coverageLevel === option.level
                          ? 'border-primary bg-primary/5'
                          : 'border-border bg-surface-elevated hover:border-primary/50'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-text-primary">{option.name}</span>
                            <span className="text-xs text-text-tertiary bg-surface-elevated px-2 py-0.5 rounded">
                              {option.testCount}
                            </span>
                          </div>
                          <p className="text-sm text-text-secondary mt-1">{option.description}</p>
                        </div>
                        {coverageLevel === option.level && (
                          <CheckCircle size={20} className="text-primary flex-shrink-0 ml-3" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Instructions */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">
                  Custom Instructions (Optional)
                </label>
                <textarea
                  value={customInstructions}
                  onChange={(e) => setCustomInstructions(e.target.value)}
                  placeholder="E.g., 'Focus on testing error handling' or 'Include tests for different file formats'"
                  className="input w-full text-sm resize-none"
                  rows={3}
                />
                <p className="text-xs text-text-tertiary mt-1.5">
                  Provide specific guidance for test generation
                </p>
              </div>

              {/* Tool Info */}
              <div className="bg-surface-elevated border border-border rounded-lg p-4">
                <h3 className="text-sm font-semibold text-text-primary mb-2">Tool Information</h3>
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-text-secondary">Name:</span>{' '}
                    <span className="font-mono text-text-primary">{tool.name}</span>
                  </div>
                  <div>
                    <span className="text-text-secondary">Description:</span>{' '}
                    <span className="text-text-primary">{tool.description.split('\n')[0]}</span>
                  </div>
                  {tool.input_schema?.properties && (
                    <div>
                      <span className="text-text-secondary">Parameters:</span>{' '}
                      <span className="text-text-primary">
                        {Object.keys(tool.input_schema.properties).length} parameter(s)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {step === 'analyzing' && (
            <div className="space-y-4">
              {/* Header */}
              <div className="flex items-center gap-3">
                <Loader className="w-6 h-6 text-primary animate-spin" />
                <div>
                  <h3 className="text-lg font-semibold text-text-primary">Generating Tests...</h3>
                  <p className="text-sm text-text-secondary">
                    Using <span className="font-medium">{providerInfo?.name || 'LLM'}</span> to analyze and generate test cases
                  </p>
                </div>
              </div>

              {/* Logs Panel */}
              <div className="bg-surface-elevated border border-border rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 bg-surface border-b border-border">
                  <Terminal size={14} className="text-text-tertiary" />
                  <span className="text-xs font-medium text-text-secondary">Generation Logs</span>
                </div>
                <div className="h-64 overflow-auto p-3 font-mono text-xs space-y-1 bg-gray-950">
                  {logs.length === 0 ? (
                    <div className="text-text-tertiary">Waiting for logs...</div>
                  ) : (
                    logs.map((log, idx) => (
                      <div
                        key={idx}
                        className={`${
                          log.type === 'error' ? 'text-error' :
                          log.type === 'success' ? 'text-success' :
                          'text-text-secondary'
                        }`}
                      >
                        {log.message}
                      </div>
                    ))
                  )}
                  <div ref={logsEndRef} />
                </div>
              </div>

              {providerInfo?.isCliTool && (
                <p className="text-xs text-text-tertiary text-center">
                  Running via CLI tool - this may take longer than API calls
                </p>
              )}
            </div>
          )}

          {step === 'success' && generatedFile && (
            <div className="space-y-6">
              <div className="flex items-center gap-3 p-4 bg-success/10 border border-success/30 rounded-lg">
                <CheckCircle size={24} className="text-success flex-shrink-0" />
                <div className="flex-1">
                  <h3 className="font-semibold text-text-primary">Tests Generated Successfully!</h3>
                  <p className="text-sm text-text-secondary mt-1">
                    Created {generatedFile.test_count} test(s) in {generatedFile.filename}
                  </p>
                </div>
              </div>

              {/* Analysis Summary */}
              {analysis && (
                <div className="bg-surface-elevated border border-border rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-text-primary mb-3">Test Strategy</h3>

                  {analysis.test_scenarios && analysis.test_scenarios.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-xs font-semibold text-text-secondary mb-2">Test Scenarios:</h4>
                      <ul className="space-y-1.5">
                        {analysis.test_scenarios.slice(0, 5).map((scenario, idx) => (
                          <li key={idx} className="text-sm text-text-primary flex items-start gap-2">
                            <span className="text-primary mt-0.5">•</span>
                            <span>
                              <span className="font-medium">{scenario.name}:</span> {scenario.description}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.key_parameters && analysis.key_parameters.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-xs font-semibold text-text-secondary mb-2">Key Parameters:</h4>
                      <div className="flex flex-wrap gap-2">
                        {analysis.key_parameters.map((param, idx) => (
                          <span
                            key={idx}
                            className="text-xs bg-primary/10 text-primary px-2 py-1 rounded font-mono"
                          >
                            {param}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {generatedFile.cost > 0 && (
                    <div className="mt-4 pt-4 border-t border-border text-xs text-text-tertiary">
                      Generation cost: ${generatedFile.cost.toFixed(4)}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {step === 'error' && error && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-16 h-16 bg-error/10 rounded-full flex items-center justify-center mb-4">
                <AlertCircle size={32} className="text-error" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary mb-2">Generation Failed</h3>
              <p className="text-text-secondary text-center max-w-md mb-4 whitespace-pre-wrap">{error}</p>
              <button
                onClick={() => setStep('configure')}
                className="btn btn-secondary text-sm"
              >
                Try Again
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-border flex items-center justify-end gap-3">
          {step === 'configure' && (
            <>
              <button onClick={handleClose} className="btn btn-secondary">
                Cancel
              </button>
              <button
                onClick={handleGenerate}
                className="btn btn-primary"
                disabled={!selectedProvider}
              >
                <Sparkles size={16} />
                <span>Generate Tests</span>
              </button>
            </>
          )}
          {step === 'success' && (
            <button onClick={handleClose} className="btn btn-primary">
              <span>Done</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default TestGenerationModal
