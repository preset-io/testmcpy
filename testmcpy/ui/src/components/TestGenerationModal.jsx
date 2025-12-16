import React, { useState, useEffect } from 'react'
import { X, Loader, CheckCircle, AlertCircle, Sparkles, ChevronDown, Settings } from 'lucide-react'

function TestGenerationModal({ tool, onClose, onSuccess }) {
  const [step, setStep] = useState('configure') // 'configure', 'analyzing', 'generating', 'success', 'error'
  const [coverageLevel, setCoverageLevel] = useState('mid')
  const [customInstructions, setCustomInstructions] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [generatedFile, setGeneratedFile] = useState(null)
  const [error, setError] = useState(null)

  // LLM Profile state
  const [llmProfiles, setLlmProfiles] = useState([])
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [selectedProvider, setSelectedProvider] = useState(null) // format: "provider:model"
  const [showOverride, setShowOverride] = useState(false)

  useEffect(() => {
    loadLlmProfiles()
  }, [])

  const loadLlmProfiles = async () => {
    try {
      const res = await fetch('/api/llm/profiles')
      const data = await res.json()
      setLlmProfiles(data.profiles || [])

      // Get saved selections from localStorage (same keys as TestManager)
      const savedProfile = localStorage.getItem('selectedLLMProfileForTests')
      const savedProvider = localStorage.getItem('selectedLLMProviderForTests')

      if (savedProfile && data.profiles?.find(p => p.profile_id === savedProfile)) {
        setSelectedProfile(savedProfile)
        if (savedProvider) {
          setSelectedProvider(savedProvider)
        } else {
          // Set default provider from the profile
          const profile = data.profiles.find(p => p.profile_id === savedProfile)
          if (profile?.providers?.length > 0) {
            const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
            setSelectedProvider(`${defaultProv.provider}:${defaultProv.model}`)
          }
        }
      } else if (data.default && data.profiles?.find(p => p.profile_id === data.default)) {
        // Use default profile
        setSelectedProfile(data.default)
        const profile = data.profiles.find(p => p.profile_id === data.default)
        if (profile?.providers?.length > 0) {
          const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
          setSelectedProvider(`${defaultProv.provider}:${defaultProv.model}`)
        }
      } else if (data.profiles?.length > 0) {
        // Fallback to first profile
        const firstProfile = data.profiles[0]
        setSelectedProfile(firstProfile.profile_id)
        if (firstProfile.providers?.length > 0) {
          const defaultProv = firstProfile.providers.find(p => p.default) || firstProfile.providers[0]
          setSelectedProvider(`${defaultProv.provider}:${defaultProv.model}`)
        }
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

      const response = await fetch('/api/tests/generate', {
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

      const data = await response.json()
      setAnalysis(data.analysis)
      setGeneratedFile(data)
      setStep('success')

      // Notify parent of success
      if (onSuccess) {
        onSuccess(data)
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
              {/* LLM Configuration - Using saved profile */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="text-sm font-semibold text-text-primary">
                    LLM Configuration
                  </label>
                  <button
                    onClick={() => setShowOverride(!showOverride)}
                    className="text-xs text-text-tertiary hover:text-text-secondary flex items-center gap-1"
                  >
                    <Settings size={12} />
                    {showOverride ? 'Hide options' : 'Change provider'}
                  </button>
                </div>

                {/* Current selection display */}
                <div className="bg-surface-elevated border border-border rounded-lg p-4">
                  {providerInfo ? (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-text-primary">{providerInfo.name}</span>
                          {providerInfo.isCliTool && (
                            <span className="px-1.5 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded">CLI</span>
                          )}
                          {providerInfo.isSdk && (
                            <span className="px-1.5 py-0.5 text-xs bg-cyan-500/20 text-cyan-400 rounded">SDK</span>
                          )}
                          {providerInfo.isApi && (
                            <span className="px-1.5 py-0.5 text-xs bg-emerald-500/20 text-emerald-400 rounded">API</span>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-text-tertiary">
                        {currentProfile?.name || 'Default Profile'}
                      </div>
                    </div>
                  ) : (
                    <div className="text-text-tertiary text-sm">No LLM provider configured</div>
                  )}

                  {providerInfo?.isApi && (
                    <p className="text-xs text-text-tertiary mt-2">
                      This will use API credits. Consider using a CLI tool to avoid API costs.
                    </p>
                  )}
                  {providerInfo?.isCliTool && (
                    <p className="text-xs text-success mt-2">
                      Using CLI tool - no API credits required.
                    </p>
                  )}
                </div>

                {/* Override options */}
                {showOverride && (
                  <div className="mt-3 p-4 bg-surface-elevated border border-border rounded-lg space-y-3">
                    <div>
                      <label className="block text-xs text-text-secondary mb-1.5">LLM Profile</label>
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
                )}
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
            <div className="flex flex-col items-center justify-center py-12">
              <Loader className="w-12 h-12 text-primary animate-spin mb-4" />
              <h3 className="text-lg font-semibold text-text-primary mb-2">Generating Tests...</h3>
              <p className="text-text-secondary text-center max-w-md">
                Using <span className="font-medium">{providerInfo?.name || 'LLM'}</span> to analyze the tool and generate test cases
              </p>
              {providerInfo?.isCliTool && (
                <p className="text-xs text-text-tertiary mt-2">
                  Running via CLI - this may take a moment
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
