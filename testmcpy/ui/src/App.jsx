import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  Package,
  MessageSquare,
  FileText,
  Settings,
  Menu,
  X,
  Server,
  Cpu,
  CheckCircle2,
  ChevronRight,
  Shield,
  History,
  BarChart3
} from 'lucide-react'

import MCPExplorer from './pages/MCPExplorer'
import ChatInterface from './pages/ChatInterface'
import TestManager from './pages/TestManager'
import Configuration from './pages/Configuration'
import MCPProfiles from './pages/MCPProfiles'
import LLMProfiles from './pages/LLMProfiles'
import AuthDebugger from './pages/AuthDebugger'
import GenerationHistory from './pages/GenerationHistory'
import Reports from './pages/Reports'
import { TestRunProvider } from './contexts/TestRunContext'

function AppContent() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [config, setConfig] = useState({})
  const [selectedProfiles, setSelectedProfiles] = useState([])
  const [profiles, setProfiles] = useState([])
  const [llmProfiles, setLlmProfiles] = useState([])
  const [selectedLlmProfile, setSelectedLlmProfile] = useState(null)
  const [apiReady, setApiReady] = useState(false)
  const [healthCheckAttempts, setHealthCheckAttempts] = useState(0)
  const [appVersion, setAppVersion] = useState('v0.0.0')
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    checkApiHealth()
  }, [])

  useEffect(() => {
    if (apiReady) {
      loadConfig()
      loadProfiles()
      loadLlmProfiles()
      loadVersion()
    }
  }, [apiReady])

  const checkApiHealth = async () => {
    const maxAttempts = 5
    const delay = 1000

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        setHealthCheckAttempts(attempt + 1)
        const res = await fetch('/api/health', {
          method: 'GET',
          cache: 'no-cache'
        })

        if (res.ok) {
          const data = await res.json()
          console.log('API health check passed:', data)
          setApiReady(true)
          return
        }
      } catch (error) {
        console.log(`Health check attempt ${attempt + 1}/${maxAttempts} failed:`, error.message)
      }

      if (attempt < maxAttempts - 1) {
        const waitTime = delay * Math.pow(2, attempt)
        console.log(`Waiting ${waitTime}ms before retry...`)
        await new Promise(resolve => setTimeout(resolve, waitTime))
      }
    }

    console.error('API health check failed after all attempts')
    setApiReady(true)
  }

  const loadVersion = async () => {
    try {
      const res = await fetch('/api/version')
      const data = await res.json()
      setAppVersion(`v${data.version}`)
    } catch (error) {
      console.error('Failed to load version:', error)
    }
  }

  const loadConfig = async () => {
    try {
      const res = await fetch('/api/config')
      const data = await res.json()
      setConfig(data)
    } catch (error) {
      console.error('Failed to load config:', error)
    }
  }

  const loadProfiles = async () => {
    try {
      const res = await fetch('/api/mcp/profiles')
      const data = await res.json()
      console.log('Loaded profiles from API:', data.profiles)
      console.log('Default selection from API:', data.default_selection)
      setProfiles(data.profiles || [])

      // Check localStorage for saved selection
      const savedProfiles = localStorage.getItem('selectedMCPProfiles')
      console.log('Saved profiles in localStorage:', savedProfiles)

      if (savedProfiles) {
        // Use saved selection
        try {
          const parsed = JSON.parse(savedProfiles)
          console.log('Using saved selection:', parsed)
          setSelectedProfiles(parsed)
        } catch (e) {
          console.error('Failed to parse saved profiles:', e)
          // If parsing fails and there's a default, use it
          if (data.default_selection) {
            console.log('Parse failed, using default:', data.default_selection)
            const defaultSelection = [data.default_selection]
            setSelectedProfiles(defaultSelection)
            localStorage.setItem('selectedMCPProfiles', JSON.stringify(defaultSelection))
          }
        }
      } else if (data.default_selection) {
        // No saved selection, use default from API
        console.log('No saved selection, using default:', data.default_selection)
        const defaultSelection = [data.default_selection]
        setSelectedProfiles(defaultSelection)
        localStorage.setItem('selectedMCPProfiles', JSON.stringify(defaultSelection))
      }
    } catch (error) {
      console.error('Failed to load profiles:', error)
    }
  }

  // Helper to get provider key from profile
  const getProviderKeyFromProfile = (profile) => {
    if (!profile?.providers?.length) return null
    const defaultProv = profile.providers.find(p => p.default) || profile.providers[0]
    return `${defaultProv.provider}:${defaultProv.model}`
  }

  const loadLlmProfiles = async () => {
    try {
      const res = await fetch('/api/llm/profiles')
      const data = await res.json()
      console.log('Loaded LLM profiles:', data.profiles)
      setLlmProfiles(data.profiles || [])

      // Check localStorage for saved LLM profile selection
      const savedLlmProfile = localStorage.getItem('selectedLLMProfile')

      let profileToUse = null
      if (savedLlmProfile && data.profiles?.find(p => p.profile_id === savedLlmProfile)) {
        setSelectedLlmProfile(savedLlmProfile)
        profileToUse = data.profiles.find(p => p.profile_id === savedLlmProfile)
      } else if (data.default && data.profiles?.find(p => p.profile_id === data.default)) {
        // Use default from API
        setSelectedLlmProfile(data.default)
        localStorage.setItem('selectedLLMProfile', data.default)
        profileToUse = data.profiles.find(p => p.profile_id === data.default)
      }

      // Always sync the provider to match the profile's default provider
      // This ensures consistency between sidebar and modals
      if (profileToUse) {
        const providerKey = getProviderKeyFromProfile(profileToUse)
        if (providerKey) {
          localStorage.setItem('selectedLLMProvider', providerKey)
        }
      }
    } catch (error) {
      console.error('Failed to load LLM profiles:', error)
    }
  }

  // When profile changes, update the provider too
  const handleLlmProfileChange = (profileId) => {
    setSelectedLlmProfile(profileId)
    localStorage.setItem('selectedLLMProfile', profileId)

    const profile = llmProfiles.find(p => p.profile_id === profileId)
    const providerKey = getProviderKeyFromProfile(profile)
    if (providerKey) {
      localStorage.setItem('selectedLLMProvider', providerKey)
    }
  }

  const getSelectedLLMDisplay = () => {
    if (!selectedLlmProfile) {
      return { providerName: 'No LLM Selected', profileName: 'Click to configure', isCliTool: false }
    }

    const profile = llmProfiles.find(p => p.profile_id === selectedLlmProfile)
    if (!profile) {
      return { providerName: 'Loading...', profileName: '', isCliTool: false }
    }

    const defaultProvider = profile.providers?.find(p => p.default) || profile.providers?.[0]
    const providerType = defaultProvider?.provider || ''
    const isCliTool = ['claude-cli', 'codex-cli', 'claude-code', 'codex'].includes(providerType)
    const isSdk = providerType === 'claude-sdk'
    const isApi = ['anthropic', 'openai', 'gemini', 'google'].includes(providerType)

    return {
      providerName: defaultProvider?.name || defaultProvider?.model || 'No provider',
      profileName: profile.name,
      isCliTool,
      isSdk,
      isApi,
      providerType
    }
  }

  const getSelectedMCPDisplay = () => {
    if (selectedProfiles.length === 0) {
      return { profile: 'No MCP Selected', server: 'Click to configure' }
    }

    // If profiles haven't loaded yet, show loading state
    if (profiles.length === 0) {
      return { profile: 'Loading...', server: 'Please wait' }
    }

    if (selectedProfiles.length === 1) {
      const [profileId, mcpName] = selectedProfiles[0].split(':')
      console.log('Looking for profile:', profileId, 'server:', mcpName)
      console.log('Available profiles:', profiles.map(p => ({ id: p.id, name: p.name })))

      const profile = profiles.find(p => p.id === profileId)
      if (profile) {
        const mcp = profile.mcps.find(m => m.name === mcpName)
        if (mcp) {
          return { profile: profile.name, server: mcp.name }
        }
      }
      // Fallback if profile/server not found - clear invalid selection
      console.warn('Invalid profile selection, clearing:', selectedProfiles[0])
      localStorage.removeItem('selectedMCPProfiles')
      setSelectedProfiles([])
      return { profile: 'No MCP Selected', server: 'Click to configure' }
    }

    return { profile: `${selectedProfiles.length} Servers`, server: 'Multiple selected' }
  }

  const getModel = () => {
    const provider = config.DEFAULT_PROVIDER?.value || 'unknown'
    const model = config.DEFAULT_MODEL?.value || 'not set'
    return { provider, model }
  }

  const navItems = [
    { path: '/', label: 'Explorer', icon: Package },
    { path: '/tests', label: 'Tests', icon: FileText },
    { path: '/reports', label: 'Reports', icon: BarChart3 },
    { path: '/generation-history', label: 'Gen History', icon: History },
    { path: '/chat', label: 'Interact', icon: MessageSquare },
    { path: '/auth-debugger', label: 'Auth Debug', icon: Shield },
    { path: '/config', label: 'Config', icon: Settings },
  ]

  if (!apiReady) {
    return (
      <div className="flex h-screen bg-background text-text-primary items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-center">
            <div className="text-lg font-semibold text-text-primary">Connecting to API</div>
            <div className="text-sm text-text-secondary mt-1">
              Attempt {healthCheckAttempts} of 5...
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background text-text-primary">
        {/* Sidebar */}
        <aside
          className={`${
            sidebarOpen ? 'w-50' : 'w-16'
          } bg-surface-elevated border-r border-border transition-all duration-300 flex flex-col shadow-medium`}
        >
          <div className="p-3 flex items-center justify-between border-b border-border">
            {sidebarOpen ? (
              <div className="flex items-center gap-2">
                <svg width="28" height="28" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
                  <rect x="5" y="9" width="5" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
                  <rect x="7" y="16" width="3" height="7" fill="currentColor" className="text-primary" opacity="0.3" />
                  <circle cx="9.5" cy="6" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                  <line x1="9.5" y1="6" x2="9.5" y2="9" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                  <circle cx="20" cy="14" r="6" fill="none" stroke="currentColor" strokeWidth="2" className="text-success" />
                  <path d="M 17 14 L 19 16 L 23 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-success" />
                </svg>
                <div>
                  <h1 className="text-lg font-bold text-primary leading-tight">testmcpy</h1>
                  <p className="text-[10px] text-text-tertiary leading-tight">MCP Testing</p>
                </div>
              </div>
            ) : (
              <svg width="24" height="24" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" className="mx-auto">
                <rect x="5" y="9" width="5" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
                <rect x="7" y="16" width="3" height="7" fill="currentColor" className="text-primary" opacity="0.3" />
                <circle cx="9.5" cy="6" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                <line x1="9.5" y1="6" x2="9.5" y2="9" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
              </svg>
            )}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 hover:bg-surface-hover rounded-lg transition-all duration-200 text-text-secondary hover:text-text-primary"
            >
              {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>

          <nav className="flex-1 px-3 py-4 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-200 ${
                      isActive
                        ? 'bg-primary text-white shadow-sm'
                        : 'hover:bg-surface-hover text-text-secondary hover:text-text-primary'
                    }`
                  }
                >
                  <Icon size={20} className="flex-shrink-0" />
                  {sidebarOpen && <span className="font-medium">{item.label}</span>}
                </NavLink>
              )
            })}
          </nav>

          {/* Profile Selectors */}
          <div className="px-3 py-3 border-t border-border space-y-2">
            {/* MCP Selector Widget with Connection Status */}
            <button
              onClick={() => navigate('/mcp-profiles')}
              className={`w-full rounded-lg transition-all duration-200 ${
                location.pathname === '/mcp-profiles'
                  ? 'bg-primary/10 border border-primary'
                  : selectedProfiles.length > 0
                    ? 'bg-success/10 border border-success/30 hover:bg-success/20'
                    : 'bg-surface-elevated border border-border hover:bg-surface-hover'
              }`}
            >
              <div className="flex items-center gap-2 px-3 py-2">
                <div className="relative flex-shrink-0">
                  <Server size={16} className={location.pathname === '/mcp-profiles' ? 'text-primary' : 'text-primary'} />
                  {selectedProfiles.length > 0 && (
                    <CheckCircle2 size={10} className="absolute -bottom-1 -right-1 text-success bg-surface-elevated rounded-full" />
                  )}
                </div>
                {sidebarOpen && (
                  <div className="flex-1 min-w-0 text-left">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-text-primary truncate">
                        {getSelectedMCPDisplay().profile}
                      </span>
                      {selectedProfiles.length > 0 && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-success/20 text-success font-medium">
                          Connected
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-text-tertiary truncate">
                      {getSelectedMCPDisplay().server}
                    </div>
                  </div>
                )}
                {sidebarOpen && <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />}
              </div>
            </button>

            {/* LLM Profile Selector Widget */}
            <button
              onClick={() => navigate('/llm-profiles')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-200 ${
                location.pathname === '/llm-profiles'
                  ? 'bg-primary/10 border border-primary text-primary'
                  : 'bg-surface-elevated border border-border hover:bg-surface-hover'
              }`}
            >
              <Cpu size={16} className={location.pathname === '/llm-profiles' ? 'text-primary' : 'text-success'} />
              {sidebarOpen && (
                <div className="flex-1 min-w-0 text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-text-primary truncate">
                      {getSelectedLLMDisplay().providerName}
                    </span>
                    {getSelectedLLMDisplay().isCliTool && (
                      <span className="px-1 py-0.5 text-[9px] bg-amber-500/20 text-amber-400 rounded flex-shrink-0">CLI</span>
                    )}
                    {getSelectedLLMDisplay().isSdk && (
                      <span className="px-1 py-0.5 text-[9px] bg-cyan-500/20 text-cyan-400 rounded flex-shrink-0">SDK</span>
                    )}
                    {getSelectedLLMDisplay().isApi && (
                      <span className="px-1 py-0.5 text-[9px] bg-emerald-500/20 text-emerald-400 rounded flex-shrink-0">API</span>
                    )}
                  </div>
                  <div className="text-[10px] text-text-tertiary truncate">
                    {getSelectedLLMDisplay().profileName}
                  </div>
                </div>
              )}
              {sidebarOpen && <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />}
            </button>
          </div>

          <div className="p-3 border-t border-border">
            {sidebarOpen && (
              <div className="text-xs text-text-tertiary space-y-0.5">
                <div className="font-medium">MCP Testing Framework</div>
                <div className="text-text-disabled">{appVersion}</div>
              </div>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<MCPExplorer selectedProfiles={selectedProfiles} />} />
            <Route path="/chat" element={<ChatInterface selectedProfiles={selectedProfiles} selectedLlmProfile={selectedLlmProfile} llmProfiles={llmProfiles} />} />
            <Route path="/tests" element={<TestManager selectedProfiles={selectedProfiles} />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/generation-history" element={<GenerationHistory />} />
            <Route path="/auth-debugger" element={<AuthDebugger />} />
            <Route path="/config" element={<Configuration />} />
            <Route path="/mcp-profiles" element={
              <MCPProfiles
                selectedProfiles={selectedProfiles}
                onSelectProfiles={(newProfiles) => {
                  setSelectedProfiles(newProfiles)
                  localStorage.setItem('selectedMCPProfiles', JSON.stringify(newProfiles))
                }}
              />
            } />
            <Route path="/llm-profiles" element={<LLMProfiles selectedProfile={selectedLlmProfile} onSelectProfile={handleLlmProfileChange} onProfilesChange={loadLlmProfiles} />} />
          </Routes>
        </main>

      </div>
  )
}

function App() {
  return (
    <Router>
      <TestRunProvider>
        <AppContent />
      </TestRunProvider>
    </Router>
  )
}

export default App
