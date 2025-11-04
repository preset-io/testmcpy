import React, { useState, useEffect } from 'react'
import {
  Server, Check, AlertCircle, RefreshCw, ChevronDown, ChevronRight,
  Edit2, Trash2, Plus, Save, X, Copy, Download, Upload, Key, Lock,
  Unlock, Globe, CheckCircle, XCircle, AlertTriangle, ArrowUp, ArrowDown,
  Settings
} from 'lucide-react'

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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-elevated border border-border rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
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

// Auth type icon helper
function getAuthIcon(authType) {
  switch (authType) {
    case 'bearer':
      return <Key size={14} className="text-primary" />
    case 'jwt':
      return <Lock size={14} className="text-warning" />
    case 'oauth':
      return <Globe size={14} className="text-info" />
    case 'none':
      return <Unlock size={14} className="text-text-disabled" />
    default:
      return <Key size={14} className="text-text-disabled" />
  }
}

// Profile editor modal
function ProfileEditorModal({ profile, onSave, onCancel }) {
  const [name, setName] = useState(profile?.name || '')
  const [description, setDescription] = useState(profile?.description || '')
  const [errors, setErrors] = useState({})

  const validate = () => {
    const newErrors = {}
    if (!name.trim()) newErrors.name = 'Name is required'
    if (name.length > 50) newErrors.name = 'Name must be less than 50 characters'
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validate()) {
      onSave({ name, description })
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-elevated border border-border rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
        <h3 className="text-lg font-bold mb-4">
          {profile ? 'Edit Profile' : 'New Profile'}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Profile Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input w-full"
                placeholder="e.g., Production, Development"
                autoFocus
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
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// MCP editor modal
function MCPEditorModal({ mcp, onSave, onCancel }) {
  const [formData, setFormData] = useState({
    name: mcp?.name || '',
    mcp_url: mcp?.mcp_url || '',
    auth_type: mcp?.auth?.type || 'none',
    token: mcp?.auth?.token || '',
    api_url: mcp?.auth?.api_url || '',
    api_token: mcp?.auth?.api_token || '',
    api_secret: mcp?.auth?.api_secret || '',
    client_id: mcp?.auth?.client_id || '',
    client_secret: mcp?.auth?.client_secret || '',
    token_url: mcp?.auth?.token_url || '',
    scopes: mcp?.auth?.scopes?.join(', ') || '',
    timeout: mcp?.timeout || 30,
    rate_limit_rpm: mcp?.rate_limit_rpm || 60,
  })
  const [errors, setErrors] = useState({})

  const validate = () => {
    const newErrors = {}
    if (!formData.name.trim()) newErrors.name = 'Name is required'
    if (!formData.mcp_url.trim()) newErrors.mcp_url = 'URL is required'

    // Validate URL format
    try {
      new URL(formData.mcp_url)
    } catch {
      newErrors.mcp_url = 'Invalid URL format'
    }

    // Validate auth fields based on type
    if (formData.auth_type === 'bearer' && !formData.token) {
      newErrors.token = 'Token is required for bearer auth'
    }
    if (formData.auth_type === 'jwt') {
      if (!formData.api_url) newErrors.api_url = 'API URL is required for JWT'
      if (!formData.api_token) newErrors.api_token = 'API Token is required for JWT'
      if (!formData.api_secret) newErrors.api_secret = 'API Secret is required for JWT'
    }
    if (formData.auth_type === 'oauth') {
      if (!formData.client_id) newErrors.client_id = 'Client ID is required for OAuth'
      if (!formData.client_secret) newErrors.client_secret = 'Client Secret is required for OAuth'
      if (!formData.token_url) newErrors.token_url = 'Token URL is required for OAuth'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validate()) {
      // Convert scopes string to array
      const scopesArray = formData.scopes ?
        formData.scopes.split(',').map(s => s.trim()).filter(s => s) : []

      onSave({
        ...formData,
        scopes: scopesArray.length > 0 ? scopesArray : null
      })
    }
  }

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    // Clear error for this field
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto p-4">
      <div className="bg-surface-elevated border border-border rounded-lg p-6 max-w-2xl w-full my-8 shadow-xl">
        <h3 className="text-lg font-bold mb-4">
          {mcp ? 'Edit MCP Server' : 'Add MCP Server'}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            {/* Basic Info */}
            <div>
              <label className="block text-sm font-medium mb-1">Server Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => updateField('name', e.target.value)}
                className="input w-full"
                placeholder="e.g., Superset MCP"
                autoFocus
              />
              {errors.name && <p className="text-error text-xs mt-1">{errors.name}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">MCP URL</label>
              <input
                type="text"
                value={formData.mcp_url}
                onChange={(e) => updateField('mcp_url', e.target.value)}
                className="input w-full font-mono text-sm"
                placeholder="https://api.example.com/mcp/"
              />
              {errors.mcp_url && <p className="text-error text-xs mt-1">{errors.mcp_url}</p>}
            </div>

            {/* Auth Type */}
            <div>
              <label className="block text-sm font-medium mb-1">Authentication Type</label>
              <select
                value={formData.auth_type}
                onChange={(e) => updateField('auth_type', e.target.value)}
                className="input w-full"
              >
                <option value="none">None</option>
                <option value="bearer">Bearer Token</option>
                <option value="jwt">JWT</option>
                <option value="oauth">OAuth 2.0</option>
              </select>
            </div>

            {/* Auth Fields - Bearer */}
            {formData.auth_type === 'bearer' && (
              <div>
                <label className="block text-sm font-medium mb-1">Bearer Token</label>
                <input
                  type="password"
                  value={formData.token}
                  onChange={(e) => updateField('token', e.target.value)}
                  className="input w-full font-mono text-sm"
                  placeholder="Enter token or ${ENV_VAR_NAME}"
                />
                {errors.token && <p className="text-error text-xs mt-1">{errors.token}</p>}
                <p className="text-text-tertiary text-xs mt-1">
                  Tip: Use ${'{'}VAR_NAME{'}'} to reference environment variables
                </p>
              </div>
            )}

            {/* Auth Fields - JWT */}
            {formData.auth_type === 'jwt' && (
              <>
                <div>
                  <label className="block text-sm font-medium mb-1">API URL</label>
                  <input
                    type="text"
                    value={formData.api_url}
                    onChange={(e) => updateField('api_url', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="https://api.example.com/v1/auth/"
                  />
                  {errors.api_url && <p className="text-error text-xs mt-1">{errors.api_url}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">API Token</label>
                  <input
                    type="password"
                    value={formData.api_token}
                    onChange={(e) => updateField('api_token', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="Enter token or ${ENV_VAR_NAME}"
                  />
                  {errors.api_token && <p className="text-error text-xs mt-1">{errors.api_token}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">API Secret</label>
                  <input
                    type="password"
                    value={formData.api_secret}
                    onChange={(e) => updateField('api_secret', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="Enter secret or ${ENV_VAR_NAME}"
                  />
                  {errors.api_secret && <p className="text-error text-xs mt-1">{errors.api_secret}</p>}
                </div>
              </>
            )}

            {/* Auth Fields - OAuth */}
            {formData.auth_type === 'oauth' && (
              <>
                <div>
                  <label className="block text-sm font-medium mb-1">Client ID</label>
                  <input
                    type="text"
                    value={formData.client_id}
                    onChange={(e) => updateField('client_id', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="Enter client ID or ${ENV_VAR_NAME}"
                  />
                  {errors.client_id && <p className="text-error text-xs mt-1">{errors.client_id}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Client Secret</label>
                  <input
                    type="password"
                    value={formData.client_secret}
                    onChange={(e) => updateField('client_secret', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="Enter secret or ${ENV_VAR_NAME}"
                  />
                  {errors.client_secret && <p className="text-error text-xs mt-1">{errors.client_secret}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Token URL</label>
                  <input
                    type="text"
                    value={formData.token_url}
                    onChange={(e) => updateField('token_url', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="https://api.example.com/oauth/token"
                  />
                  {errors.token_url && <p className="text-error text-xs mt-1">{errors.token_url}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Scopes (comma-separated)</label>
                  <input
                    type="text"
                    value={formData.scopes}
                    onChange={(e) => updateField('scopes', e.target.value)}
                    className="input w-full font-mono text-sm"
                    placeholder="read, write, admin"
                  />
                </div>
              </>
            )}

            {/* Advanced Settings */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Timeout (seconds)</label>
                <input
                  type="number"
                  value={formData.timeout}
                  onChange={(e) => updateField('timeout', parseInt(e.target.value))}
                  className="input w-full"
                  min="1"
                  max="300"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Rate Limit (req/min)</label>
                <input
                  type="number"
                  value={formData.rate_limit_rpm}
                  onChange={(e) => updateField('rate_limit_rpm', parseInt(e.target.value))}
                  className="input w-full"
                  min="1"
                  max="1000"
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-border">
            <button type="button" onClick={onCancel} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              <Save size={16} />
              Save MCP
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function MCPProfiles({ selectedProfiles = [], onSelectProfiles, hideHeader = false }) {
  const [profiles, setProfiles] = useState([])
  const [defaultProfile, setDefaultProfile] = useState(null)
  const [selectedServers, setSelectedServers] = useState(new Set(selectedProfiles))
  const [expandedProfiles, setExpandedProfiles] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [profileEditor, setProfileEditor] = useState(null)
  const [mcpEditor, setMCPEditor] = useState(null)
  const [testingConnection, setTestingConnection] = useState(null)

  useEffect(() => {
    loadProfiles()
  }, [])

  useEffect(() => {
    setSelectedServers(new Set(selectedProfiles))
  }, [selectedProfiles])

  useEffect(() => {
    // Auto-expand all profiles when they're loaded
    if (profiles.length > 0) {
      const allProfileIds = profiles.map(p => p.id)
      setExpandedProfiles(new Set(allProfileIds))
    }
  }, [profiles])

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

  const loadProfiles = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchWithRetry('/api/mcp/profiles')
      const data = await res.json()

      if (data.error) {
        setError(data.error)
      } else if (data.message) {
        setError(data.message)
      } else {
        setProfiles(data.profiles || [])
        setDefaultProfile(data.default)
      }
    } catch (error) {
      console.error('Failed to load MCP profiles:', error)
      setError('Failed to load MCP profiles. Make sure .mcp_services.yaml exists.')
    } finally {
      setLoading(false)
    }
  }

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
  }

  const toggleServer = (profileId, mcpName) => {
    const serverId = `${profileId}:${mcpName}`
    const newSelected = new Set(selectedServers)
    if (newSelected.has(serverId)) {
      newSelected.delete(serverId)
    } else {
      newSelected.add(serverId)
    }
    setSelectedServers(newSelected)
    if (onSelectProfiles) {
      onSelectProfiles(Array.from(newSelected))
    }
  }

  const isServerSelected = (profileId, mcpName) => {
    const serverId = `${profileId}:${mcpName}`
    return selectedServers.has(serverId)
  }

  const getProfileSelectionCount = (profile) => {
    if (!profile.mcps) return 0
    return profile.mcps.filter(mcp => isServerSelected(profile.id, mcp.name)).length
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

  const createConfiguration = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/mcp/profiles/create-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        showToast('Configuration file created successfully')
      } else {
        setError(data.error || 'Failed to create configuration')
      }
    } catch (error) {
      console.error('Failed to create configuration:', error)
      setError('Failed to create configuration file')
    } finally {
      setLoading(false)
    }
  }

  // Profile operations
  const handleCreateProfile = async (profileData) => {
    try {
      const res = await fetch('/api/mcp/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileData)
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setProfileEditor(null)
        showToast('Profile created successfully')
      } else {
        showToast('Failed to create profile', 'error')
      }
    } catch (error) {
      console.error('Failed to create profile:', error)
      showToast('Failed to create profile', 'error')
    }
  }

  const handleUpdateProfile = async (profileId, profileData) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileData)
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setProfileEditor(null)
        showToast('Profile updated successfully')
      } else {
        showToast('Failed to update profile', 'error')
      }
    } catch (error) {
      console.error('Failed to update profile:', error)
      showToast('Failed to update profile', 'error')
    }
  }

  const handleDeleteProfile = async (profileId) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}`, {
        method: 'DELETE'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setConfirmDialog(null)
        showToast('Profile deleted successfully')
      } else {
        showToast('Failed to delete profile', 'error')
      }
    } catch (error) {
      console.error('Failed to delete profile:', error)
      showToast('Failed to delete profile', 'error')
    }
  }

  const handleDuplicateProfile = async (profileId) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/duplicate`, {
        method: 'POST'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        showToast('Profile duplicated successfully')
      } else {
        showToast('Failed to duplicate profile', 'error')
      }
    } catch (error) {
      console.error('Failed to duplicate profile:', error)
      showToast('Failed to duplicate profile', 'error')
    }
  }

  const handleSetDefault = async (profileId) => {
    try {
      const res = await fetch(`/api/mcp/profiles/default/${profileId}`, {
        method: 'PUT'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        showToast('Default profile updated')
      } else {
        showToast('Failed to set default profile', 'error')
      }
    } catch (error) {
      console.error('Failed to set default:', error)
      showToast('Failed to set default profile', 'error')
    }
  }

  const handleExportProfile = async (profileId) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/export`)
      const data = await res.json()

      if (data.success) {
        // Create download link
        const blob = new Blob([data.yaml], { type: 'text/yaml' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = data.filename
        a.click()
        URL.revokeObjectURL(url)
        showToast('Profile exported successfully')
      } else {
        showToast('Failed to export profile', 'error')
      }
    } catch (error) {
      console.error('Failed to export profile:', error)
      showToast('Failed to export profile', 'error')
    }
  }

  // MCP operations
  const handleAddMCP = async (profileId, mcpData) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/mcps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mcpData)
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setMCPEditor(null)
        showToast('MCP added successfully')
      } else {
        showToast('Failed to add MCP', 'error')
      }
    } catch (error) {
      console.error('Failed to add MCP:', error)
      showToast('Failed to add MCP', 'error')
    }
  }

  const handleUpdateMCP = async (profileId, mcpIndex, mcpData) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/mcps/${mcpIndex}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mcpData)
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setMCPEditor(null)
        showToast('MCP updated successfully')
      } else {
        showToast('Failed to update MCP', 'error')
      }
    } catch (error) {
      console.error('Failed to update MCP:', error)
      showToast('Failed to update MCP', 'error')
    }
  }

  const handleDeleteMCP = async (profileId, mcpIndex) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/mcps/${mcpIndex}`, {
        method: 'DELETE'
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        setConfirmDialog(null)
        showToast('MCP deleted successfully')
      } else {
        showToast('Failed to delete MCP', 'error')
      }
    } catch (error) {
      console.error('Failed to delete MCP:', error)
      showToast('Failed to delete MCP', 'error')
    }
  }

  const handleReorderMCP = async (profileId, fromIndex, toIndex) => {
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/mcps/reorder`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_index: fromIndex, to_index: toIndex })
      })
      const data = await res.json()

      if (data.success) {
        await loadProfiles()
        showToast('MCP reordered successfully')
      } else {
        showToast('Failed to reorder MCP', 'error')
      }
    } catch (error) {
      console.error('Failed to reorder MCP:', error)
      showToast('Failed to reorder MCP', 'error')
    }
  }

  const handleTestConnection = async (profileId, mcpIndex) => {
    setTestingConnection(`${profileId}-${mcpIndex}`)
    try {
      const res = await fetch(`/api/mcp/profiles/${profileId}/test-connection/${mcpIndex}`, {
        method: 'POST'
      })
      const data = await res.json()

      if (data.success) {
        showToast(`Connected! Found ${data.tool_count} tools`, 'success')
      } else {
        showToast(data.message || 'Connection failed', 'error')
      }
    } catch (error) {
      console.error('Failed to test connection:', error)
      showToast('Connection test failed', 'error')
    } finally {
      setTestingConnection(null)
    }
  }

  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text)
    showToast(`${label} copied to clipboard`)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-text-secondary">Loading MCP profiles...</div>
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
              <h1 className="text-2xl font-bold">MCP Profiles</h1>
              <p className="text-text-secondary mt-1 text-base">
                Manage and configure MCP service profiles
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
              {profiles.length > 0 && (
                <button
                  onClick={() => setProfileEditor({ isNew: true })}
                  className="btn btn-primary flex items-center gap-2"
                >
                  <Plus size={16} />
                  Add Profile
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {error ? (
          <div className="max-w-2xl mx-auto">
            <div className="bg-surface-elevated border border-warning rounded-lg p-4 flex items-start gap-3">
              <AlertCircle size={20} className="text-warning mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="font-medium text-warning mb-1">Configuration Not Found</h3>
                <p className="text-text-secondary text-sm mb-3">{error}</p>
                <p className="text-text-secondary text-sm mb-4">
                  Create a <code className="font-mono bg-surface px-1 rounded">.mcp_services.yaml</code> file to define MCP profiles. See{' '}
                  <a
                    href="https://github.com/aminghadersohi/testmcpy/blob/main/docs/MCP_PROFILES.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    documentation
                  </a> for examples.
                </p>
                <button
                  onClick={createConfiguration}
                  className="btn btn-primary"
                >
                  Create Configuration File
                </button>
              </div>
            </div>
          </div>
        ) : profiles.length === 0 ? (
          <div className="max-w-2xl mx-auto text-center py-12">
            <Server size={48} className="text-text-disabled mx-auto mb-4" />
            <h2 className="text-xl font-medium mb-2">No MCP Profiles Found</h2>
            <p className="text-text-secondary mb-4">
              Create a .mcp_services.yaml file to configure multiple MCP services
            </p>
            <a
              href="https://github.com/aminghadersohi/testmcpy/blob/main/docs/MCP_PROFILES.md"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary inline-block"
            >
              View Documentation
            </a>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            <div className="mb-4 text-sm text-text-secondary">
              Click on individual MCP servers to select them. Selected services will be available across the app.
              {selectedServers.size > 0 && (
                <span className="ml-2 text-primary font-medium">
                  {selectedServers.size} server{selectedServers.size !== 1 ? 's' : ''} selected
                </span>
              )}
            </div>

            <div className="grid gap-3">
              {profiles.map((profile) => {
                const isDefault = profile.id === defaultProfile
                const isExpanded = expandedProfiles.has(profile.id)
                const mcps = profile.mcps || []
                const hasMCPs = mcps.length > 0
                const selectionCount = getProfileSelectionCount(profile)

                return (
                  <div
                    key={profile.id}
                    className="border rounded-lg p-4 transition-all border-border bg-surface-elevated"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3 flex-1">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-medium">{profile.name}</h3>
                            {isDefault && (
                              <span className="px-2 py-0.5 text-xs rounded-full bg-primary/20 text-primary">
                                Default
                              </span>
                            )}
                            {hasMCPs && (
                              <span className="px-2 py-0.5 text-xs rounded-full bg-surface border border-border text-text-secondary">
                                {mcps.length} MCP{mcps.length !== 1 ? 's' : ''}
                              </span>
                            )}
                            {selectionCount > 0 && (
                              <span className="px-2 py-0.5 text-xs rounded-full bg-primary/20 text-primary font-medium">
                                {selectionCount} selected
                              </span>
                            )}
                          </div>

                          {profile.description && (
                            <p className="text-sm text-text-secondary mb-2">
                              {profile.description}
                            </p>
                          )}

                          {hasMCPs && !isExpanded && (
                            <div className="text-xs text-text-tertiary">
                              {mcps.slice(0, 2).map((mcp, idx) => mcp.name).join(', ')}
                              {mcps.length > 2 && ` + ${mcps.length - 2} more`}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        {/* Profile Actions */}
                        <button
                          onClick={() => setProfileEditor({ profile, profileId: profile.id })}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Edit profile"
                        >
                          <Edit2 size={16} className="text-text-secondary" />
                        </button>

                        <button
                          onClick={() => handleDuplicateProfile(profile.id)}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Duplicate profile"
                        >
                          <Copy size={16} className="text-text-secondary" />
                        </button>

                        <button
                          onClick={() => handleExportProfile(profile.id)}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Export profile"
                        >
                          <Download size={16} className="text-text-secondary" />
                        </button>

                        {!isDefault && (
                          <button
                            onClick={() => handleSetDefault(profile.id)}
                            className="p-2 hover:bg-surface-hover rounded transition-colors"
                            title="Set as default"
                          >
                            <Settings size={16} className="text-text-secondary" />
                          </button>
                        )}

                        <button
                          onClick={() => setConfirmDialog({
                            title: 'Delete Profile',
                            message: `Are you sure you want to delete "${profile.name}"? This action cannot be undone.`,
                            onConfirm: () => handleDeleteProfile(profile.id)
                          })}
                          className="p-2 hover:bg-surface-hover rounded transition-colors"
                          title="Delete profile"
                        >
                          <Trash2 size={16} className="text-error" />
                        </button>

                        {hasMCPs && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleExpanded(profile.id)
                            }}
                            className="p-2 hover:bg-surface-hover rounded transition-colors ml-1"
                            title={isExpanded ? "Hide MCPs" : "Show MCPs"}
                          >
                            {isExpanded ? (
                              <ChevronDown size={18} className="text-text-secondary" />
                            ) : (
                              <ChevronRight size={18} className="text-text-secondary" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expanded MCP Details */}
                    {isExpanded && (
                      <div className="mt-4 space-y-2">
                        {mcps.map((mcp, idx) => {
                          const isTesting = testingConnection === `${profile.id}-${idx}`
                          const isSelected = isServerSelected(profile.id, mcp.name)

                          return (
                            <div
                              key={idx}
                              className={`rounded-lg p-3 space-y-2 transition-all cursor-pointer ${
                                isSelected
                                  ? 'bg-primary/10 border-2 border-primary'
                                  : 'bg-surface border-2 border-transparent hover:border-primary/30'
                              }`}
                              onClick={() => toggleServer(profile.id, mcp.name)}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex items-center gap-2 flex-1">
                                  {isSelected && <Check size={14} className="text-primary flex-shrink-0" />}
                                  <Server size={14} className="text-primary flex-shrink-0" />
                                  <span className="font-medium text-sm">{mcp.name}</span>
                                  {getAuthIcon(mcp.auth?.type || 'none')}
                                </div>

                                {/* MCP Actions */}
                                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                                  <button
                                    onClick={() => handleTestConnection(profile.id, idx)}
                                    disabled={isTesting}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors disabled:opacity-50"
                                    title="Test connection"
                                  >
                                    {isTesting ? (
                                      <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                                    ) : (
                                      <CheckCircle size={14} className="text-success" />
                                    )}
                                  </button>

                                  {idx > 0 && (
                                    <button
                                      onClick={() => handleReorderMCP(profile.id, idx, idx - 1)}
                                      className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                      title="Move up"
                                    >
                                      <ArrowUp size={14} className="text-text-secondary" />
                                    </button>
                                  )}

                                  {idx < mcps.length - 1 && (
                                    <button
                                      onClick={() => handleReorderMCP(profile.id, idx, idx + 1)}
                                      className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                      title="Move down"
                                    >
                                      <ArrowDown size={14} className="text-text-secondary" />
                                    </button>
                                  )}

                                  <button
                                    onClick={() => setMCPEditor({ mcp, profileId: profile.id, mcpIndex: idx })}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                    title="Edit MCP"
                                  >
                                    <Edit2 size={14} className="text-text-secondary" />
                                  </button>

                                  <button
                                    onClick={() => copyToClipboard(mcp.mcp_url, 'MCP URL')}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                    title="Copy URL"
                                  >
                                    <Copy size={14} className="text-text-secondary" />
                                  </button>

                                  <button
                                    onClick={() => setConfirmDialog({
                                      title: 'Delete MCP',
                                      message: `Are you sure you want to delete "${mcp.name}"? This action cannot be undone.`,
                                      onConfirm: () => handleDeleteMCP(profile.id, idx)
                                    })}
                                    className="p-1 hover:bg-surface-elevated rounded transition-colors"
                                    title="Delete MCP"
                                  >
                                    <Trash2 size={14} className="text-error" />
                                  </button>
                                </div>
                              </div>

                              <div className="space-y-1.5 text-xs">
                                <div className="flex items-start gap-2">
                                  <span className="text-text-disabled min-w-[50px]">URL:</span>
                                  <code className="font-mono bg-surface-elevated px-2 py-0.5 rounded flex-1 break-all">
                                    {mcp.mcp_url}
                                  </code>
                                </div>

                                {mcp.auth && mcp.auth.type && mcp.auth.type !== 'none' && (
                                  <div className="flex items-start gap-2">
                                    <span className="text-text-disabled min-w-[50px]">Auth:</span>
                                    <div className="flex items-center gap-2 flex-1">
                                      <span className="px-1.5 py-0.5 bg-surface-elevated rounded">
                                        {mcp.auth.type}
                                      </span>
                                      {mcp.auth.token && (
                                        <code className="font-mono bg-surface-elevated px-2 py-0.5 rounded text-text-tertiary">
                                          {mcp.auth.token.startsWith('${') ? mcp.auth.token : '***'}
                                        </code>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {(mcp.timeout || mcp.rate_limit_rpm) && (
                                  <div className="flex items-center gap-3 text-text-tertiary">
                                    {mcp.timeout && (
                                      <span>Timeout: {mcp.timeout}s</span>
                                    )}
                                    {mcp.rate_limit_rpm && (
                                      <span>Rate: {mcp.rate_limit_rpm} req/min</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          )
                        })}

                        {/* Add MCP Button */}
                        <button
                          onClick={() => setMCPEditor({ profileId: profile.id, isNew: true })}
                          className="w-full p-3 border-2 border-dashed border-border rounded-lg hover:border-primary hover:bg-primary/5 transition-all flex items-center justify-center gap-2 text-text-secondary hover:text-primary"
                        >
                          <Plus size={16} />
                          Add MCP Server
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

      {mcpEditor && (
        <MCPEditorModal
          mcp={mcpEditor.mcp}
          onSave={(data) => {
            if (mcpEditor.isNew) {
              handleAddMCP(mcpEditor.profileId, data)
            } else {
              handleUpdateMCP(mcpEditor.profileId, mcpEditor.mcpIndex, data)
            }
          }}
          onCancel={() => setMCPEditor(null)}
        />
      )}
    </div>
  )
}

export default MCPProfiles
