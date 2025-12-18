import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

/**
 * Error Boundary component that catches JavaScript errors in child components.
 *
 * This prevents the entire UI from freezing when an error occurs in a component.
 * Instead, it shows a helpful error message with options to retry or reload.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    }
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI.
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    // Log error to console for debugging
    console.error('Error Boundary caught an error:', error, errorInfo)

    // Update state with error details
    this.setState({
      error: error,
      errorInfo: errorInfo
    })

    // You could also log the error to an error reporting service here
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null
    })

    // Call onReset callback if provided
    if (this.props.onReset) {
      this.props.onReset()
    }
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback UI can be provided via props
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleReset)
      }

      // Default error UI
      return (
        <div className="flex items-center justify-center min-h-screen bg-background p-4">
          <div className="bg-surface-elevated border-2 border-error rounded-xl p-8 max-w-2xl w-full">
            <div className="flex items-start gap-4 mb-6">
              <div className="p-3 bg-error/10 rounded-lg">
                <AlertTriangle className="text-error" size={32} />
              </div>
              <div className="flex-1">
                <h2 className="text-2xl font-bold text-error mb-2">
                  {this.props.title || 'Something went wrong'}
                </h2>
                <p className="text-text-secondary">
                  {this.props.message || 'An unexpected error occurred in this component. The rest of the application should still work.'}
                </p>
              </div>
            </div>

            {this.state.error && (
              <div className="mb-6 bg-surface border border-border rounded-lg p-4">
                <h3 className="text-sm font-semibold text-text-secondary mb-2">Error Details:</h3>
                <p className="text-sm text-error font-mono mb-2">{this.state.error.toString()}</p>
                {this.state.errorInfo && this.state.errorInfo.componentStack && (
                  <details className="mt-2">
                    <summary className="text-xs text-text-tertiary cursor-pointer hover:text-text-secondary">
                      Stack Trace
                    </summary>
                    <pre className="text-xs text-text-tertiary mt-2 overflow-auto max-h-40 p-2 bg-background rounded">
                      {this.state.errorInfo.componentStack}
                    </pre>
                  </details>
                )}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={this.handleReset}
                className="btn btn-primary flex items-center gap-2"
              >
                <RefreshCw size={16} />
                <span>Try Again</span>
              </button>
              <button
                onClick={this.handleReload}
                className="btn btn-secondary"
              >
                Reload Page
              </button>
            </div>

            {this.props.showSupport && (
              <p className="text-xs text-text-tertiary mt-4">
                If this problem persists, please report it with the error details above.
              </p>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
