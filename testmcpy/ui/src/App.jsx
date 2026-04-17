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
  BarChart3,
  Grid3X3,
  Sun,
  Moon,
  Monitor,
  GitCompare,
  Heart,
  TrendingUp,
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
import CompatibilityMatrix from './pages/CompatibilityMatrix'
import MetricsDashboard from './pages/MetricsDashboard'
import RunComparison from './pages/RunComparison'
import MCPHealth from './pages/MCPHealth'
import SecurityDashboard from './pages/SecurityDashboard'
import { TestRunProvider } from './contexts/TestRunContext'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import { NotificationProvider } from './components/NotificationProvider'
import CommandPalette from './components/CommandPalette'

function ThemeSwitcher({ collapsed }) {
  const { theme, setTheme } = useTheme()

  const options = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'dark', icon: Moon, label: 'Dark' },
    { value: 'system', icon: Monitor, label: 'System' },
  ]

  if (collapsed) {
    // Cycle through themes on click when collapsed
    const next = { light: 'dark', dark: 'system', system: 'light' }
    const CurrentIcon = options.find(o => o.value === theme)?.icon || Monitor
    return (
      <button
        onClick={() => setTheme(next[theme])}
        className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-surface-hover transition-all duration-200 text-text-secondary hover:text-text-primary"
        title={`Theme: ${theme}`}
      >
        <CurrentIcon size={16} />
      </button>
    )
  }

  return (
    <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-background-subtle border border-border">
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          className={`flex-1 flex items-center justify-center gap-1 px-1.5 py-1.5 rounded-md text-[11px] font-medium transition-all duration-200 ${
            theme === value
              ? 'bg-primary text-white shadow-sm'
              : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
          }`}
          title={label}
        >
          <Icon size={11} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  )
}

