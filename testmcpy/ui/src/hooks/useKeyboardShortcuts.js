import { useEffect, useCallback } from 'react'

/**
 * Custom hook for handling keyboard shortcuts
 *
 * @param {Object} shortcuts - Object mapping shortcut keys to handlers
 *   Keys are in format: "ctrl+enter", "escape", "ctrl+shift+s", etc.
 * @param {boolean} enabled - Whether shortcuts are enabled (default: true)
 * @param {HTMLElement} targetElement - Element to listen on (default: document)
 *
 * Example usage:
 * useKeyboardShortcuts({
 *   'ctrl+enter': () => handleSubmit(),
 *   'escape': () => closeModal(),
 *   'ctrl+k': () => openSearch(),
 * })
 */
export function useKeyboardShortcuts(shortcuts, enabled = true, targetElement = null) {
  const handleKeyDown = useCallback((event) => {
    if (!enabled) return

    // Build the shortcut key string
    const parts = []
    if (event.ctrlKey || event.metaKey) parts.push('ctrl')
    if (event.shiftKey) parts.push('shift')
    if (event.altKey) parts.push('alt')

    // Handle special keys
    let key = event.key.toLowerCase()
    if (key === ' ') key = 'space'
    if (key === 'enter') key = 'enter'
    if (key === 'escape') key = 'escape'
    if (key === 'arrowup') key = 'up'
    if (key === 'arrowdown') key = 'down'
    if (key === 'arrowleft') key = 'left'
    if (key === 'arrowright') key = 'right'

    // Don't include modifier keys as the main key
    if (!['control', 'shift', 'alt', 'meta'].includes(key)) {
      parts.push(key)
    }

    const shortcutKey = parts.join('+')

    // Check if we have a handler for this shortcut
    const handler = shortcuts[shortcutKey]
    if (handler) {
      // Don't prevent default for all shortcuts - let handler decide
      handler(event)
    }
  }, [shortcuts, enabled])

  useEffect(() => {
    const element = targetElement || document
    element.addEventListener('keydown', handleKeyDown)
    return () => {
      element.removeEventListener('keydown', handleKeyDown)
    }
  }, [handleKeyDown, targetElement])
}

/**
 * Hook for managing focus trap in modals
 *
 * @param {React.RefObject} containerRef - Ref to the modal container
 * @param {boolean} isOpen - Whether the modal is open
 */
export function useFocusTrap(containerRef, isOpen) {
  useEffect(() => {
    if (!isOpen || !containerRef.current) return

    const container = containerRef.current
    const focusableElements = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    const firstElement = focusableElements[0]
    const lastElement = focusableElements[focusableElements.length - 1]

    // Focus first element when modal opens
    if (firstElement) {
      firstElement.focus()
    }

    const handleKeyDown = (event) => {
      if (event.key !== 'Tab') return

      if (event.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          event.preventDefault()
          lastElement?.focus()
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          event.preventDefault()
          firstElement?.focus()
        }
      }
    }

    container.addEventListener('keydown', handleKeyDown)
    return () => {
      container.removeEventListener('keydown', handleKeyDown)
    }
  }, [containerRef, isOpen])
}

/**
 * Hook for announcing messages to screen readers
 *
 * @returns {function} announce - Function to announce a message
 */
export function useAnnounce() {
  const announce = useCallback((message, priority = 'polite') => {
    // Create or get the announcement region
    let region = document.getElementById('sr-announcements')
    if (!region) {
      region = document.createElement('div')
      region.id = 'sr-announcements'
      region.setAttribute('role', 'status')
      region.setAttribute('aria-live', priority)
      region.setAttribute('aria-atomic', 'true')
      region.style.cssText = `
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      `
      document.body.appendChild(region)
    }

    // Clear and set the message (needs to change for screen readers to announce)
    region.textContent = ''
    setTimeout(() => {
      region.textContent = message
    }, 50)
  }, [])

  return announce
}

/**
 * Common keyboard shortcuts configuration
 */
export const KEYBOARD_SHORTCUTS = {
  // Chat
  SEND_MESSAGE: 'ctrl+enter',
  CLEAR_CHAT: 'ctrl+shift+c',

  // Navigation
  CLOSE_MODAL: 'escape',
  FOCUS_SEARCH: 'ctrl+k',

  // Tests
  RUN_TESTS: 'ctrl+shift+t',
  SAVE_FILE: 'ctrl+s',

  // General
  HELP: 'ctrl+/',
}

export default useKeyboardShortcuts
