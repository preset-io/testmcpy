import { useTheme } from '../contexts/ThemeContext'

/**
 * Returns theme strings for Monaco editor and ReactJson viewer
 * based on the current app theme.
 */
export function useEditorTheme() {
  const { resolvedTheme } = useTheme()
  return {
    monacoTheme: resolvedTheme === 'dark' ? 'vs-dark' : 'light',
    jsonTheme: resolvedTheme === 'dark' ? 'monokai' : 'rjv-default',
  }
}
