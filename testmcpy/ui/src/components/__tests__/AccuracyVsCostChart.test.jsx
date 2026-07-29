import { describe, it, expect } from 'vitest'
import { buildEffortSeries, computeYDomain } from '../AccuracyVsCostChart'

// Series shape computeYDomain consumes: only `points[].y` (pass rate, 0..100).
const series = (...ys) => [{ points: ys.map((y) => ({ y })) }]

const cfg = (over) => ({
  model: 'claude-opus-4-8',
  provider: 'claude-sdk',
  mcp_profile: null,
  effort: null,
  n_results: 4,
  total_cost: 0.4,
  pass_rate: 0.8,
  key: 'claude-sdk/claude-opus-4-8',
  ...over,
})

describe('buildEffortSeries', () => {
  it('does not merge the same model across different providers', () => {
    const series = buildEffortSeries([
      cfg({ provider: 'claude-sdk', key: 'claude-sdk/claude-opus-4-8' }),
      cfg({ provider: 'bedrock', key: 'bedrock/claude-opus-4-8' }),
    ])
    // Two distinct providers → two separate curves (the review's issue 2).
    expect(series).toHaveLength(2)
    expect(new Set(series.map((s) => s.key)).size).toBe(2)
  })

  it('does not merge the same model+provider across different MCP profiles', () => {
    const series = buildEffortSeries([
      cfg({ mcp_profile: 'staging', key: 'claude-sdk/claude-opus-4-8 @ staging' }),
      cfg({ mcp_profile: 'prod', key: 'claude-sdk/claude-opus-4-8 @ prod' }),
    ])
    expect(series).toHaveLength(2)
  })

  it('connects one config across effort levels, sorted low→high', () => {
    const series = buildEffortSeries([
      cfg({ effort: 'high', total_cost: 1.2, key: 'claude-sdk/claude-opus-4-8 [high]' }),
      cfg({ effort: 'low', total_cost: 0.2, key: 'claude-sdk/claude-opus-4-8 [low]' }),
      cfg({ effort: 'medium', total_cost: 0.6, key: 'claude-sdk/claude-opus-4-8 [medium]' }),
    ])
    expect(series).toHaveLength(1)
    expect(series[0].points.map((p) => p.effort)).toEqual(['low', 'medium', 'high'])
  })

  it('drops configs with no results or non-positive cost (log axis)', () => {
    const series = buildEffortSeries([
      cfg({ n_results: 0 }),
      cfg({ total_cost: 0, provider: 'openai', key: 'openai/x' }),
    ])
    expect(series).toHaveLength(0)
  })
})

describe('computeYDomain', () => {
  it('falls back to the full 0–100 axis when there is no data', () => {
    expect(computeYDomain([])).toEqual([0, 100])
  })

  it('brackets a high-clustered field without starting at zero', () => {
    // Pass rates 72–94 → padded, snapped-to-5 window that excludes 0 so the
    // spread fills the axis instead of hugging the top.
    const [min, max] = computeYDomain(series(72, 88, 94, 81))
    expect(min).toBeGreaterThan(0)
    expect(min).toBeLessThanOrEqual(72)
    expect(max).toBeGreaterThanOrEqual(94)
    expect(max).toBeLessThanOrEqual(100)
    expect(min % 5).toBe(0)
    expect(max % 5).toBe(0)
  })

  it('never exceeds [0,100] even with extreme values', () => {
    const [min, max] = computeYDomain(series(0, 100))
    expect(min).toBe(0)
    expect(max).toBe(100)
  })

  it('gives a single-value field a visible, non-zero-height band', () => {
    const [min, max] = computeYDomain(series(80, 80, 80))
    expect(max).toBeGreaterThan(min)
    expect(min).toBeGreaterThan(0)
  })
})