function AppContent() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
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

  // Close mobile drawer on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Close mobile drawer on resize to desktop
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const handler = () => {
      if (mq.matches) {
        setMobileMenuOpen(false)
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

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
    { path: '/compatibility', label: 'Compat', icon: Grid3X3 },
    { path: '/generation-history', label: 'Gen History', icon: History },
    { path: '/chat', label: 'Interact', icon: MessageSquare },
    { section: 'Analytics' },
    { path: '/metrics', label: 'Metrics', icon: TrendingUp },
    { path: '/compare', label: 'Compare', icon: GitCompare },
    { path: '/mcp-health', label: 'MCP Health', icon: Heart },
    { path: '/security', label: 'Security', icon: Shield },
    { section: 'Settings' },
    { path: '/auth-debugger', label: 'Auth Debug', icon: Shield },
    { path: '/config', label: 'Config', icon: Settings },
  ]

  // On mobile, sidebar always shows labels (acts as expanded drawer)
  const showLabels = sidebarOpen || mobileMenuOpen

  if (!apiReady) {
    return (
      <div className="flex h-screen bg-background text-text-primary items-center justify-center">
        <div className="flex flex-col items-center gap-5">
          <div className="relative">
            <div className="w-14 h-14 border-4 border-primary/30 rounded-full"></div>
            <div className="w-14 h-14 border-4 border-primary border-t-transparent rounded-full animate-spin absolute inset-0"></div>
          </div>
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
        {/* Command Palette (Cmd+K) */}
        <CommandPalette />

        {/* Mobile backdrop overlay */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 bg-black/40 z-30 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Sidebar — fixed drawer on mobile, static on desktop */}
        <aside
          className={`
            fixed inset-y-0 left-0 z-40 w-64
            md:relative md:z-auto
            ${sidebarOpen ? 'md:w-56' : 'md:w-16'}
            transform transition-all duration-300 ease-in-out
            ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
            md:translate-x-0
            sidebar-bg border-r border-border flex flex-col shadow-medium
          `}
        >
          {/* Header */}
          <div className={`border-b border-border ${showLabels ? 'p-3 flex items-center justify-between' : 'p-2 flex flex-col items-center gap-2'}`}>
            {showLabels ? (
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center flex-shrink-0">
                  <svg width="18" height="18" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
                    <rect x="5" y="9" width="5" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
                    <rect x="7" y="16" width="3" height="7" fill="currentColor" className="text-primary" opacity="0.3" />
                    <circle cx="9.5" cy="6" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                    <line x1="9.5" y1="6" x2="9.5" y2="9" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                    <circle cx="20" cy="14" r="6" fill="none" stroke="currentColor" strokeWidth="2" className="text-success" />
                    <path d="M 17 14 L 19 16 L 23 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-success" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-sm font-bold text-text-primary leading-tight tracking-tight">testmcpy</h1>
                  <p className="text-[10px] text-text-tertiary leading-tight">MCP Testing</p>
                </div>
              </div>
            ) : (
              <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
                  <rect x="5" y="9" width="5" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
                  <rect x="7" y="16" width="3" height="7" fill="currentColor" className="text-primary" opacity="0.3" />
                  <circle cx="9.5" cy="6" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                  <line x1="9.5" y1="6" x2="9.5" y2="9" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
                </svg>
              </div>
            )}
            {/* Desktop: collapse/expand toggle. Mobile: close drawer */}
            <button
              onClick={() => {
                // On mobile, close the drawer
                if (window.innerWidth < 768) {
                  setMobileMenuOpen(false)
                } else {
                  setSidebarOpen(!sidebarOpen)
                }
              }}
              className="p-1.5 hover:bg-surface-hover rounded-lg transition-all duration-200 text-text-tertiary hover:text-text-primary"
            >
              {showLabels ? <X size={16} /> : <Menu size={18} />}
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
            {navItems.map((item, idx) => {
              if (item.section) {
                return showLabels ? (
                  <div key={item.section} className="pt-3 pb-1 px-3">
                    <span className="text-[10px] font-semibold text-text-disabled uppercase tracking-wider">{item.section}</span>
                  </div>
                ) : (
                  <div key={item.section} className="pt-2 pb-1 px-3">
                    <div className="border-t border-border" />
                  </div>
                )
              }
              const Icon = item.icon
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-200 group ${
                      isActive
                        ? 'bg-primary text-white shadow-sm shadow-primary/25'
                        : 'hover:bg-surface-hover text-text-secondary hover:text-text-primary'
                    }`
                  }
                >
                  <Icon size={18} className="flex-shrink-0" />
                  {showLabels && <span className="text-sm font-medium">{item.label}</span>}
                </NavLink>
              )
            })}
          </nav>

          {/* Profile Selectors */}
          <div className="px-2 py-2 border-t border-border space-y-1.5">
            {/* MCP Selector Widget with Connection Status */}
            <button
              onClick={() => navigate('/mcp-profiles')}
              className={`w-full rounded-lg transition-all duration-200 ${
                location.pathname === '/mcp-profiles'
                  ? 'bg-primary/10 border border-primary/40 shadow-glow-primary'
                  : selectedProfiles.length > 0
                    ? 'bg-success/8 border border-success/20 hover:bg-success/15 hover:border-success/30'
                    : 'bg-surface border border-border hover:bg-surface-hover hover:border-border-subtle'
              }`}
            >
              <div className="flex items-center gap-2 px-2.5 py-2">
                <div className="relative flex-shrink-0">
                  <Server size={15} className="text-primary" />
                  {selectedProfiles.length > 0 && (
                    <CheckCircle2 size={9} className="absolute -bottom-1 -right-1 text-success" />
                  )}
                </div>
                {showLabels && (
                  <div className="flex-1 min-w-0 text-left">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-text-primary truncate">
                        {getSelectedMCPDisplay().profile}
                      </span>
                      {selectedProfiles.length > 0 && (
                        <span className="text-[8px] px-1 py-0.5 rounded-full bg-success/15 text-success font-semibold uppercase tracking-wider">
                          Live
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-text-tertiary truncate">
                      {getSelectedMCPDisplay().server}
                    </div>
                  </div>
                )}
                {showLabels && <ChevronRight size={13} className="text-text-tertiary flex-shrink-0" />}
              </div>
            </button>

            {/* LLM Profile Selector Widget */}
            <button
              onClick={() => navigate('/llm-profiles')}
              className={`w-full rounded-lg transition-all duration-200 ${
                location.pathname === '/llm-profiles'
                  ? 'bg-primary/10 border border-primary/40 shadow-glow-primary'
                  : 'bg-surface border border-border hover:bg-surface-hover hover:border-border-subtle'
              }`}
            >
              <div className="flex items-center gap-2 px-2.5 py-2">
                <Cpu size={15} className={location.pathname === '/llm-profiles' ? 'text-primary' : 'text-info-light'} />
                {showLabels && (
                  <div className="flex-1 min-w-0 text-left">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-text-primary truncate">
                        {getSelectedLLMDisplay().providerName}
                      </span>
                      {getSelectedLLMDisplay().isCliTool && (
                        <span className="px-1 py-0.5 text-[8px] bg-amber-500/15 text-amber-500 dark:text-amber-400 rounded font-semibold flex-shrink-0">CLI</span>
                      )}
                      {getSelectedLLMDisplay().isSdk && (
                        <span className="px-1 py-0.5 text-[8px] bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 rounded font-semibold flex-shrink-0">SDK</span>
                      )}
                      {getSelectedLLMDisplay().isApi && (
                        <span className="px-1 py-0.5 text-[8px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 rounded font-semibold flex-shrink-0">API</span>
                      )}
                    </div>
                    <div className="text-[10px] text-text-tertiary truncate">
                      {getSelectedLLMDisplay().profileName}
                    </div>
                  </div>
                )}
                {showLabels && <ChevronRight size={13} className="text-text-tertiary flex-shrink-0" />}
              </div>
            </button>
          </div>

          {/* Footer with theme switcher */}
          <div className="px-2 py-2.5 border-t border-border space-y-2">
            <ThemeSwitcher collapsed={!showLabels} />
            {showLabels && (
              <div className="text-[10px] text-text-tertiary flex items-center justify-between px-1">
                <span className="font-medium">testmcpy</span>
                <span className="text-text-disabled">{appVersion}</span>
              </div>
            )}
          </div>
        </aside>

        {/* Main content area with mobile header */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Mobile top bar — only visible below md */}
          <div className="md:hidden flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface-elevated">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="p-1.5 hover:bg-surface-hover rounded-lg transition-all duration-200 text-text-secondary hover:text-text-primary"
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
                  <rect x="5" y="9" width="5" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
                  <circle cx="20" cy="14" r="6" fill="none" stroke="currentColor" strokeWidth="2" className="text-success" />
                  <path d="M 17 14 L 19 16 L 23 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-success" />
                </svg>
              </div>
              <span className="text-sm font-bold text-text-primary">testmcpy</span>
            </div>
            <ThemeSwitcher collapsed={true} />
          </div>

          {/* Main Content */}
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<MCPExplorer selectedProfiles={selectedProfiles} />} />
              <Route path="/chat" element={<ChatInterface selectedProfiles={selectedProfiles} selectedLlmProfile={selectedLlmProfile} llmProfiles={llmProfiles} />} />
              <Route path="/tests" element={<TestManager selectedProfiles={selectedProfiles} selectedLlmProfile={selectedLlmProfile} llmProfiles={llmProfiles} />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/compatibility" element={<CompatibilityMatrix />} />
              <Route path="/generation-history" element={<GenerationHistory />} />
              <Route path="/metrics" element={<MetricsDashboard />} />
              <Route path="/compare" element={<RunComparison />} />
              <Route path="/mcp-health" element={<MCPHealth />} />
              <Route path="/security" element={<SecurityDashboard />} />
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

      </div>
  )
}

function App() {
  return (
    <Router>
      <ThemeProvider>
        <NotificationProvider>
          <TestRunProvider>
            <AppContent />
          </TestRunProvider>
        </NotificationProvider>
      </ThemeProvider>
    </Router>
  )
}

export default App
