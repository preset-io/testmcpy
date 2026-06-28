import React, { useState, useMemo, useEffect } from 'react'
import { X, Plus, Play, Zap, ClipboardPaste } from 'lucide-react'
import { useTestRun } from '../contexts/TestRunContext'

// Persist the long connection/auth block (incl. JWT) so it isn't retyped.
// localhost dev tool — acceptable to keep in localStorage.
const CONN_KEY = 'testmcpy.benchmark.connection'

const EMPTY_CONN = {
  mcp_url: '',
  auth_type: 'jwt',
  jwt_url: '',
  jwt_token: '',
  jwt_secret: '',
  auth_token: '',
  workspace_hash: '',
  domain: '',
  assistant_conversations_path: '',
  assistant_completions_path: '',
}

// Map `testmcpy run`/`bench --run-args` flags onto our connection fields so a
// user can paste the exact string from their bench script.
const FLAG_MAP = {
  '--mcp-url': 'mcp_url',
  '--auth-type': 'auth_type',
  '--jwt-url': 'jwt_url',
  '--jwt-token': 'jwt_token',
  '--jwt-secret': 'jwt_secret',
  '--auth-token': 'auth_token',
  '--workspace-hash': 'workspace_hash',
  '--domain': 'domain',
  '--assistant-conversations-path': 'assistant_conversations_path',
  '--assistant-completions-path': 'assistant_completions_path',
}

function parseRunArgs(text) {
  const tokens = text.trim().split(/\s+/)
  const out = {}
  for (let i = 0; i < tokens.length; i++) {
    const field = FLAG_MAP[tokens[i]]
    if (field && i + 1 < tokens.length) {
      out[field] = tokens[i + 1]
      i++
    }
  }
  return out
}

function loadConn() {
  try {
    return { ...EMPTY_CONN, ...JSON.parse(localStorage.getItem(CONN_KEY) || '{}') }
  } catch {
    return { ...EMPTY_CONN }
  }
}

