import { describe, it, expect } from 'vitest'
import { buildEffortSeries } from '../AccuracyVsCostChart'

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
