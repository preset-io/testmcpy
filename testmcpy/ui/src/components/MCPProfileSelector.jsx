import React, { useState, useEffect } from 'react'
import { Server, ChevronDown, CheckCircle2, ChevronRight } from 'lucide-react'

const MCPProfileSelector = ({ selectedProfiles = [], onChange, multiple = false }) => {
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const [expandedProfiles, setExpandedProfiles] = useState(new Set())

  useEffect(() => {
    loadProfiles()
  }, [])

  const loadProfiles = async () => {
    try {
      const res = await fetch('/api/mcp/profiles')
      const data = await res.json()
      setProfiles(data.profiles || [])
    } catch (error) {
      console.error('Failed to load profiles:', error)
    } finally {
      setLoading(false)
    }
  }

  const toggleProfileExpansion = (profileId, e) => {
    e.stopPropagation()
    e.preventDefault()

    setExpandedProfiles(prev => {
      const newExpanded = new Set(prev)
      if (newExpanded.has(profileId)) {
        newExpanded.delete(profileId)
      } else {
        newExpanded.add(profileId)
      }
      return newExpanded
    })
  }

  const handleToggleServer = (profileId, mcpName) => {
    const serverId = `${profileId}:${mcpName}`
    if (multiple) {
      // Multi-select mode
      const newSelection = selectedProfiles.includes(serverId)
        ? selectedProfiles.filter(id => id !== serverId)
        : [...selectedProfiles, serverId]
      onChange(newSelection)
    } else {
      // Single-select mode
      onChange(selectedProfiles.includes(serverId) ? [] : [serverId])
      setIsOpen(false)
    }
  }

  const getSelectedServerNames = () => {
    if (selectedProfiles.length === 0) return 'Default MCP'

    const names = []
    selectedProfiles.forEach(serverId => {
      const [profileId, mcpName] = serverId.split(':')
      const profile = profiles.find(p => p.profile_id === profileId)
      if (profile) {
        const mcp = profile.mcps.find(m => m.name === mcpName)
        if (mcp) {
          names.push(mcp.name)
        }
      }
    })

    return names.length > 0 ? names.join(', ') : 'Default MCP'
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-surface-elevated border border-border rounded-lg">
        <Server size={16} className="text-text-secondary" />
        <span className="text-sm text-text-secondary">Loading profiles...</span>
      </div>
    )
  }

  if (profiles.length === 0) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-surface-elevated border border-border rounded-lg">
        <Server size={16} className="text-text-secondary" />
        <span className="text-sm text-text-secondary">No profiles configured</span>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-surface-elevated border border-border rounded-lg hover:bg-surface-hover transition-colors w-full text-left"
      >
        <Server size={16} className="text-primary flex-shrink-0" />
        <span className="text-sm font-medium text-text-primary flex-1 truncate">
          {getSelectedServerNames()}
        </span>
        <ChevronDown size={16} className={`text-text-secondary transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full left-0 right-0 mt-1 bg-surface-elevated border border-border rounded-lg shadow-lg z-20 max-h-80 overflow-y-auto">
            <div className="p-2">
              {profiles.map((profile) => {
                const isExpanded = expandedProfiles.has(profile.profile_id)
                return (
                  <div key={profile.profile_id} className="mb-1">
                    {/* Profile Header */}
                    <button
                      onClick={(e) => toggleProfileExpansion(profile.profile_id, e)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-hover text-left transition-colors"
                    >
                      <ChevronRight
                        size={14}
                        className={`text-text-tertiary transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm text-text-primary truncate">{profile.name}</div>
                        <div className="text-xs text-text-tertiary">
                          {profile.mcps.length} server{profile.mcps.length !== 1 ? 's' : ''}
                        </div>
                      </div>
                    </button>

                    {/* MCP Servers List */}
                    {isExpanded && (
                      <div className="ml-6 mt-1 space-y-1">
                        {profile.mcps.map((mcp) => {
                          const serverId = `${profile.profile_id}:${mcp.name}`
                          const isSelected = selectedProfiles.includes(serverId)
                          return (
                            <button
                              key={mcp.name}
                              onClick={() => handleToggleServer(profile.profile_id, mcp.name)}
                              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left ${
                                isSelected
                                  ? 'bg-primary/20 text-primary border border-primary/30'
                                  : 'hover:bg-surface-hover text-text-primary'
                              }`}
                            >
                              {isSelected && <CheckCircle2 size={14} className="flex-shrink-0" />}
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-sm truncate">{mcp.name}</div>
                                <div className="text-xs text-text-tertiary truncate">{mcp.mcp_url}</div>
                              </div>
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default MCPProfileSelector
