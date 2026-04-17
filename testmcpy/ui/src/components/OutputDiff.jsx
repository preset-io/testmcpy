import React, { useMemo } from 'react'

/**
 * Simple word-level diff between two strings.
 * Returns an array of { type: 'same' | 'added' | 'removed', text: string } segments.
 */
function computeDiff(textA, textB) {
  const wordsA = (textA || '').split(/(\s+)/)
  const wordsB = (textB || '').split(/(\s+)/)

  // Simple LCS-based diff (O(n*m) but fine for reasonably-sized text)
  const m = wordsA.length
  const n = wordsB.length

  // For very large texts, fall back to simple side-by-side
  if (m * n > 500000) {
    return {
      segments: [],
      tooLarge: true,
    }
  }

  // Build LCS table
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (wordsA[i - 1] === wordsB[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }

  // Backtrack to get diff segments
  const segments = []
  let i = m
  let j = n

  const stack = [] // build in reverse, then reverse
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && wordsA[i - 1] === wordsB[j - 1]) {
      stack.push({ type: 'same', text: wordsA[i - 1] })
      i--
      j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      stack.push({ type: 'added', text: wordsB[j - 1] })
      j--
    } else {
      stack.push({ type: 'removed', text: wordsA[i - 1] })
      i--
    }
  }

  stack.reverse()

  // Merge consecutive same-type segments
  for (const seg of stack) {
    if (segments.length > 0 && segments[segments.length - 1].type === seg.type) {
      segments[segments.length - 1].text += seg.text
    } else {
      segments.push({ ...seg })
    }
  }

  return { segments, tooLarge: false }
}

function OutputDiff({ textA, textB, labelA = 'Run A', labelB = 'Run B' }) {
  const { segments, tooLarge } = useMemo(() => computeDiff(textA, textB), [textA, textB])

  if (!textA && !textB) {
    return <div className="text-xs text-text-tertiary text-center py-4">No output to compare</div>
  }

  // For very large texts, show side-by-side only
  if (tooLarge) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-xs font-semibold text-text-secondary mb-1">{labelA}</div>
          <pre className="text-xs font-mono bg-surface p-3 rounded border border-border overflow-auto max-h-96 text-text-secondary whitespace-pre-wrap">
            {textA || '(empty)'}
          </pre>
        </div>
        <div>
          <div className="text-xs font-semibold text-text-secondary mb-1">{labelB}</div>
          <pre className="text-xs font-mono bg-surface p-3 rounded border border-border overflow-auto max-h-96 text-text-secondary whitespace-pre-wrap">
            {textB || '(empty)'}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-4 text-xs text-text-tertiary mb-2">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-error/30 border border-error/50" />
          Removed ({labelA})
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-success/30 border border-success/50" />
          Added ({labelB})
        </span>
      </div>
      <div className="font-mono text-xs bg-surface p-3 rounded border border-border overflow-auto max-h-96 whitespace-pre-wrap leading-relaxed">
        {segments.map((seg, idx) => {
          if (seg.type === 'removed') {
            return (
              <span key={idx} className="bg-error/20 text-error line-through decoration-error/50">
                {seg.text}
              </span>
            )
          }
          if (seg.type === 'added') {
            return (
              <span key={idx} className="bg-success/20 text-success">
                {seg.text}
              </span>
            )
          }
          return <span key={idx} className="text-text-secondary">{seg.text}</span>
        })}
      </div>
    </div>
  )
}

export default OutputDiff
