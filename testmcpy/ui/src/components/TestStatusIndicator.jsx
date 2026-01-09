import React from 'react'
import { Loader } from 'lucide-react'

/**
 * Visual progress indicator for test execution
 * Shows progress bar, current test name, and completion count
 */
function TestStatusIndicator({ current, completed, total, status }) {
  if (status !== 'running') return null

  const progressPercentage = total > 0 ? (completed / total) * 100 : 0

  return (
    <div className="border-t border-border p-4 bg-surface-elevated">
      <div className="flex items-center gap-3 mb-3">
        <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent"></div>
        <span className="text-sm font-medium text-text-primary">Running Tests</span>
        <span className="text-xs text-text-tertiary">
          {completed} / {total}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-surface rounded-full overflow-hidden mb-3">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${progressPercentage}%` }}
        />
      </div>

      {/* Current test */}
      {current && (
        <div className="text-xs text-text-tertiary flex items-center gap-2">
          <Loader size={12} className="animate-spin" />
          <span>Running: {current}</span>
        </div>
      )}
    </div>
  )
}

export default TestStatusIndicator
