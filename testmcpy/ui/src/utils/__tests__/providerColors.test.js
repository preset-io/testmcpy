import { describe, it, expect } from 'vitest'
import { providerColor, providerFamily, buildColorScale } from '../providerColors'

describe('providerFamily', () => {
  it('classifies known providers/models by either field', () => {
    expect(providerFamily('claude-sdk', 'claude-opus-4-8')).toBe('anthropic')
    expect(providerFamily('openai', 'gpt-4o')).toBe('openai')
    expect(providerFamily('codex-sdk', 'o3')).toBe('openai')
    expect(providerFamily('google-adk', 'gemini-2.5-pro')).toBe('google')
    expect(providerFamily('xai', 'grok-4')).toBe('xai')
    expect(providerFamily('whoknows', 'mystery-model')).toBe('other')
  })
})

describe('providerColor', () => {
  it('is a stable pure function of (provider, model)', () => {
    const a = providerColor('claude-sdk', 'claude-opus-4-8')
    const b = providerColor('claude-sdk', 'claude-opus-4-8')
    expect(a).toBe(b)
    expect(a).toMatch(/^hsl\(\d+(\.\d+)?, \d+%, \d+%\)$/)
  })

  it('gives different models in the SAME family different colors (the all-yellow bug)', () => {
    const models = [
      'claude-opus-4-8',
      'claude-sonnet-4-5',
      'claude-haiku-4-5',
      'claude-3-7-sonnet',
      'claude-opus-4-1',
    ]
    const colors = models.map((m) => providerColor('claude-sdk', m))
    // Every Claude model must resolve to a distinct color, not one shared amber.
    expect(new Set(colors).size).toBe(models.length)
  })

  it('keeps distinct families in visibly different hue ranges', () => {
    const anthropic = providerColor('claude-sdk', 'claude-opus-4-8')
    const openai = providerColor('openai', 'gpt-4o')
    expect(anthropic).not.toBe(openai)
  })
})

describe('buildColorScale', () => {
  const configs = [
    { provider: 'claude-sdk', model: 'claude-opus-4-8' },
    { provider: 'claude-sdk', model: 'claude-sonnet-4-5' },
    { provider: 'claude-sdk', model: 'claude-haiku-4-5' },
    { provider: 'openai', model: 'gpt-4o' },
  ]

  it('assigns every distinct model a distinct, evenly-spaced color', () => {
    const scale = buildColorScale(configs)
    const colors = configs.map((c) => scale(c.provider, c.model))
    expect(new Set(colors).size).toBe(configs.length)
    // Evenly spaced → 4 models at 0/90/180/270 hues.
    expect(colors.some((c) => c.startsWith('hsl(0.0,'))).toBe(true)
    expect(colors.some((c) => c.startsWith('hsl(90.0,'))).toBe(true)
  })

  it('is order-independent: same model → same color regardless of input order', () => {
    const a = buildColorScale(configs)
    const b = buildColorScale([...configs].reverse())
    for (const c of configs) {
      expect(a(c.provider, c.model)).toBe(b(c.provider, c.model))
    }
  })

  it('collapses effort/duplicate rows of the same model to one color', () => {
    const scale = buildColorScale([
      { provider: 'claude-sdk', model: 'claude-opus-4-8', effort: 'low' },
      { provider: 'claude-sdk', model: 'claude-opus-4-8', effort: 'high' },
    ])
    expect(scale('claude-sdk', 'claude-opus-4-8')).toBe(scale('claude-sdk', 'claude-opus-4-8'))
    // Single distinct model → hue 0.
    expect(scale('claude-sdk', 'claude-opus-4-8')).toMatch(/^hsl\(0\.0,/)
  })

  it('falls back to the stable per-model color for unknown models', () => {
    const scale = buildColorScale(configs)
    expect(scale('xai', 'grok-4')).toBe(providerColor('xai', 'grok-4'))
  })
})
