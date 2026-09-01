import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OAuthProbe from '../OAuthProbe'

describe('OAuthProbe', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('validates through the shared API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ valid: true, schema: 'testmcpy.io/oauth-smoke/v1', targets: ['local'], profiles: [] }),
    }))
    render(<OAuthProbe />)
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByText(/Valid testmcpy.io\/oauth-smoke\/v1/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/oauth-probe/validate', expect.objectContaining({ method: 'POST' }))
  })

  it('renders structured check results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      targets: [{ target: { id: 'edge' }, spec_profile: 'mcp-2025-06-18', duration_ms: 4,
        summary: { pass: 1 }, checks: [{ id: 'target.url.policy', status: 'pass', stage: 'target', message: 'safe' }] }]
    }) }))
    render(<OAuthProbe />)
    fireEvent.click(screen.getByRole('button', { name: /Run checks/ }))
    await waitFor(() => expect(screen.getByText('target.url.policy')).toBeInTheDocument())
    expect(screen.getByText('edge')).toBeInTheDocument()
  })
})
