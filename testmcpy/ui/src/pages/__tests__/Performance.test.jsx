import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import Performance from '../Performance'
import { TestRunProvider } from '../../contexts/TestRunContext'

const emptyMatrix = { configs: [], rows: [], warnings: [] }
const emptyLeaderboard = { configs: [], total: 0 }
const emptyFilters = { models: [], providers: [], test_files: [], mcp_profiles: [] }

const populatedMatrix = {
  configs: [
    {
      key: 'claude-sonnet-4-5 (anthropic)',
      model: 'claude-sonnet-4-5',
      provider: 'anthropic',
      mcp_profile: null,
      n_runs: 3,
      n_results: 6,
      pass_rate: 0.8333,
      total_cost: 0.12,
      flaky_cells: 1,
    },
  ],
  rows: [
    {
      question_id: 'q_multi_run',
      cells: {
        'claude-sonnet-4-5 (anthropic)': {
          n: 3,
          pass_rate: 1.0,
          flaky: false,
          avg_score: 0.95,
          avg_cost: 0.01,
          avg_duration_ms: 1200,
          last_run_at: '2026-06-09T00:00:00Z',
          trend: [1.0, 1.0, 1.0],
        },
      },
    },
    {
      question_id: 'q_single_run',
      cells: {
        'claude-sonnet-4-5 (anthropic)': {
          n: 1,
          pass_rate: 0.0,
          flaky: false,
          avg_score: 0.1,
          avg_cost: 0.02,
          avg_duration_ms: 900,
          last_run_at: '2026-06-09T00:00:00Z',
          trend: [0.0],
        },
      },
    },
  ],
  warnings: ['Only 3 runs total — results may not be statistically meaningful'],
}

const populatedLeaderboard = {
  configs: [
    {
      key: 'claude-sonnet-4-5 (anthropic)',
      model: 'claude-sonnet-4-5',
      provider: 'anthropic',
      mcp_profile: null,
      n_runs: 3,
      n_results: 6,
      pass_rate: 0.8333,
      total_cost: 0.12,
      flaky_cells: 1,
      avg_duration_ms: 1100.0,
      cost_per_pass: 0.024,
    },
  ],
  total: 1,
}

function mockFetch({ matrix, leaderboard }) {
  global.fetch = vi.fn((url) => {
    const u = String(url)
    let body = {}
    if (u.includes('/api/analytics/matrix')) body = matrix
    else if (u.includes('/api/analytics/leaderboard')) body = leaderboard
    else if (u.includes('/api/analytics/question-history')) {
      body = { question_id: 'q', points: [], total: 0 }
    } else if (u.includes('/api/results/filters')) body = emptyFilters
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
}

function renderPage() {
  return render(
    <BrowserRouter>
      <TestRunProvider>
        <Performance />
      </TestRunProvider>
    </BrowserRouter>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('Performance', () => {
  it('renders empty state when API returns no configs', async () => {
    mockFetch({ matrix: emptyMatrix, leaderboard: emptyLeaderboard })
    renderPage()

    expect(
      await screen.findByText('No completed runs across configs yet')
    ).toBeInTheDocument()
    expect(
      screen.getByText('testmcpy bench tests/ --models claude-sonnet-4-5,gpt-4o --repeat 3')
    ).toBeInTheDocument()
    expect(
      screen.getByText('or run the same suite with different --model/--profile flags')
    ).toBeInTheDocument()
  })

  it('renders matrix cells with pass% when API returns data', async () => {
    mockFetch({ matrix: populatedMatrix, leaderboard: populatedLeaderboard })
    renderPage()

    // Row labels
    expect(await screen.findByText('q_multi_run')).toBeInTheDocument()
    expect(screen.getByText('q_single_run')).toBeInTheDocument()

    // Cell pass% for the multi-run cell (now shows "n=3 · <avg score>")
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText(/n=3/)).toBeInTheDocument()

    // Footer aggregate rows (Pass rate / Avg score / Cost per run)
    expect(screen.getByText('Pass rate')).toBeInTheDocument()
    expect(screen.getByText('3 runs')).toBeInTheDocument()

    // Warnings banner
    expect(
      screen.getByText('Only 3 runs total — results may not be statistically meaningful')
    ).toBeInTheDocument()
  })

  it('gives n=1 cells the neutral single-run treatment', async () => {
    mockFetch({ matrix: populatedMatrix, leaderboard: populatedLeaderboard })
    renderPage()

    await screen.findByText('q_single_run')

    const singleRunCell = screen.getByTitle('single run — not statistically meaningful')
    expect(singleRunCell).toBeInTheDocument()
    // Neutral: no red/green/amber tint despite pass_rate of 0
    expect(singleRunCell.className).toContain('bg-surface')
    expect(singleRunCell.className).not.toContain('bg-error')
    expect(singleRunCell.className).not.toContain('bg-success')
    expect(singleRunCell.className).not.toContain('bg-warning')
  })
})
