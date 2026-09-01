import React, { useMemo, useState } from 'react'
import { CheckCircle2, Play, ShieldCheck, XCircle } from 'lucide-react'

const EXAMPLE = `schema: testmcpy.io/oauth-smoke/v1
targets:
  local:
    mcp_url: https://mcp.example.com/mcp
    spec_profile: mcp-2025-06-18
    oauth:
      flow: bearer
      access_token: { env: MCP_ACCESS_TOKEN }
    expectations:
      capabilities:
        bearer_challenge: required
        protected_resource_metadata: required
      min_tools: 0
`

const statusClass = {
  pass: 'text-success', fail: 'text-error', error: 'text-error', warn: 'text-warning', skip: 'text-text-muted'
}

export default function OAuthProbe() {
  const [manifest, setManifest] = useState(() => localStorage.getItem('oauthProbeManifest') || EXAMPLE)
  const [validation, setValidation] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const totals = useMemo(() => report?.targets?.reduce((all, target) => {
    Object.entries(target.summary || {}).forEach(([key, value]) => { all[key] = (all[key] || 0) + value })
    return all
  }, {}) || {}, [report])

  const request = async (path) => {
    setError(''); setRunning(true)
    try {
      localStorage.setItem('oauthProbeManifest', manifest)
      const response = await fetch(`/api/oauth-probe/${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ manifest })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
      if (path === 'validate') setValidation(data)
      else setReport(data)
    } catch (e) { setError(e.message) } finally { setRunning(false) }
  }

  return <div className="p-6 max-w-7xl mx-auto space-y-5">
    <div>
      <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck /> Auth Smoke</h1>
      <p className="text-text-secondary mt-1">Run the same versioned, headless OAuth/MCP interoperability probe exposed by <code>testmcpy auth</code>.</p>
    </div>
    <div className="grid lg:grid-cols-2 gap-5">
      <section className="bg-surface border border-border rounded-xl p-4 space-y-3">
        <div className="flex justify-between items-center"><h2 className="font-semibold">Probe manifest (YAML or JSON)</h2><span className="text-xs text-text-muted">Secrets must be environment references</span></div>
        <textarea aria-label="Probe manifest" spellCheck="false" value={manifest} onChange={e => { setManifest(e.target.value); setValidation(null) }} className="w-full h-[32rem] font-mono text-xs bg-background border border-border rounded-lg p-3 focus:ring-2 focus:ring-primary outline-none" />
        <div className="flex gap-2">
          <button disabled={running} onClick={() => request('validate')} className="px-4 py-2 border border-border rounded-lg hover:bg-surface-hover disabled:opacity-50">Validate</button>
          <button disabled={running} onClick={() => request('check')} className="px-4 py-2 bg-primary text-white rounded-lg flex items-center gap-2 disabled:opacity-50"><Play size={15}/>{running ? 'Running…' : 'Run checks'}</button>
        </div>
        {validation && <div className="text-success text-sm flex items-center gap-2"><CheckCircle2 size={16}/>Valid {validation.schema}: {validation.targets.length} target(s)</div>}
        {error && <div role="alert" className="text-error text-sm flex items-start gap-2"><XCircle size={16} className="mt-0.5 shrink-0"/>{error}</div>}
      </section>
      <section className="bg-surface border border-border rounded-xl p-4 min-w-0">
        <h2 className="font-semibold mb-3">Results</h2>
        {!report && <p className="text-text-muted text-sm">Validate a manifest, then run the probe to see stage-visible evidence here.</p>}
        {report && <div className="space-y-4">
          <div className="flex flex-wrap gap-2">{Object.entries(totals).map(([status, count]) => <span key={status} className={`px-2 py-1 rounded bg-background text-xs ${statusClass[status]}`}>{status}: {count}</span>)}</div>
          {report.targets.map(target => <div key={target.target.id} className="border border-border rounded-lg overflow-hidden">
            <div className="p-3 bg-background-subtle"><div className="font-medium">{target.target.id}</div><div className="text-xs text-text-muted">{target.spec_profile} · {target.duration_ms} ms</div></div>
            <div className="divide-y divide-border max-h-[28rem] overflow-auto">{target.checks.map((check, index) => <div key={`${check.id}-${index}`} className="p-3 text-sm">
              <div className="flex justify-between gap-3"><code className="text-xs break-all">{check.id}</code><span className={`uppercase text-xs font-semibold ${statusClass[check.status]}`}>{check.status}</span></div>
              <div className="text-text-secondary mt-1">{check.message}</div>
              <div className="text-xs text-text-muted mt-1">{check.stage}{check.http_status ? ` · HTTP ${check.http_status}` : ''}</div>
            </div>)}</div>
          </div>)}
        </div>}
      </section>
    </div>
  </div>
}
