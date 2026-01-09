import React from 'react'
import { AlertCircle, RefreshCw, X } from 'lucide-react'

/**
 * ErrorAlert component for displaying actionable error messages.
 *
 * Shows errors in a non-blocking way with options to retry or dismiss.
 * This prevents the UI from freezing on errors.
 *
 * @param {Object} props
 * @param {string} props.error - Error message to display
 * @param {Function} props.onRetry - Optional callback when retry is clicked
 * @param {Function} props.onDismiss - Optional callback when dismiss is clicked
 * @param {string} props.title - Optional custom title (default: "Error")
 * @param {boolean} props.showRetry - Whether to show retry button (default: true)
 * @param {boolean} props.showDismiss - Whether to show dismiss button (default: true)
 */
function ErrorAlert({
  error,
  onRetry,
  onDismiss,
  title = 'Error',
  showRetry = true,
  showDismiss = true
}) {
  if (!error) return null

  return (
    <div className="bg-error/10 border-2 border-error/30 rounded-lg p-4 animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <AlertCircle className="text-error" size={20} />
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-error mb-1">{title}</h4>
          <p className="text-sm text-text-primary whitespace-pre-wrap break-words">
            {error}
          </p>
        </div>

        <div className="flex-shrink-0 flex gap-2">
          {showRetry && onRetry && (
            <button
              onClick={onRetry}
              className="p-1.5 hover:bg-error/20 rounded transition-colors"
              title="Retry"
            >
              <RefreshCw size={16} className="text-error" />
            </button>
          )}

          {showDismiss && onDismiss && (
            <button
              onClick={onDismiss}
              className="p-1.5 hover:bg-error/20 rounded transition-colors"
              title="Dismiss"
            >
              <X size={16} className="text-error" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default ErrorAlert
