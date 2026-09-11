import { fireEvent, render, screen } from '@testing-library/react'
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

  it('does not offer web execution without a safe credential channel', () => {
    render(<OAuthProbe />)
    expect(screen.queryByRole('button', { name: /Run checks/ })).not.toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('does not yet provide a safe channel')
    expect(screen.getByRole('note')).toHaveTextContent('testmcpy auth check')
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
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unknown profile: strict')
    expect(screen.getByRole('button', { name: 'Validate' })).toBeEnabled()
  })

  it('reports network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network unavailable')))
    render(<OAuthProbe />)
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable')
  })
})
