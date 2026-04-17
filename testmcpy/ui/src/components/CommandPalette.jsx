import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  FileText,
  Globe,
  Server,
  Cpu,
  ArrowRight,
  Command,
} from 'lucide-react'

const TYPE_ICONS = {
  page: Globe,
  test: FileText,
  profile: Server,
  llm_profile: Cpu,
}

const TYPE_LABELS = {
  page: 'Page',
  test: 'Test',
  profile: 'MCP Profile',
  llm_profile: 'LLM Profile',
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const navigate = useNavigate()
  const debounceRef = useRef(null)

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(prev => !prev)
      }
      if (e.key === 'Escape' && open) {
        e.preventDefault()
        setOpen(false)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      setSelectedIndex(0)
      return
    }

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query.trim())}`)
        if (res.ok) {
          const data = await res.json()
          setResults(data.results || [])
          setSelectedIndex(0)
        }
      } catch (err) {
        console.error('Search failed:', err)
      } finally {
        setLoading(false)
      }
    }, 200)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  // Navigate to result
  const goToResult = useCallback((result) => {
    setOpen(false)
    navigate(result.url)
  }, [navigate])

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(prev => Math.min(prev + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(prev => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      e.preventDefault()
      goToResult(results[selectedIndex])
    }
  }

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const item = listRef.current.children[selectedIndex]
      if (item) {
        item.scrollIntoView({ block: 'nearest' })
      }
    }
  }, [selectedIndex])

  if (!open) return null

  // Group results by type
  const grouped = {}
  results.forEach(r => {
    if (!grouped[r.type]) grouped[r.type] = []
    grouped[r.type].push(r)
  })

  let flatIndex = -1

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Palette */}
      <div className="relative w-full max-w-lg mx-4 bg-surface-elevated border border-border rounded-xl shadow-strong overflow-hidden animate-slide-in">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search size={18} className="text-text-tertiary flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search pages, tests, profiles..."
            className="flex-1 bg-transparent text-text-primary placeholder-text-tertiary outline-none text-sm"
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-surface border border-border text-[10px] text-text-disabled font-mono">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto">
          {results.length === 0 && query.trim() && !loading && (
            <div className="px-4 py-8 text-center text-text-tertiary text-sm">
              No results for "{query}"
            </div>
          )}

          {results.length === 0 && !query.trim() && (
            <div className="px-4 py-8 text-center text-text-tertiary text-sm">
              <div className="flex items-center justify-center gap-2 mb-2">
                <Command size={14} />
                <span>Type to search</span>
              </div>
              <p className="text-xs text-text-disabled">Pages, test files, MCP profiles, LLM models</p>
            </div>
          )}

          {loading && results.length === 0 && (
            <div className="px-4 py-6 text-center text-text-tertiary text-sm">
              Searching...
            </div>
          )}

          {Object.entries(grouped).map(([type, items]) => (
            <div key={type}>
              <div className="px-4 py-1.5 text-[10px] font-semibold text-text-disabled uppercase tracking-wider bg-background-subtle">
                {TYPE_LABELS[type] || type}
              </div>
              {items.map((result) => {
                flatIndex++
                const isSelected = flatIndex === selectedIndex
                const idx = flatIndex
                const Icon = TYPE_ICONS[result.type] || FileText

                return (
                  <button
                    key={`${result.type}-${result.name}-${result.url}`}
                    onClick={() => goToResult(result)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                      isSelected
                        ? 'bg-primary/10 text-text-primary'
                        : 'text-text-secondary hover:bg-surface-hover'
                    }`}
                  >
                    <Icon size={16} className={isSelected ? 'text-primary' : 'text-text-tertiary'} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{result.name}</div>
                      {result.description && (
                        <div className="text-xs text-text-tertiary truncate">{result.description}</div>
                      )}
                    </div>
                    {isSelected && <ArrowRight size={14} className="text-primary flex-shrink-0" />}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-border bg-background-subtle flex items-center gap-4 text-[10px] text-text-disabled">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-surface border border-border font-mono">↑↓</kbd> navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-surface border border-border font-mono">↵</kbd> select
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-surface border border-border font-mono">esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  )
}
