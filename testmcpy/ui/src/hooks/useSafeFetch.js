import { useState, useCallback } from 'react'

/**
 * Custom hook for making safe fetch requests with timeout and error handling.
 *
 * This hook ensures that fetch requests never freeze the UI by:
 * - Adding timeout protection (default 30s)
 * - Catching and handling all errors gracefully
 * - Providing loading states
 * - Returning actionable error messages
 *
 * @param {number} defaultTimeout - Default timeout in milliseconds (default: 30000)
 * @returns {Object} - { data, error, loading, execute }
 */
export function useSafeFetch(defaultTimeout = 30000, defaultRetries = 3) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const execute = useCallback(async (url, options = {}, timeout = defaultTimeout, retries = defaultRetries) => {
    setLoading(true)
    setError(null)
    setData(null)

    // Retry loop with exponential backoff
    for (let attempt = 0; attempt < retries; attempt++) {
      // Create abort controller for timeout
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeout)

      try {
        const response = await fetch(url, {
          ...options,
          signal: controller.signal
        })

        clearTimeout(timeoutId)

        // Handle HTTP errors
        if (!response.ok) {
          let errorDetail = `HTTP ${response.status}`

          try {
            const errorData = await response.json()
            if (errorData.detail) {
              errorDetail = errorData.detail
            } else if (errorData.error) {
              errorDetail = errorData.error
            }

            // Include suggestions if available
            if (errorData.suggestion) {
              errorDetail += `\n\nSuggestion: ${errorData.suggestion}`
            }
          } catch (e) {
            // Couldn't parse error as JSON, use status text
            errorDetail = response.statusText || errorDetail
          }

          throw new Error(errorDetail)
        }

        // Parse response
        const contentType = response.headers.get('content-type')
        let result

        if (contentType && contentType.includes('application/json')) {
          result = await response.json()
        } else {
          result = await response.text()
        }

        setData(result)
        setLoading(false)
        return result

      } catch (err) {
        clearTimeout(timeoutId)

        const isLastAttempt = attempt === retries - 1
        let errorMessage

        if (err.name === 'AbortError') {
          errorMessage = `Request timed out after ${timeout / 1000} seconds. The server may be slow or unresponsive.`
        } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
          errorMessage = 'Network error: Unable to connect to the server. Check your connection and try again.'
        } else {
          errorMessage = err.message
        }

        // If this is the last attempt, set error and throw
        if (isLastAttempt) {
          setError(errorMessage)
          setLoading(false)
          throw new Error(errorMessage)
        }

        // Otherwise, wait and retry with exponential backoff
        const delay = 1000 * Math.pow(2, attempt)
        console.log(`Retry ${attempt + 1}/${retries} for ${url} in ${delay}ms...`)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }, [defaultTimeout, defaultRetries])

  const reset = useCallback(() => {
    setData(null)
    setError(null)
    setLoading(false)
  }, [])

  return {
    data,
    error,
    loading,
    execute,
    reset
  }
}

/**
 * Simple utility function for one-off safe fetch calls.
 *
 * @param {string} url - URL to fetch
 * @param {Object} options - Fetch options
 * @param {number} timeout - Timeout in milliseconds (default: 30000)
 * @returns {Promise} - Promise that resolves to response data or rejects with error
 */
export async function safeFetch(url, options = {}, timeout = 30000) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      let errorDetail = `HTTP ${response.status}`

      try {
        const errorData = await response.json()
        if (errorData.detail) {
          errorDetail = errorData.detail
        } else if (errorData.error) {
          errorDetail = errorData.error
        }

        if (errorData.suggestion) {
          errorDetail += `\n\nSuggestion: ${errorData.suggestion}`
        }
      } catch (e) {
        errorDetail = response.statusText || errorDetail
      }

      throw new Error(errorDetail)
    }

    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      return await response.json()
    } else {
      return await response.text()
    }

  } catch (err) {
    clearTimeout(timeoutId)

    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeout / 1000} seconds`)
    } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      throw new Error('Network error: Unable to connect to the server')
    } else {
      throw err
    }
  }
}

export default useSafeFetch
