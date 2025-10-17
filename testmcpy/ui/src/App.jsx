import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import {
  Package,
  MessageSquare,
  FileText,
  Settings,
  Menu,
  X,
  Server,
  Cpu,
  CheckCircle2
} from 'lucide-react'

import MCPExplorer from './pages/MCPExplorer'
import ChatInterface from './pages/ChatInterface'
import TestManager from './pages/TestManager'
import Configuration from './pages/Configuration'

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [config, setConfig] = useState({})

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const res = await fetch('/api/config')
      const data = await res.json()
      setConfig(data)
    } catch (error) {
      console.error('Failed to load config:', error)
    }
  }

  const getMcpUrl = () => {
    const url = config.MCP_URL?.value || 'Not configured'
    // Shorten URL for display
    if (url.length > 40 && sidebarOpen) {
      const urlObj = new URL(url)
      return `${urlObj.protocol}//${urlObj.hostname}/mcp`
    }
    return url
  }

  const getModel = () => {
    const provider = config.DEFAULT_PROVIDER?.value || 'unknown'
    const model = config.DEFAULT_MODEL?.value || 'not set'
    return { provider, model }
  }

  const navItems = [
    { path: '/', label: 'MCP Explorer', icon: Package },
    { path: '/chat', label: 'Chat', icon: MessageSquare },
    { path: '/tests', label: 'Tests', icon: FileText },
    { path: '/config', label: 'Config', icon: Settings },
  ]

  return (
    <Router>
      <div className="flex h-screen bg-background text-text-primary">
        {/* Sidebar */}
        <aside
          className={`${
            sidebarOpen ? 'w-64' : 'w-16'
          } bg-surface-elevated border-r border-border transition-all duration-300 flex flex-col shadow-medium`}
        >
          <div className="p-4 flex items-center justify-between border-b border-border">
            {sidebarOpen && (
              <h1 className="text-xl font-bold text-primary">testmcpy</h1>
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
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
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

          {/* Connection Status */}
          <div className="px-3 pb-3 border-t border-border space-y-2">
            {sidebarOpen ? (
              <div className="mt-3 bg-primary/10 border border-primary/30 rounded-lg p-3 space-y-2.5">
                <div className="flex items-start gap-2">
                  <CheckCircle2 size={16} className="text-success mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-success mb-0.5">Connected</div>
                    <div className="flex items-center gap-1.5">
                      <Server size={12} className="text-primary-light flex-shrink-0" />
                      <div className="text-xs text-text-secondary truncate" title={config.MCP_URL?.value}>
                        {getMcpUrl()}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-start gap-2 pt-2 border-t border-border/50">
                  <Cpu size={16} className="text-primary-light mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-primary-light mb-0.5">Model</div>
                    <div className="text-xs text-text-secondary">
                      <div className="truncate">{getModel().model}</div>
                      <div className="text-text-tertiary text-[10px] capitalize">{getModel().provider}</div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-3 flex flex-col items-center gap-2 py-2">
                <CheckCircle2 size={20} className="text-success" />
                <Server size={18} className="text-primary-light" />
                <Cpu size={18} className="text-primary-light" />
              </div>
            )}
          </div>

          <div className="p-4 border-t border-border">
            {sidebarOpen && (
              <div className="text-xs text-text-tertiary space-y-0.5">
                <div className="font-medium">MCP Testing Framework</div>
                <div className="text-text-disabled">v1.0.0</div>
              </div>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<MCPExplorer />} />
            <Route path="/chat" element={<ChatInterface />} />
            <Route path="/tests" element={<TestManager />} />
            <Route path="/config" element={<Configuration />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
