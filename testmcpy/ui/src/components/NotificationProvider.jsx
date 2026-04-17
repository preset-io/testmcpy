import React, { createContext, useContext, useState, useCallback, useRef } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

const NotificationContext = createContext()

let toastIdCounter = 0

const TOAST_ICONS = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const TOAST_STYLES = {
  success: 'bg-success/10 border-success/30 text-success',
  error: 'bg-error/10 border-error/30 text-error',
  warning: 'bg-warning/10 border-warning/30 text-warning',
  info: 'bg-info/10 border-info/30 text-info',
}

function Toast({ toast, onDismiss }) {
  const Icon = TOAST_ICONS[toast.type] || Info
  const style = TOAST_STYLES[toast.type] || TOAST_STYLES.info

  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-lg border shadow-medium animate-slide-in max-w-sm ${style} bg-surface`}
      role="alert"
    >
      <Icon size={18} className="flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className="text-sm font-semibold text-text-primary">{toast.title}</p>
        )}
        <p className="text-sm text-text-secondary">{toast.message}</p>
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 p-0.5 rounded hover:bg-surface-hover text-text-tertiary hover:text-text-primary transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  )
}

export function NotificationProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef({})

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    if (timersRef.current[id]) {
      clearTimeout(timersRef.current[id])
      delete timersRef.current[id]
    }
  }, [])

  const notify = useCallback(({ type = 'info', title, message, duration = 5000 }) => {
    const id = ++toastIdCounter
    const toast = { id, type, title, message }
    setToasts(prev => [...prev.slice(-4), toast]) // Keep max 5 toasts

    if (duration > 0) {
      timersRef.current[id] = setTimeout(() => {
        dismiss(id)
      }, duration)
    }

    return id
  }, [dismiss])

  const success = useCallback((message, title) => {
    return notify({ type: 'success', message, title })
  }, [notify])

  const error = useCallback((message, title) => {
    return notify({ type: 'error', message, title, duration: 8000 })
  }, [notify])

  const warning = useCallback((message, title) => {
    return notify({ type: 'warning', message, title })
  }, [notify])

  const info = useCallback((message, title) => {
    return notify({ type: 'info', message, title })
  }, [notify])

  return (
    <NotificationContext.Provider value={{ notify, success, error, warning, info, dismiss }}>
      {children}
      {/* Toast container - bottom right */}
      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {toasts.map(toast => (
            <Toast key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </NotificationContext.Provider>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotification must be used within a NotificationProvider')
  }
  return context
}
