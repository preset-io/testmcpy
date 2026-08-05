// Provider/model color mapping shared across leaderboard charts so every model
// renders with a stable, distinguishable color in light and dark themes.
//
// providerColor() gives each distinct model its own well-separated hue spread
// across the whole color wheel — so a leaderboard that's mostly one provider
// (e.g. all Claude) still comes out multi-colored instead of all-amber. It's a
// pure function of (provider, model): a given model keeps the same color across
// the bar chart, the accuracy-vs-cost curve, and the per-suite facets. The
// providerFamily/familyColors helpers below stay available for coarse
// family-level grouping (legends, swatches) where that's wanted.

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

// Family → representative hex color. Exported so callers can build legends or
// swatches keyed on the coarse family rather than the per-model shade.
export const familyColors = {
  anthropic: '#f59e0b',
  openai: '#10b981',
  google: '#3b82f6',
  xai: '#8b5cf6',
  other: '#94a3b8',
}

// Stable 32-bit FNV-1a hash so a model's color is deterministic (no Math.random)
// and identical on every render and in every chart.
function hashStr(s) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// Resolve a provider/model pair to a distinct, stable color. Hue is spread
// across the full wheel via the golden angle (137.5°) so distinct models land
// far apart even when they all belong to one provider; saturation/lightness sit
// in a readable mid-band that works on both light and dark backgrounds.
export function providerColor(provider, model) {
  const hash = hashStr(`${provider || ''}/${model || ''}`)
  const hue = (hash * 137.508) % 360
  const sat = 68 + (hash % 3) * 8 // 68 / 76 / 84
  const light = 52 + ((hash >>> 5) % 3) * 7 // 52 / 59 / 66
  return `hsl(${hue.toFixed(1)}, ${sat}%, ${light}%)`
}

// Stable coloring identity: same provider+model → same color.
export function modelColorKey(provider, model) {
  return `${provider || ''}/${model || ''}`
}

// Build an evenly-spaced color scale over the distinct models in `configs`, so
// every model gets a maximally-separated hue and — because a single scale is
// shared — the SAME color in every chart that uses it. Returns a
// (provider, model) => hsl function; models not in `configs` fall back to the
// stable per-model providerColor(). Distinct models are sorted so the mapping
// is deterministic regardless of input order.
export function buildColorScale(configs) {
  const keys = []
  const seen = new Set()
  for (const c of configs || []) {
    const k = modelColorKey(c.provider, c.model)
    if (!seen.has(k)) {
      seen.add(k)
      keys.push(k)
    }
  }
  keys.sort()
  const n = keys.length
  const map = new Map()
  keys.forEach((k, i) => {
    const hue = n > 0 ? (i * 360) / n : 0
    // Nudge lightness on alternating entries so that when n is large (hues get
    // close) there's still a second axis of separation.
    const light = 54 + (i % 2 === 0 ? 0 : 9)
    map.set(k, `hsl(${hue.toFixed(1)}, 74%, ${light}%)`)
  })
  return (provider, model) => map.get(modelColorKey(provider, model)) || providerColor(provider, model)
}
