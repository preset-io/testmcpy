// Provider/model color mapping shared across leaderboard charts so every model
// family renders with a consistent hue in light and dark themes.

// Map a provider/model pair to a coarse provider "family". Matching is done on
// the lowercased `${provider} ${model}` string so either field can identify it.
export function providerFamily(provider, model) {
  const s = `${provider || ''} ${model || ''}`.toLowerCase()
  if (s.includes('claude') || s.includes('anthropic')) return 'anthropic'
  if (
    s.includes('gpt') ||
    s.includes('openai') ||
    s.includes('codex') ||
    s.includes('o1') ||
    s.includes('o3')
  ) {
    return 'openai'
  }
  if (s.includes('gemini') || s.includes('google')) return 'google'
  if (s.includes('grok') || s.includes('xai')) return 'xai'
  return 'other'
}

// Family → hex color. Exported so callers can build legends/swatches.
export const familyColors = {
  anthropic: '#f59e0b',
  openai: '#10b981',
  google: '#3b82f6',
  xai: '#8b5cf6',
  other: '#94a3b8',
}

// Resolve a provider/model pair straight to its color.
export function providerColor(provider, model) {
  return familyColors[providerFamily(provider, model)]
}
