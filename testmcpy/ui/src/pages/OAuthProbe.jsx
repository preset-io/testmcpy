import React, { useState } from 'react'
import { CheckCircle2, ShieldCheck, XCircle } from 'lucide-react'

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

export default function OAuthProbe() {
  const [manifest, setManifest] = useState(() => localStorage.getItem('oauthProbeManifest') || EXAMPLE)
  const [validation, setValidation] = useState(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const validate = async () => {
    setError(''); setRunning(true)
    try {
      localStorage.setItem('oauthProbeManifest', manifest)
      const response = await fetch('/api/oauth-probe/validate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ manifest })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
      setValidation(data)
    } catch (e) { setError(e.message) } finally { setRunning(false) }
  }

  return <div className="p-6 max-w-7xl mx-auto space-y-5">
    <div>
      <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck /> Auth Smoke</h1>
      <p className="text-text-secondary mt-1">Validate manifests for the versioned, headless OAuth/MCP interoperability probe exposed by <code>testmcpy auth</code>.</p>
    </div>
    <div className="grid lg:grid-cols-2 gap-5">
      <section className="bg-surface border border-border rounded-xl p-4 space-y-3">
        <div className="flex justify-between items-center"><h2 className="font-semibold">Probe manifest (YAML or JSON)</h2><span className="text-xs text-text-muted">Secrets must be environment references</span></div>
        <textarea aria-label="Probe manifest" spellCheck="false" value={manifest} onChange={e => { setManifest(e.target.value); setValidation(null) }} className="w-full h-[32rem] font-mono text-xs bg-background border border-border rounded-lg p-3 focus:ring-2 focus:ring-primary outline-none" />
        <div className="flex gap-2">
          <button disabled={running} onClick={validate} className="px-4 py-2 border border-border rounded-lg hover:bg-surface-hover disabled:opacity-50">{running ? 'Validating…' : 'Validate'}</button>
        </div>
        {validation && <div className="text-success text-sm flex items-center gap-2"><CheckCircle2 size={16}/>Valid {validation.schema}: {validation.targets.length} target(s)</div>}
        {error && <div role="alert" className="text-error text-sm flex items-start gap-2"><XCircle size={16} className="mt-0.5 shrink-0"/>{error}</div>}
      </section>
      <section className="bg-surface border border-border rounded-xl p-4 min-w-0">
        <h2 className="font-semibold mb-3">Run checks from the CLI</h2>
        <div role="note" className="space-y-3 text-sm text-text-secondary">
          <p>Web execution is disabled because this page does not yet provide a safe channel for probe authentication and referenced credentials.</p>
          <p>Save the manifest locally and run <code className="text-text-primary">testmcpy auth check --manifest &lt;path&gt;</code> in an environment containing its referenced credentials.</p>
        </div>
      </section>
    </div>
  </div>
}
