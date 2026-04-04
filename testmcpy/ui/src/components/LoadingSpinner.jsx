import React from 'react'

/**
 * Reusable loading spinner component with customizable size and text
 */
export const LoadingSpinner = ({ size = 'md', text = 'Loading...', className = '' }) => {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-2',
    lg: 'w-12 h-12 border-3',
    xl: 'w-16 h-16 border-4'
  }

  const textSizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
    xl: 'text-lg'
  }

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className="flex flex-col items-center gap-3">
        <div
          className={`${sizeClasses[size]} border-primary border-t-transparent rounded-full animate-spin`}
          role="status"
          aria-label="Loading"
        />
        {text && (
          <div className={`${textSizeClasses[size]} text-text-secondary`}>
            {text}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Inline loading spinner (smaller, for buttons or inline use)
 */
export const InlineSpinner = ({ className = '' }) => {
  return (
    <div
      className={`w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin ${className}`}
      role="status"
      aria-label="Loading"
    />
  )
}

/**
 * Full-page loading overlay
 */
export const LoadingOverlay = ({ text = 'Loading...', blur = true }) => {
  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center ${blur ? 'bg-black/50 backdrop-blur-sm' : 'bg-black/30'}`}>
      <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl p-8">
        <LoadingSpinner size="lg" text={text} />
      </div>
    </div>
  )
}

export default LoadingSpinner
