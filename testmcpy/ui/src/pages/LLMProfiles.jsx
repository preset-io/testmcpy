import React, { useState, useEffect } from 'react'
import {
  Cpu, Check, AlertCircle, RefreshCw, ChevronDown, ChevronRight,
  Edit2, Trash2, Plus, Save, X, Copy, Download, Settings,
  CheckCircle, XCircle, AlertTriangle, DollarSign, Zap, Play, Loader2,
  Eye, EyeOff, Key, Star, Wand2
} from 'lucide-react'
import Wizard from '../components/Wizard'

// Toast notification component
function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  const bgColor = type === 'success' ? 'bg-success border-success text-white' :
                  type === 'error' ? 'bg-error border-error text-white' :
                  'bg-warning border-warning text-white'

  const icon = type === 'success' ? <CheckCircle size={16} /> :
               type === 'error' ? <XCircle size={16} /> :
               <AlertTriangle size={16} />

  return (
    <div className={`fixed top-4 right-4 ${bgColor} border-2 rounded-lg p-4 shadow-xl flex items-center gap-3 z-50 animate-slide-in`}>
      {icon}
      <span className="font-medium">{message}</span>
      <button onClick={onClose} className="ml-2 hover:opacity-70">
        <X size={16} />
      </button>
    </div>
  )
}