function BenchmarkModal({ defaultTestPath = '', onClose }) {
  const { runBenchmark } = useTestRun()

  const [testPath, setTestPath] = useState(defaultTestPath)
  const [models, setModels] = useState(['claude-sonnet-4-6'])
  const [modelInput, setModelInput] = useState('')
  const [providers, setProviders] = useState('assistant')
  const [profiles, setProfiles] = useState('')
  const [repeat, setRepeat] = useState(3)
  const [conn, setConn] = useState(loadConn)
  const [runArgs, setRunArgs] = useState('')

  useEffect(() => {
    setTestPath(defaultTestPath)
  }, [defaultTestPath])

  const profileList = profiles.split(',').map(s => s.trim()).filter(Boolean)
  const comboCount = models.length * (profileList.length || 1) * Math.max(1, repeat)

  const previewLabels = useMemo(() => {
    const provs = providers.split(',').map(s => s.trim()).filter(Boolean)
    const profs = profileList.length ? profileList : [null]
    const out = []
    models.forEach((m, i) => {
      const prov = provs.length === 1 ? provs[0] : provs[i] || provs[0] || 'default'
      profs.forEach(pf => out.push(`${prov || 'default'}/${m}${pf ? ` @ ${pf}` : ''} ×${repeat}`))
    })
    return out
  }, [models, providers, profiles, repeat]) // eslint-disable-line react-hooks/exhaustive-deps

  const addModel = () => {
    const m = modelInput.trim()
    if (m && !models.includes(m)) setModels([...models, m])
    setModelInput('')
  }

  const updateConn = (k, v) => setConn(prev => ({ ...prev, [k]: v }))

  const applyRunArgs = () => {
    const parsed = parseRunArgs(runArgs)
    if (Object.keys(parsed).length) setConn(prev => ({ ...prev, ...parsed }))
  }

  const canRun = testPath.trim() && models.length > 0 && comboCount > 0

  const start = () => {
    localStorage.setItem(CONN_KEY, JSON.stringify(conn))
    const payload = {
      test_path: testPath.trim(),
      models,
      repeat: Number(repeat) || 1,
      label: `${testPath.trim().split('/').filter(Boolean).pop()} · ${models.join(', ')} ×${repeat}`,
    }
    const provs = providers.split(',').map(s => s.trim()).filter(Boolean)
    if (provs.length) payload.providers = provs
    if (profileList.length) payload.profiles = profileList
    // Only send non-empty connection fields.
    Object.entries(conn).forEach(([k, v]) => {
      if (v && String(v).trim()) payload[k] = v
    })
    runBenchmark(payload)
    onClose?.()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="bg-surface-elevated border border-border rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-surface-elevated border-b border-border px-5 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-primary" />
            <h2 className="text-base font-semibold text-text-primary">Run Benchmark</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-surface-hover text-text-tertiary" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Target */}
          <div>
            <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Test file or directory</label>
            <input
              className="input w-full mt-1 text-sm"
              value={testPath}
              onChange={e => setTestPath(e.target.value)}
              placeholder="tests/chatbot/"
            />
          </div>

          {/* Matrix: models */}
          <div>
            <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Models</label>
            <div className="flex flex-wrap gap-1.5 mt-1 mb-1.5">
              {models.map(m => (
                <span key={m} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20">
                  {m}
                  <button onClick={() => setModels(models.filter(x => x !== m))} className="hover:text-error"><X size={11} /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                className="input flex-1 text-sm"
                value={modelInput}
                onChange={e => setModelInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addModel() } }}
                placeholder="add a model, e.g. claude-opus-4-8"
              />
              <button onClick={addModel} className="btn btn-ghost px-2"><Plus size={15} /></button>
            </div>
          </div>

          {/* Matrix: providers / profiles / repeat */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Providers</label>
              <input className="input w-full mt-1 text-sm" value={providers} onChange={e => setProviders(e.target.value)} placeholder="assistant" title="One value applies to all models, or a comma list aligned to models" />
            </div>
            <div>
              <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">MCP profiles</label>
              <input className="input w-full mt-1 text-sm" value={profiles} onChange={e => setProfiles(e.target.value)} placeholder="(none)" title="Optional, comma-separated; each is a full product dimension" />
            </div>
            <div>
              <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Repeat</label>
              <input type="number" min="1" className="input w-full mt-1 text-sm" value={repeat} onChange={e => setRepeat(e.target.value)} />
            </div>
          </div>

          {/* Connection / auth */}
          <details className="rounded-lg border border-border" open={!conn.mcp_url}>
            <summary className="px-3 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wide cursor-pointer">
              Connection &amp; auth {conn.mcp_url ? '✓' : '(required for assistant)'}
            </summary>
            <div className="p-3 space-y-3 border-t border-border">
              <div>
                <label className="text-[11px] text-text-tertiary flex items-center gap-1"><ClipboardPaste size={11} /> Paste run-args (auto-fills the fields below)</label>
                <div className="flex gap-2 mt-1">
                  <textarea
                    className="input flex-1 text-xs font-mono h-16"
                    value={runArgs}
                    onChange={e => setRunArgs(e.target.value)}
                    placeholder="--mcp-url https://… --auth-type jwt --jwt-url … --jwt-token … --jwt-secret … --workspace-hash … --domain …"
                  />
                  <button onClick={applyRunArgs} className="btn btn-ghost px-2 text-xs self-start">Parse</button>
                </div>
              </div>
              <div className="flex items-center gap-2 mb-2">
                <label className="text-[11px] text-text-tertiary">Auth type</label>
                <select
                  className="input text-xs py-1"
                  value={conn.auth_type}
                  onChange={e => updateConn('auth_type', e.target.value)}
                >
                  <option value="jwt">jwt</option>
                  <option value="bearer">bearer</option>
                  <option value="api_key">api_key</option>
                  <option value="">none</option>
                </select>
                {(conn.auth_type === 'bearer' || conn.auth_type === 'api_key') && (
                  <input
                    className="input text-xs font-mono flex-1"
                    value={conn.auth_token || ''}
                    onChange={e => updateConn('auth_token', e.target.value)}
                    placeholder="auth token"
                  />
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['mcp_url', 'MCP URL'],
                  ['domain', 'Domain'],
                  ['jwt_url', 'JWT URL'],
                  ['workspace_hash', 'Workspace hash'],
                  ['jwt_token', 'JWT token'],
                  ['jwt_secret', 'JWT secret'],
                  ['assistant_conversations_path', 'Conversations path'],
                  ['assistant_completions_path', 'Completions path'],
                ].map(([k, label]) => (
                  <input
                    key={k}
                    className="input text-xs font-mono"
                    value={conn[k]}
                    onChange={e => updateConn(k, e.target.value)}
                    placeholder={label}
                    title={label}
                  />
                ))}
              </div>
            </div>
          </details>

          {/* Combo preview */}
          <div className="rounded-lg border border-border bg-surface p-3">
            <div className="text-xs text-text-secondary mb-1.5">
              <span className="font-semibold text-text-primary">{comboCount}</span> run(s):
              {' '}{models.length} model(s) × {profileList.length || 1} profile(s) × {repeat} repeat(s)
            </div>
            <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
              {previewLabels.slice(0, 24).map((l, i) => (
                <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-surface-hover text-text-tertiary font-mono">{l}</span>
              ))}
              {previewLabels.length > 24 && <span className="text-[10px] text-text-disabled">+{previewLabels.length - 24} more</span>}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-surface-elevated border-t border-border px-5 py-3 flex items-center justify-end gap-2">
          <button onClick={onClose} className="btn btn-ghost text-sm">Cancel</button>
          <button onClick={start} disabled={!canRun} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Play size={14} /> Run {comboCount} benchmark{comboCount === 1 ? '' : 's'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default BenchmarkModal
