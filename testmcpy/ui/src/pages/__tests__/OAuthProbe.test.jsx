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
    expect(screen.getByText('pass: 1')).toBeInTheDocument()
  })

  it('restores and persists the edited manifest', async () => {
    localStorage.setItem('oauthProbeManifest', 'stored manifest')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ valid: true, schema: 'v1', targets: [], profiles: [] }),
    }))
    render(<OAuthProbe />)
    const editor = screen.getByLabelText('Probe manifest')
    expect(editor).toHaveValue('stored manifest')
    fireEvent.change(editor, { target: { value: 'edited manifest' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    await screen.findByText(/Valid v1/)
    expect(localStorage.getItem('oauthProbeManifest')).toBe('edited manifest')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ manifest: 'edited manifest' })
  })

  it('shows API errors and re-enables actions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'Unknown profile: strict' }),
    }))
    render(<OAuthProbe />)
    fireEvent.click(screen.getByRole('button', { name: /Run checks/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unknown profile: strict')
    expect(screen.getByRole('button', { name: 'Validate' })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Run checks/ })).toBeEnabled()
  })

  it('reports network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network unavailable')))
    render(<OAuthProbe />)
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable')
  })
})