// Confirmation dialog component
function ConfirmDialog({ title, message, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-0 md:p-4">
      <div className="bg-surface-elevated border border-border rounded-none md:rounded-lg p-6 md:max-w-md w-full h-full md:h-auto max-h-full md:max-h-[90vh] mx-0 md:mx-4 shadow-xl">
        <h3 className="text-lg font-bold mb-2">{title}</h3>
        <p className="text-text-secondary mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button onClick={onCancel} className="btn btn-secondary">
            Cancel
          </button>
          <button onClick={onConfirm} className="btn btn-primary bg-error hover:bg-error/80">
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

// Provider icon helper
function getProviderIcon(provider) {
  switch (provider?.toLowerCase()) {
    case 'anthropic':
      return <span className="text-orange-500 font-bold text-xs">A</span>
    case 'openai':
      return <span className="text-green-500 font-bold text-xs">O</span>
    case 'google':
    case 'gemini':
      return <span className="text-blue-500 font-bold text-xs">G</span>
    case 'claude-code':
      return <span className="text-purple-500 font-bold text-xs">CC</span>
    case 'claude-sdk':
      return <span className="text-indigo-500 font-bold text-xs">SDK</span>
    case 'ollama':
      return <span className="text-text-tertiary font-bold text-xs">L</span>
    default:
      return <Cpu size={14} className="text-text-disabled" />
  }
}

// Profile editor modal
function ProfileEditorModal({ profile, onSave, onCancel }) {
  const [profileId, setProfileId] = useState(profile?.profile_id || '')
  const [name, setName] = useState(profile?.name || '')
  const [description, setDescription] = useState(profile?.description || '')
  const [errors, setErrors] = useState({})
  const isNew = !profile

  const validate = () => {
    const newErrors = {}
    if (!profileId.trim()) newErrors.profileId = 'Profile ID is required'
    if (profileId && !/^[a-z0-9-]+$/.test(profileId)) newErrors.profileId = 'Use lowercase letters, numbers, and hyphens only'
    if (!name.trim()) newErrors.name = 'Name is required'
    if (name.length > 50) newErrors.name = 'Name must be less than 50 characters'
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validate()) {
      onSave({ profileId, name, description })
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-0 md:p-4">
      <div className="bg-surface-elevated border border-border rounded-none md:rounded-lg p-6 md:max-w-md w-full h-full md:h-auto max-h-full md:max-h-[90vh] mx-0 md:mx-4 shadow-xl">
        <h3 className="text-lg font-bold mb-4">
          {isNew ? 'New LLM Profile' : 'Edit LLM Profile'}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Profile ID</label>
              <input
                type="text"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                className="input w-full"
                placeholder="e.g., prod, dev, budget"
                disabled={!isNew}
                autoFocus={isNew}
              />
              {errors.profileId && (
                <p className="text-error text-xs mt-1">{errors.profileId}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Profile Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input w-full"
                placeholder="e.g., Production, Development"
                autoFocus={!isNew}
              />
              {errors.name && (
                <p className="text-error text-xs mt-1">{errors.name}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input w-full"
                rows={3}
                placeholder="Describe when to use this profile..."
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button type="button" onClick={onCancel} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              <Save size={16} />
              {isNew ? 'Create Profile' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Provider editor modal with model registry
function ProviderEditorModal({ provider, availableModels, onSave, onCancel }) {
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    provider: provider?.provider || 'anthropic',
    model: provider?.model || '',
    api_key: provider?.api_key || '',  // Direct API key
    api_key_env: provider?.api_key_env || '',  // Or env var name
    base_url: provider?.base_url || '',
    timeout: provider?.timeout || 60,
    default: provider?.default || false,
  })
  const [showApiKey, setShowApiKey] = useState(false)  // Toggle visibility
  const [errors, setErrors] = useState({})
  const [filteredModels, setFilteredModels] = useState([])

  useEffect(() => {
    // Filter models based on selected provider
    if (availableModels && formData.provider) {
      const providerKey = formData.provider.toLowerCase()
      const filtered = availableModels.filter(m =>
        m.provider === providerKey ||
        (providerKey === 'gemini' && m.provider === 'google')
      )
      setFilteredModels(filtered)

      // Auto-select first model if current model is not in filtered list
      if (filtered.length > 0 && !filtered.find(m => m.id === formData.model)) {
        const defaultModel = filtered.find(m => m.is_default) || filtered[0]
        setFormData(prev => ({ ...prev, model: defaultModel.id, name: defaultModel.name }))
      }
    }
  }, [formData.provider, availableModels])

  const validate = () => {
    const newErrors = {}
    if (!formData.name.trim()) newErrors.name = 'Name is required'
    if (!formData.model.trim()) newErrors.model = 'Model is required'
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validate()) {
      onSave(formData)
    }
  }

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }

  const handleModelSelect = (modelId) => {
    const model = availableModels.find(m => m.id === modelId)
    if (model) {
      updateField('model', modelId)
      if (!formData.name || formData.name === provider?.name) {
        updateField('name', model.name)
      }
    }
  }

  const selectedModel = availableModels?.find(m => m.id === formData.model)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto p-0 md:p-4">
      <div className="bg-surface-elevated border border-border rounded-none md:rounded-lg p-6 md:max-w-2xl w-full h-full md:h-auto max-h-full md:max-h-[90vh] my-0 md:my-8 shadow-xl overflow-y-auto">
        <h3 className="text-lg font-bold mb-4">
          {provider ? 'Edit Provider' : 'Add Provider'}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            {/* Provider Type */}
            <div>
              <label className="block text-sm font-medium mb-1">Provider</label>
              <select
                value={formData.provider}
                onChange={(e) => updateField('provider', e.target.value)}
                className="input w-full"
              >
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI (GPT)</option>
                <option value="google">Google (Gemini)</option>
                <option value="claude-code">Claude Code CLI</option>
                <option value="claude-sdk">Claude Agent SDK</option>
                <option value="ollama">Ollama (Local)</option>
              </select>
            </div>

            {/* Model Selection */}
            <div>
              <label className="block text-sm font-medium mb-1">Model</label>
              {filteredModels.length > 0 ? (
                <select
                  value={formData.model}
                  onChange={(e) => handleModelSelect(e.target.value)}
                  className="input w-full"
                >
                  {filteredModels.map(model => (
                    <option key={model.id} value={model.id}>
                      {model.name} - ${model.input_price_per_1m}/1M in, ${model.output_price_per_1m}/1M out
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={formData.model}
                  onChange={(e) => updateField('model', e.target.value)}
                  className="input w-full font-mono text-sm"
                  placeholder="e.g., claude-sonnet-4-5-20250514"
                />
              )}
              {errors.model && <p className="text-error text-xs mt-1">{errors.model}</p>}
            </div>

            {/* Model Info Card */}
            {selectedModel && (
              <div className="bg-surface rounded-lg p-3 border border-border">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{selectedModel.name}</div>
                    <div className="text-xs text-text-secondary mt-1">{selectedModel.description}</div>
                  </div>
                  <div className="text-right text-xs">
                    <div className="flex items-center gap-1 text-text-secondary">
                      <DollarSign size={12} />
                      ${selectedModel.input_price_per_1m}/1M in
                    </div>
                    <div className="flex items-center gap-1 text-text-secondary">
                      <DollarSign size={12} />
                      ${selectedModel.output_price_per_1m}/1M out
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {selectedModel.capabilities?.map(cap => (
                    <span key={cap} className="px-1.5 py-0.5 bg-primary/10 text-primary text-xs rounded">
                      {cap}
                    </span>
                  ))}
                </div>
                <div className="text-xs text-text-tertiary mt-2">
                  Context: {selectedModel.context_window?.toLocaleString()} tokens
                </div>
              </div>
            )}

            {/* Display Name */}
            <div>
              <label className="block text-sm font-medium mb-1">Display Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => updateField('name', e.target.value)}
                className="input w-full"
                placeholder="e.g., Claude Sonnet 4.5"
              />
              {errors.name && <p className="text-error text-xs mt-1">{errors.name}</p>}
            </div>

            {/* API Key Section - hidden for claude-code and claude-sdk */}
            {!['claude-code', 'claude-sdk'].includes(formData.provider) && (
              <div className="space-y-3 p-3 bg-surface rounded-lg border border-border">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Key size={14} />
                  API Key Configuration
                </div>

                {/* Direct API Key */}
                <div>
                  <label className="block text-xs font-medium mb-1 text-text-secondary">API Key (direct)</label>
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={formData.api_key}
                      onChange={(e) => updateField('api_key', e.target.value)}
                      className="input w-full font-mono text-sm pr-10"
                      placeholder="sk-ant-... or sk-..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-surface-hover rounded"
                    >
                      {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>

                <div className="text-center text-xs text-text-tertiary">— or —</div>

                {/* Environment Variable */}
                <div>
                  <label className="block text-xs font-medium mb-1 text-text-secondary">Environment Variable</label>
                  <input
                    type="text"
                    value={formData.api_key_env}
                    onChange={(e) => updateField('api_key_env', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="e.g., ANTHROPIC_API_KEY"
                  />
                  <p className="text-text-tertiary text-xs mt-1">
                    Leave both empty to use default env var for the provider
                  </p>
                </div>
              </div>
            )}

            {/* Info for Claude Code/SDK */}
            {['claude-code', 'claude-sdk'].includes(formData.provider) && (
              <div className="p-3 bg-primary/10 rounded-lg border border-primary/30 text-sm">
                <div className="flex items-center gap-2 font-medium text-primary">
                  <CheckCircle size={14} />
                  No API key needed
                </div>
                <p className="text-text-secondary mt-1 text-xs">
                  Uses Claude Code authentication. Make sure you're logged in via <code className="bg-surface px-1 rounded">claude auth</code>
                </p>
              </div>
            )}

            {/* Base URL (for Ollama) */}
            {formData.provider === 'ollama' && (
              <div>
                <label className="block text-sm font-medium mb-1">Base URL</label>
                <input
                  type="text"
                  value={formData.base_url}
                  onChange={(e) => updateField('base_url', e.target.value)}
                  className="input w-full font-mono text-sm"
                  placeholder="http://localhost:11434"
                />
              </div>
            )}

            {/* Timeout */}
            <div>
              <label className="block text-sm font-medium mb-1">Timeout (seconds)</label>
              <input
                type="number"
                value={formData.timeout}
                onChange={(e) => updateField('timeout', parseInt(e.target.value) || 60)}
                className="input w-full"
                min="10"
                max="300"
              />
            </div>

            {/* Default Provider */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="default"
                checked={formData.default}
                onChange={(e) => updateField('default', e.target.checked)}
                className="w-4 h-4"
              />
              <label htmlFor="default" className="text-sm">
                <span className="font-medium">Set as default provider</span>
                <span className="text-text-tertiary ml-1">(used when no specific provider requested)</span>
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-border">
            <button type="button" onClick={onCancel} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              <Save size={16} />
              Save Provider
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// LLM Provider Wizard - guided multi-step flow for adding a provider
function LLMWizard({ profiles, availableModels, onComplete, onCancel }) {
  const [wizardData, setWizardData] = useState({
    // Step 1: Provider type
    provider: 'anthropic',
    // Step 2: Model selection
    model: '',
    name: '',
    // Step 3: Credentials
    api_key: '',
    api_key_env: '',
    base_url: '',
    timeout: 60,
    default: false,
    showApiKey: false,
    // Test result
    testResult: null,
    testLoading: false,
    // Step 4: Save
    targetProfileId: profiles.length > 0 ? profiles[0].profile_id : '',
  })

  const providerCards = [
    { value: 'anthropic', label: 'Anthropic', desc: 'Claude models - Sonnet, Opus, Haiku', color: 'text-orange-500', letter: 'A' },
    { value: 'openai', label: 'OpenAI', desc: 'GPT-4o, GPT-4 Turbo, o1 models', color: 'text-green-500', letter: 'O' },
    { value: 'google', label: 'Gemini', desc: 'Gemini 2.5 Pro/Flash, 1.5 Pro', color: 'text-blue-500', letter: 'G' },
    { value: 'ollama', label: 'Ollama', desc: 'Local models (Llama, Mistral, etc.)', color: 'text-text-tertiary', letter: 'L' },
    { value: 'claude-sdk', label: 'Claude SDK', desc: 'Agent SDK, uses Claude auth', color: 'text-indigo-500', letter: 'SDK' },
    { value: 'claude-code', label: 'Claude Code', desc: 'Claude Code CLI, no API key needed', color: 'text-purple-500', letter: 'CC' },
  ]

  // Get filtered models for selected provider
  const getFilteredModels = () => {
    if (!availableModels || !wizardData.provider) return []
    const key = wizardData.provider.toLowerCase()
    return availableModels.filter(m =>
      m.provider === key || (key === 'gemini' && m.provider === 'google')
    )
  }

  const handleTestCredentials = async () => {
    setWizardData(prev => ({ ...prev, testLoading: true, testResult: null }))
    try {
      const res = await fetch('/api/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: wizardData.provider,
          model: wizardData.model,
          api_key: wizardData.api_key || null,
          api_key_env: wizardData.api_key_env || null,
          base_url: wizardData.base_url || null,
          timeout: wizardData.timeout,
        })
      })
      const data = await res.json()
      setWizardData(prev => ({
        ...prev,
        testLoading: false,
        testResult: data
      }))
    } catch (err) {
      setWizardData(prev => ({
        ...prev,
        testLoading: false,
        testResult: { success: false, error: err.message }
      }))
    }
  }

  const steps = [
    {
      label: 'Provider',
      validate: (data) => {
        if (!data.provider) return 'Please select a provider'
        return true
      },
      component: ({ data, setData }) => (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">Choose your LLM provider:</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {providerCards.map(p => (
              <button
                key={p.value}
                type="button"
                onClick={() => {
                  setData(prev => ({ ...prev, provider: p.value, model: '', name: '' }))
                }}
                className={`p-4 rounded-lg border-2 text-left transition-all ${
                  data.provider === p.value
                    ? 'border-primary bg-primary/10'
                    : 'border-border hover:border-primary/30'
                }`}
              >
                <div className={`text-lg font-bold ${p.color} mb-1`}>{p.letter}</div>
                <div className="font-medium text-sm">{p.label}</div>
                <div className="text-xs text-text-tertiary mt-1">{p.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ),
    },
    {
      label: 'Model',
      validate: (data) => {
        if (!data.model.trim()) return 'Please select or enter a model'
        return true
      },
      component: ({ data, setData }) => {
        const filtered = getFilteredModels()
        const selectedModel = availableModels?.find(m => m.id === data.model)

        return (
          <div className="space-y-4">
            {filtered.length > 0 ? (
              <>
                <div>
                  <label className="block text-sm font-medium mb-1">Select Model</label>
                  <select
                    value={data.model}
                    onChange={(e) => {
                      const model = availableModels.find(m => m.id === e.target.value)
                      setData(prev => ({
                        ...prev,
                        model: e.target.value,
                        name: model?.name || prev.name,
                      }))
                    }}
                    className="input w-full"
                    autoFocus
                  >
                    <option value="">Choose a model...</option>
                    {filtered.map(model => (
                      <option key={model.id} value={model.id}>
                        {model.name} - ${model.input_price_per_1m}/1M in, ${model.output_price_per_1m}/1M out
                      </option>
                    ))}
                  </select>
                </div>

                {selectedModel && (
                  <div className="bg-surface rounded-lg p-3 border border-border">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-medium">{selectedModel.name}</div>
                        <div className="text-xs text-text-secondary mt-1">{selectedModel.description}</div>
                      </div>
                      <div className="text-right text-xs">
                        <div className="flex items-center gap-1 text-text-secondary">
                          <DollarSign size={12} /> ${selectedModel.input_price_per_1m}/1M in
                        </div>
                        <div className="flex items-center gap-1 text-text-secondary">
                          <DollarSign size={12} /> ${selectedModel.output_price_per_1m}/1M out
                        </div>
                      </div>
                    </div>
                    {selectedModel.capabilities?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {selectedModel.capabilities.map(cap => (
                          <span key={cap} className="px-1.5 py-0.5 bg-primary/10 text-primary text-xs rounded">
                            {cap}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="text-xs text-text-tertiary mt-2">
                      Context: {selectedModel.context_window?.toLocaleString()} tokens
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div>
                <label className="block text-sm font-medium mb-1">Model ID</label>
                <input
                  type="text"
                  value={data.model}
                  onChange={(e) => setData(prev => ({ ...prev, model: e.target.value }))}
                  className="input w-full font-mono text-sm"
                  placeholder="e.g., llama3.2:latest"
                  autoFocus
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-1">Display Name</label>
              <input
                type="text"
                value={data.name}
                onChange={(e) => setData(prev => ({ ...prev, name: e.target.value }))}
                className="input w-full"
                placeholder="e.g., Claude Sonnet 4"
              />
            </div>
          </div>
        )
      },
    },
    {
      label: 'Credentials',
      optional: ['claude-code', 'claude-sdk'].includes(wizardData.provider),
      validate: (data) => {
        if (!data.name.trim()) return 'Display name is required'
        return true
      },
      component: ({ data, setData }) => {
        const noKeyNeeded = ['claude-code', 'claude-sdk'].includes(data.provider)

        return (
          <div className="space-y-4">
            {noKeyNeeded ? (
              <div className="p-3 bg-primary/10 rounded-lg border border-primary/30 text-sm">
                <div className="flex items-center gap-2 font-medium text-primary">
                  <CheckCircle size={14} /> No API key needed
                </div>
                <p className="text-text-secondary mt-1 text-xs">
                  Uses Claude Code authentication. Make sure you are logged in via <code className="bg-surface px-1 rounded">claude auth</code>
                </p>
              </div>
            ) : (
              <div className="space-y-3 p-3 bg-surface rounded-lg border border-border">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Key size={14} /> API Key Configuration
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1 text-text-secondary">API Key (direct)</label>
                  <div className="relative">
                    <input
                      type={data.showApiKey ? 'text' : 'password'}
                      value={data.api_key}
                      onChange={(e) => setData(prev => ({ ...prev, api_key: e.target.value }))}
                      className="input w-full font-mono text-sm pr-10"
                      placeholder="sk-ant-... or sk-..."
                    />
                    <button
                      type="button"
                      onClick={() => setData(prev => ({ ...prev, showApiKey: !prev.showApiKey }))}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-surface-hover rounded"
                    >
                      {data.showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
                <div className="text-center text-xs text-text-tertiary">-- or --</div>
                <div>
                  <label className="block text-xs font-medium mb-1 text-text-secondary">Environment Variable</label>
                  <input
                    type="text"
                    value={data.api_key_env}
                    onChange={(e) => setData(prev => ({ ...prev, api_key_env: e.target.value }))}
                    className="input w-full font-mono text-sm"
                    placeholder="e.g., ANTHROPIC_API_KEY"
                  />
                  <p className="text-text-tertiary text-xs mt-1">Leave both empty to use default env var</p>
                </div>
              </div>
            )}

            {data.provider === 'ollama' && (
              <div>
                <label className="block text-sm font-medium mb-1">Base URL</label>
                <input
                  type="text"
                  value={data.base_url}
                  onChange={(e) => setData(prev => ({ ...prev, base_url: e.target.value }))}
                  className="input w-full font-mono text-sm"
                  placeholder="http://localhost:11434"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-1">Timeout (seconds)</label>
              <input
                type="number"
                value={data.timeout}
                onChange={(e) => setData(prev => ({ ...prev, timeout: parseInt(e.target.value) || 60 }))}
                className="input w-full"
                min="10" max="300"
              />
            </div>

            <div className="flex items-center gap-2">
              <input type="checkbox" id="wiz_default_llm"
                checked={data.default}
                onChange={(e) => setData(prev => ({ ...prev, default: e.target.checked }))}
                className="w-4 h-4" />
              <label htmlFor="wiz_default_llm" className="text-sm">
                <span className="font-medium">Set as default provider</span>
              </label>
            </div>

            {/* Test button */}
            <div className="pt-2 border-t border-border">
              <button
                onClick={handleTestCredentials}
                disabled={data.testLoading}
                className="btn btn-secondary text-sm"
              >
                {data.testLoading ? (
                  <><Loader2 size={14} className="animate-spin" /> Testing...</>
                ) : (
                  <><Play size={14} /> Test Credentials</>
                )}
              </button>
              {data.testResult && (
                <div className={`mt-2 p-2 rounded text-xs ${
                  data.testResult.success
                    ? 'bg-success/10 border border-success/30'
                    : 'bg-error/10 border border-error/30'
                }`}>
                  <div className="flex items-center gap-1.5">
                    {data.testResult.success ? (
                      <><CheckCircle size={12} className="text-success" />
                        <span className="text-success">Test passed</span></>
                    ) : (
                      <><XCircle size={12} className="text-error" />
                        <span className="text-error">Test failed</span></>
                    )}
                    {data.testResult.duration && (
                      <span className="text-text-tertiary ml-auto">{data.testResult.duration.toFixed(2)}s</span>
                    )}
                  </div>
                  {data.testResult.error && (
                    <div className="mt-1 text-error">{data.testResult.error}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      },
    },
    {
      label: 'Save',
      validate: (data) => {
        if (!data.targetProfileId) return 'Please select a profile'
        return true
      },
      component: ({ data, setData }) => {
        const selectedModel = availableModels?.find(m => m.id === data.model)
        return (
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-text-secondary">Review your LLM provider configuration:</h4>
            <div className="bg-surface rounded-lg p-4 border border-border space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-tertiary">Provider</span>
                <span className="font-medium">{data.provider}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-tertiary">Model</span>
                <span className="font-mono text-xs">{data.model}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-tertiary">Display Name</span>
                <span>{data.name}</span>
              </div>
              {selectedModel && (
                <div className="flex justify-between">
                  <span className="text-text-tertiary">Pricing</span>
                  <span className="text-xs">${selectedModel.input_price_per_1m}/1M in, ${selectedModel.output_price_per_1m}/1M out</span>
                </div>
              )}
              {data.testResult?.success && (
                <div className="flex justify-between">
                  <span className="text-text-tertiary">Credential Test</span>
                  <span className="text-success flex items-center gap-1"><CheckCircle size={12} /> Passed</span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Add to Profile</label>
              <select
                value={data.targetProfileId}
                onChange={(e) => setData(prev => ({ ...prev, targetProfileId: e.target.value }))}
                className="input w-full"
              >
                {profiles.map(p => (
                  <option key={p.profile_id} value={p.profile_id}>{p.name}</option>
                ))}
              </select>
            </div>
          </div>
        )
      },
    },
  ]

  const handleComplete = (data) => {
    const providerData = {
      name: data.name,
      provider: data.provider,
      model: data.model,
      api_key: data.api_key || undefined,
      api_key_env: data.api_key_env || undefined,
      base_url: data.base_url || undefined,
      timeout: data.timeout,
      default: data.default,
    }
    onComplete(data.targetProfileId, providerData)
  }

  return (
    <Wizard
      title="Add LLM Provider"
      steps={steps}
      data={wizardData}
      setData={setWizardData}
      onComplete={handleComplete}
      onCancel={onCancel}
    />
  )
}

function LLMProfiles({ selectedProfile, onSelectProfile, onProfilesChange, hideHeader = false }) {
  const [profiles, setProfiles] = useState([])
  const [defaultProfile, setDefaultProfile] = useState(null)
  const [availableModels, setAvailableModels] = useState([])
  const [expandedProfiles, setExpandedProfiles] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [profileEditor, setProfileEditor] = useState(null)
  const [providerEditor, setProviderEditor] = useState(null)
  const [testingProvider, setTestingProvider] = useState(null) // "profileId:providerIndex"
  const [testResults, setTestResults] = useState({}) // { "profileId:providerIndex": { success, response, error, duration } }
  const [showLLMWizard, setShowLLMWizard] = useState(false)

  useEffect(() => {
    loadProfiles()
    loadAvailableModels()
  }, [])

  useEffect(() => {
    // Auto-expand all profiles when they're loaded
    if (profiles.length > 0) {
      const allProfileIds = profiles.map(p => p.profile_id)
      setExpandedProfiles(new Set(allProfileIds))
    }
  }, [profiles])

  const loadProfiles = async (notifyParent = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/llm/profiles')
      const data = await res.json()

      if (data.message && data.profiles?.length === 0) {
        setError(data.message)
      } else {
        setProfiles(data.profiles || [])
        setDefaultProfile(data.default)
        // Notify parent component to refresh its state
        if (notifyParent && onProfilesChange) {
          onProfilesChange()
        }
      }
    } catch (error) {
      console.error('Failed to load LLM profiles:', error)
      setError('Failed to load LLM profiles')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableModels = async () => {
    try {
      const res = await fetch('/api/llm/models')
      const data = await res.json()
      setAvailableModels(data.models || [])
    } catch (error) {
      console.error('Failed to load available models:', error)
    }
  }

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
  }

  const toggleExpanded = (profileId) => {
    const newExpanded = new Set(expandedProfiles)
    if (newExpanded.has(profileId)) {
      newExpanded.delete(profileId)
    } else {
      newExpanded.add(profileId)
    }
    setExpandedProfiles(newExpanded)
  }

  // Test provider connection
  const handleTestProvider = async (profileId, providerIndex, provider) => {
    const testKey = `${profileId}:${providerIndex}`
    setTestingProvider(testKey)
    // Clear previous result for this provider
    setTestResults(prev => ({ ...prev, [testKey]: null }))

    try {
      const res = await fetch('/api/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: provider.provider,
          model: provider.model,
          api_key: provider.api_key || null,  // Direct API key
          api_key_env: provider.api_key_env || null,  // Or env var name
          base_url: provider.base_url || null,
          timeout: provider.timeout || 30,
        })
      })
      const data = await res.json()

      setTestResults(prev => ({ ...prev, [testKey]: data }))

      if (data.success) {
        showToast(`Test passed: ${data.response?.substring(0, 50) || 'OK'}`)
      } else {
        showToast(data.error || 'Test failed', 'error')
      }
    } catch (error) {
      const errorResult = { success: false, error: error.message }
      setTestResults(prev => ({ ...prev, [testKey]: errorResult }))
      showToast(`Test failed: ${error.message}`, 'error')
    } finally {
      setTestingProvider(null)
    }
  }

  // Profile operations
  const handleCreateProfile = async (profileData) => {
    try {
      const res = await fetch(`/api/llm/profiles/${profileData.profileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: profileData.name,
          description: profileData.description,
          providers: []
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setProfileEditor(null)
        showToast('Profile created successfully')
      } else {
        showToast(data.detail || 'Failed to create profile', 'error')
      }
    } catch (error) {
      console.error('Failed to create profile:', error)
      showToast('Failed to create profile', 'error')
    }
  }

  const handleUpdateProfile = async (profileId, profileData) => {
    try {
      // Get current profile data
      const currentProfile = profiles.find(p => p.profile_id === profileId)

      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: profileData.name,
          description: profileData.description,
          providers: currentProfile?.providers || []
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setProfileEditor(null)
        showToast('Profile updated successfully')
      } else {
        showToast(data.detail || 'Failed to update profile', 'error')
      }
    } catch (error) {
      console.error('Failed to update profile:', error)
      showToast('Failed to update profile', 'error')
    }
  }

  const handleDeleteProfile = async (profileId) => {
    try {
      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'DELETE'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setConfirmDialog(null)
        showToast('Profile deleted successfully')
      } else {
        showToast(data.detail || 'Failed to delete profile', 'error')
      }
    } catch (error) {
      console.error('Failed to delete profile:', error)
      showToast('Failed to delete profile', 'error')
    }
  }

  const handleSetDefault = async (profileId) => {
    try {
      const res = await fetch(`/api/llm/profiles/default/${profileId}`, {
        method: 'PUT'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        if (onSelectProfile) {
          onSelectProfile(profileId)
        }
        showToast('Default profile updated')
      } else {
        showToast(data.detail || 'Failed to set default profile', 'error')
      }
    } catch (error) {
      console.error('Failed to set default:', error)
      showToast('Failed to set default profile', 'error')
    }
  }

  // Provider operations
  const handleAddProvider = async (profileId, providerData) => {
    try {
      const currentProfile = profiles.find(p => p.profile_id === profileId)
      let updatedProviders = [...(currentProfile?.providers || [])]

      // If the new provider is default, unset default on all existing providers
      if (providerData.default) {
        updatedProviders = updatedProviders.map(p => ({ ...p, default: false }))
      }

      updatedProviders.push(providerData)

      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: currentProfile.name,
          description: currentProfile.description,
          providers: updatedProviders
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setProviderEditor(null)
        showToast('Provider added successfully')
      } else {
        showToast(data.detail || 'Failed to add provider', 'error')
      }
    } catch (error) {
      console.error('Failed to add provider:', error)
      showToast('Failed to add provider', 'error')
    }
  }

  const handleUpdateProvider = async (profileId, providerIndex, providerData) => {
    try {
      const currentProfile = profiles.find(p => p.profile_id === profileId)
      let updatedProviders = [...currentProfile.providers]

      // If the updated provider is default, unset default on all other providers
      if (providerData.default) {
        updatedProviders = updatedProviders.map((p, idx) =>
          idx === providerIndex ? p : { ...p, default: false }
        )
      }

      updatedProviders[providerIndex] = providerData

      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: currentProfile.name,
          description: currentProfile.description,
          providers: updatedProviders
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setProviderEditor(null)
        showToast('Provider updated successfully')
      } else {
        showToast(data.detail || 'Failed to update provider', 'error')
      }
    } catch (error) {
      console.error('Failed to update provider:', error)
      showToast('Failed to update provider', 'error')
    }
  }

  // Set a provider as default (quick action without opening modal)
  const handleSetDefaultProvider = async (profileId, providerIndex) => {
    try {
      const currentProfile = profiles.find(p => p.profile_id === profileId)
      // Set all providers to non-default, except the selected one
      const updatedProviders = currentProfile.providers.map((p, idx) => ({
        ...p,
        default: idx === providerIndex
      }))

      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: currentProfile.name,
          description: currentProfile.description,
          providers: updatedProviders
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        showToast(`${currentProfile.providers[providerIndex].name} set as default`)
      } else {
        showToast(data.detail || 'Failed to set default provider', 'error')
      }
    } catch (error) {
      console.error('Failed to set default provider:', error)
      showToast('Failed to set default provider', 'error')
    }
  }

  const handleDeleteProvider = async (profileId, providerIndex) => {
    try {
      const currentProfile = profiles.find(p => p.profile_id === profileId)
      const updatedProviders = currentProfile.providers.filter((_, idx) => idx !== providerIndex)

      const res = await fetch(`/api/llm/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: currentProfile.name,
          description: currentProfile.description,
          providers: updatedProviders
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        setConfirmDialog(null)
        showToast('Provider removed successfully')
      } else {
        showToast(data.detail || 'Failed to remove provider', 'error')
      }
    } catch (error) {
      console.error('Failed to remove provider:', error)
      showToast('Failed to remove provider', 'error')
    }
  }

  const createDefaultConfig = async () => {
    try {
      // Create a default profile with Claude Sonnet
      const res = await fetch('/api/llm/profiles/prod', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Production',
          description: 'High-quality models for production use',
          providers: [{
            name: 'Claude Sonnet 4.5',
            provider: 'anthropic',
            model: 'claude-sonnet-4-5-20250514',
            timeout: 60,
            default: true
          }]
        })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles(true)
        showToast('Default configuration created')
      } else {
        showToast(data.detail || 'Failed to create configuration', 'error')
      }
    } catch (error) {
      console.error('Failed to create configuration:', error)
      showToast('Failed to create configuration', 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-text-secondary">Loading LLM profiles...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      {!hideHeader && (
        <div className="p-4 border-b border-border bg-surface-elevated">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl md:text-2xl font-bold">LLM Profiles</h1>
              <p className="text-text-secondary mt-1 text-base">
                Configure LLM providers for testing and chat
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={loadProfiles}
                className="btn btn-secondary flex items-center gap-2"
              >
                <RefreshCw size={16} />
                Refresh
              </button>
              <button
                onClick={() => setShowLLMWizard(true)}
                className="btn btn-primary flex items-center gap-2"
              >
                <Wand2 size={16} />
                Add Provider (Wizard)
              </button>
              <button
                onClick={() => setProfileEditor({ isNew: true })}
                className="btn btn-secondary flex items-center gap-2"
              >
                <Plus size={16} />
                Add Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {error && profiles.length === 0 ? (
          <div className="max-w-2xl mx-auto">
            <div className="bg-surface-elevated border border-warning rounded-lg p-4 flex items-start gap-3">
              <AlertCircle size={20} className="text-warning mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="font-medium text-warning mb-1">No Configuration Found</h3>
                <p className="text-text-secondary text-sm mb-3">{error}</p>
                <p className="text-text-secondary text-sm mb-4">
                  Create an LLM provider profile to get started with testing and chat features.
                </p>
                <button
                  onClick={createDefaultConfig}
                  className="btn btn-primary"
                >
                  Create Default Configuration
                </button>
              </div>
            </div>
          </div>
        ) : profiles.length === 0 ? (
          <div className="max-w-2xl mx-auto text-center py-12">
            <Cpu size={48} className="text-text-disabled mx-auto mb-4" />
            <h2 className="text-xl font-medium mb-2">No LLM Profiles Found</h2>
            <p className="text-text-secondary mb-4">
              Create an LLM provider profile to configure your AI models
            </p>
            <button
              onClick={() => setProfileEditor({ isNew: true })}
              className="btn btn-primary"
            >
              <Plus size={16} />
              Create Profile
            </button>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            <div className="mb-4 text-sm text-text-secondary">
              Click the star icon to set a profile as default. Add providers to each profile for different use cases.
            </div>

            <div className="grid gap-3">
              {profiles.map((profile) => {
                const isDefault = profile.profile_id === defaultProfile
                const isExpanded = expandedProfiles.has(profile.profile_id)
                const providers = profile.providers || []
                const hasProviders = providers.length > 0
                const defaultProvider = providers.find(p => p.default) || providers[0]

                return (
                  <div
                    key={profile.profile_id}
                    className="border rounded-lg p-4 transition-all border-border bg-surface-elevated"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3 flex-1">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-medium">{profile.name}</h3>
                            <code className="text-xs text-text-tertiary bg-surface px-1 rounded">{profile.profile_id}</code>
                            {isDefault && (
                              <span className="px-2 py-0.5 text-xs rounded-full bg-primary/20 text-primary">
                                Default
                              </span>
                            )}
                            {hasProviders && (
                              <span className="px-2 py-0.5 text-xs rounded-full bg-surface border border-border text-text-secondary">
                                {providers.length} provider{providers.length !== 1 ? 's' : ''}
                              </span>
                            )}
                          </div>

                          {profile.description && (
                            <p className="text-sm text-text-secondary mb-2">
                              {profile.description}
                            </p>
                          )}

                          {hasProviders && !isExpanded && defaultProvider && (
                            <div className="text-xs text-text-tertiary flex items-center gap-2">
                              {getProviderIcon(defaultProvider.provider)}
                              <span>{defaultProvider.name}</span>
                              <span className="text-text-disabled">({defaultProvider.model})</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        {/* Profile Actions */}
                        {!isDefault && (
                          <button
                            onClick={() => handleSetDefault(profile.profile_id)}
                            className="p-2 hover:bg-surface-hover rounded transition-colors"
                            title="Set as default"
                          >
                            <Settings size={16} className="text-text-secondary" />
                          </button>
                        )}

                        <button
                          onClick={() => setProfileEditor({ profile, profileId: profile.profile_id })}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Edit profile"
                        >
                          <Edit2 size={16} className="text-text-secondary" />
                        </button>

                        <button
                          onClick={() => setConfirmDialog({
                            title: 'Delete Profile',
                            message: `Are you sure you want to delete "${profile.name}"? This action cannot be undone.`,
                            onConfirm: () => handleDeleteProfile(profile.profile_id)
                          })}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Delete profile"
                        >
                          <Trash2 size={16} className="text-error" />
                        </button>

                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleExpanded(profile.profile_id)
                          }}
                          className="p-2 hover:bg-surface-hover rounded transition-colors ml-1"
                          title={isExpanded ? "Hide providers" : "Show providers"}
                        >
                          {isExpanded ? (
                            <ChevronDown size={18} className="text-text-secondary" />
                          ) : (
                            <ChevronRight size={18} className="text-text-secondary" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Expanded Provider Details */}
                    {isExpanded && (
                      <div className="mt-4 space-y-2">
                        {providers.map((provider, idx) => {
                          const modelInfo = availableModels.find(m => m.id === provider.model)

                          return (
                            <div
                              key={idx}
                              className={`rounded-lg p-3 space-y-2 transition-all ${
                                provider.default
                                  ? 'bg-primary/10 border-2 border-primary'
                                  : 'bg-surface border-2 border-transparent'
                              }`}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex items-center gap-2 flex-1">
                                  {provider.default && <Check size={14} className="text-primary flex-shrink-0" />}
                                  {getProviderIcon(provider.provider)}
                                  <span className="font-medium text-sm">{provider.name}</span>
                                  <span className="text-xs text-text-tertiary px-1.5 py-0.5 bg-surface-elevated rounded">
                                    {provider.provider}
                                  </span>
                                </div>

                                {/* Provider Actions */}
                                <div className="flex items-center gap-1">
                                  {/* Set as default button */}
                                  {!provider.default && (
                                    <button
                                      onClick={() => handleSetDefaultProvider(profile.profile_id, idx)}
                                      className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                      title="Set as default provider"
                                    >
                                      <Star size={14} className="text-text-tertiary hover:text-warning" />
                                    </button>
                                  )}
                                  {provider.default && (
                                    <span className="p-1" title="Default provider">
                                      <Star size={14} className="text-warning fill-warning" />
                                    </span>
                                  )}

                                  <button
                                    onClick={() => handleTestProvider(profile.profile_id, idx, provider)}
                                    disabled={testingProvider === `${profile.profile_id}:${idx}`}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors disabled:opacity-50"
                                    title="Test provider connection"
                                  >
                                    {testingProvider === `${profile.profile_id}:${idx}` ? (
                                      <Loader2 size={14} className="text-primary animate-spin" />
                                    ) : (
                                      <Play size={14} className="text-success" />
                                    )}
                                  </button>

                                  <button
                                    onClick={() => setProviderEditor({ provider, profileId: profile.profile_id, providerIndex: idx })}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                    title="Edit provider"
                                  >
                                    <Edit2 size={14} className="text-text-secondary" />
                                  </button>

                                  <button
                                    onClick={() => setConfirmDialog({
                                      title: 'Remove Provider',
                                      message: `Are you sure you want to remove "${provider.name}"?`,
                                      onConfirm: () => handleDeleteProvider(profile.profile_id, idx)
                                    })}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                    title="Remove provider"
                                  >
                                    <Trash2 size={14} className="text-error" />
                                  </button>
                                </div>
                              </div>

                              <div className="space-y-1.5 text-xs">
                                <div className="flex items-start gap-2">
                                  <span className="text-text-disabled min-w-[60px]">Model:</span>
                                  <code className="font-mono bg-surface-elevated px-2 py-0.5 rounded flex-1">
                                    {provider.model}
                                  </code>
                                </div>

                                {modelInfo && (
                                  <div className="flex items-center gap-3 text-text-tertiary">
                                    <span className="flex items-center gap-1">
                                      <DollarSign size={12} />
                                      ${modelInfo.input_price_per_1m}/1M in
                                    </span>
                                    <span className="flex items-center gap-1">
                                      <DollarSign size={12} />
                                      ${modelInfo.output_price_per_1m}/1M out
                                    </span>
                                    <span className="flex items-center gap-1">
                                      <Zap size={12} />
                                      {(modelInfo.context_window / 1000).toFixed(0)}K ctx
                                    </span>
                                  </div>
                                )}

                                {provider.timeout && (
                                  <div className="text-text-tertiary">
                                    Timeout: {provider.timeout}s
                                  </div>
                                )}

                                {/* Test Result Display */}
                                {testResults[`${profile.profile_id}:${idx}`] && (
                                  <div className={`mt-2 p-2 rounded text-xs ${
                                    testResults[`${profile.profile_id}:${idx}`].success
                                      ? 'bg-success/10 border border-success/30'
                                      : 'bg-error/10 border border-error/30'
                                  }`}>
                                    <div className="flex items-center gap-1.5">
                                      {testResults[`${profile.profile_id}:${idx}`].success ? (
                                        <CheckCircle size={12} className="text-success" />
                                      ) : (
                                        <XCircle size={12} className="text-error" />
                                      )}
                                      <span className={testResults[`${profile.profile_id}:${idx}`].success ? 'text-success' : 'text-error'}>
                                        {testResults[`${profile.profile_id}:${idx}`].success ? 'Test passed' : 'Test failed'}
                                      </span>
                                      {testResults[`${profile.profile_id}:${idx}`].duration && (
                                        <span className="text-text-tertiary ml-auto">
                                          {testResults[`${profile.profile_id}:${idx}`].duration.toFixed(2)}s
                                        </span>
                                      )}
                                    </div>
                                    {testResults[`${profile.profile_id}:${idx}`].response && (
                                      <div className="mt-1 text-text-secondary truncate">
                                        Response: {testResults[`${profile.profile_id}:${idx}`].response}
                                      </div>
                                    )}
                                    {testResults[`${profile.profile_id}:${idx}`].error && (
                                      <div className="mt-1 text-error">
                                        Error: {testResults[`${profile.profile_id}:${idx}`].error}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          )
                        })}

                        {/* Add Provider Button */}
                        <button
                          onClick={() => setProviderEditor({ profileId: profile.profile_id, isNew: true })}
                          className="w-full p-3 border-2 border-dashed border-border rounded-lg hover:border-primary hover:bg-primary/5 transition-all flex items-center justify-center gap-2 text-text-secondary hover:text-primary"
                        >
                          <Plus size={16} />
                          Add Provider
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Modals and Dialogs */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      {confirmDialog && (
        <ConfirmDialog
          title={confirmDialog.title}
          message={confirmDialog.message}
          onConfirm={confirmDialog.onConfirm}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {profileEditor && (
        <ProfileEditorModal
          profile={profileEditor.profile}
          onSave={(data) => {
            if (profileEditor.isNew) {
              handleCreateProfile(data)
            } else {
              handleUpdateProfile(profileEditor.profileId, data)
            }
          }}
          onCancel={() => setProfileEditor(null)}
        />
      )}

      {providerEditor && (
        <ProviderEditorModal
          provider={providerEditor.provider}
          availableModels={availableModels}
          onSave={(data) => {
            if (providerEditor.isNew) {
              handleAddProvider(providerEditor.profileId, data)
            } else {
              handleUpdateProvider(providerEditor.profileId, providerEditor.providerIndex, data)
            }
          }}
          onCancel={() => setProviderEditor(null)}
        />
      )}

      {showLLMWizard && (
        <LLMWizard
          profiles={profiles}
          availableModels={availableModels}
          onComplete={(profileId, providerData) => {
            handleAddProvider(profileId, providerData)
            setShowLLMWizard(false)
          }}
          onCancel={() => setShowLLMWizard(false)}
        />
      )}
    </div>
  )
}

export default LLMProfiles
