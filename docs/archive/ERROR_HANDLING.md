# Never-Freeze Error Handling Implementation

This document describes the comprehensive error handling system implemented across testmcpy to prevent UI freezing and provide actionable error messages.

## Overview

The error handling system prevents the application from freezing by:

1. **Timeout Protection**: All async operations have configurable timeouts (default: 30s)
2. **Graceful Degradation**: Errors return result objects instead of raising exceptions where possible
3. **Exponential Backoff**: Automatic retry with exponential backoff for transient failures
4. **Resource Cleanup**: Proper cleanup of resources even when errors occur
5. **Actionable Messages**: Clear error messages with suggestions for recovery

## Components

### 1. MCP Client (`testmcpy/src/mcp_client.py`)

#### New Error Types

```python
class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass

class MCPTimeoutError(MCPError):
    """Exception raised when an MCP operation times out."""
    pass

class MCPConnectionError(MCPError):
    """Exception raised when unable to connect to MCP service."""
    pass
```

#### Retry with Backoff

```python
async def retry_with_backoff(func, *args, max_retries=3, timeout=30.0, **kwargs):
    """
    Retry an async function with exponential backoff.

    - Default timeout: 30 seconds
    - Max retries: 3
    - Backoff factor: 2.0 (1s, 2s, 4s)
    """
```

#### Key Changes

- **`initialize(timeout=30.0)`**: Initializes MCP connection with timeout protection
  - Wraps authentication setup with timeout
  - Wraps client connection with timeout
  - Attempts ping but continues if ping fails
  - Cleans up partial connections on failure

- **`list_tools(timeout=30.0)`**: Lists tools with timeout
  - Caches results for performance
  - Continues processing even if individual tools fail to parse
  - Returns empty list on total failure

- **`call_tool(timeout=30.0)`**: Executes tool calls with timeout
  - **Never raises exceptions** - returns `MCPToolResult` with `is_error=True` instead
  - This ensures UI never freezes on tool failures
  - Returns actionable error messages

- **`close()`**: Safely closes connections
  - Never raises exceptions
  - Has 5-second timeout on close operations
  - Clears cache on close

### 2. API Server (`testmcpy/server/api.py` + `testmcpy/error_handlers.py`)

#### Global Exception Handler

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Catches all unhandled exceptions and returns helpful HTTP responses.

    Returns:
    - 504 for timeout errors
    - 503 for connection errors
    - 500 for general MCP errors
    - Includes error_type and suggestion fields
    """
```

#### Benefits

- **No Server Crashes**: Catches all unhandled exceptions
- **Helpful Messages**: Returns structured error responses with suggestions
- **Logging**: Logs full tracebacks for debugging
- **Client-Friendly**: Returns appropriate HTTP status codes

### 3. TUI Application (`testmcpy/tui/app.py`)

#### ErrorModal Screen

```python
class ErrorModal(ModalScreen):
    """Modal screen to display error messages without crashing the TUI."""
```

Features:
- Non-blocking error display
- Keyboard shortcuts (ESC/Enter to close)
- Shows full error details with stack trace
- Allows app to continue running

#### Error-Wrapped Actions

All navigation and screen actions are wrapped in try/catch:

```python
def on_button_pressed(self, event: Button.Pressed) -> None:
    try:
        # Navigate to screen
    except Exception as e:
        self.app.push_screen(ErrorModal(error_msg))
```

#### Global Exception Handler

```python
def handle_exception(self, exc: Exception) -> None:
    """
    Prevents TUI from crashing on unhandled exceptions.
    Shows error modal instead.
    """
```

### 4. React UI Components

#### ErrorBoundary Component (`ui/src/components/ErrorBoundary.jsx`)

React Error Boundary that catches JavaScript errors in child components:

```jsx
<ErrorBoundary
  title="Custom Title"
  message="Custom error message"
  onReset={() => {/* Reset handler */}}
  showSupport={true}
>
  <YourComponent />
</ErrorBoundary>
```

Features:
- Catches rendering errors in child components
- Shows helpful error UI with stack trace
- Provides "Try Again" and "Reload Page" buttons
- Prevents entire app from crashing

#### useSafeFetch Hook (`ui/src/hooks/useSafeFetch.js`)

Custom hook for safe API calls:

```javascript
const { data, error, loading, execute, reset } = useSafeFetch()

// Use it
try {
  const result = await execute('/api/endpoint', { method: 'POST' }, 30000)
} catch (err) {
  // Error is already set in state
}
```

Features:
- Built-in timeout protection (default: 30s)
- Automatic error parsing from API responses
- Loading states
- Includes suggestions from server errors
- Never freezes on network issues

#### ErrorAlert Component (`ui/src/components/ErrorAlert.jsx`)

Inline error display with retry:

```jsx
<ErrorAlert
  error={errorMessage}
  onRetry={() => retryOperation()}
  onDismiss={() => setError(null)}
  title="Operation Failed"
/>
```

Features:
- Non-blocking inline error display
- Optional retry button
- Optional dismiss button
- Supports multiline error messages

## Usage Examples

### Backend: Making a Safe MCP Call

```python
from testmcpy.src.mcp_client import MCPClient, MCPToolCall

async def safe_mcp_operation():
    client = MCPClient(base_url="https://api.example.com/mcp")

    try:
        # Initialize with timeout
        await client.initialize(timeout=10.0)

        # List tools with timeout
        tools = await client.list_tools(timeout=5.0)

        # Call tool - this never raises exceptions
        result = await client.call_tool(
            MCPToolCall(name="my_tool", arguments={"param": "value"}),
            timeout=30.0
        )

        if result.is_error:
            print(f"Tool call failed: {result.error_message}")
        else:
            print(f"Success: {result.content}")

    finally:
        # Always safe to close
        await client.close()
```

### Frontend: Using Error Boundary

```jsx
import ErrorBoundary from './components/ErrorBoundary'
import MCPExplorer from './pages/MCPExplorer'

function App() {
  return (
    <ErrorBoundary title="Explorer Error">
      <MCPExplorer />
    </ErrorBoundary>
  )
}
```

### Frontend: Using Safe Fetch

```javascript
import { useSafeFetch } from './hooks/useSafeFetch'
import ErrorAlert from './components/ErrorAlert'

function MyComponent() {
  const { data, error, loading, execute } = useSafeFetch()

  const loadData = async () => {
    try {
      await execute('/api/data', {}, 30000)
    } catch (err) {
      // Error is already in state, just handle if needed
    }
  }

  return (
    <div>
      {error && <ErrorAlert error={error} onRetry={loadData} />}
      {loading && <div>Loading...</div>}
      {data && <div>{JSON.stringify(data)}</div>}
    </div>
  )
}
```

## Error Message Patterns

### Good Error Messages

Error messages should be:

1. **Descriptive**: What went wrong?
2. **Actionable**: What can the user do?
3. **Contextual**: Where did it happen?

Examples:

```
Good:
"Tool call 'get_data' timed out after 30s. The MCP service may be slow. Try again or check your connection."

Bad:
"Timeout error"
```

```
Good:
"Cannot connect to MCP service at https://api.example.com/mcp. Verify the URL and authentication settings."

Bad:
"Connection failed"
```

## Testing Error Handling

### Simulating Timeouts

```python
import asyncio

async def test_timeout():
    client = MCPClient("https://slow-service.com")
    try:
        # This will timeout after 1 second
        await client.initialize(timeout=1.0)
    except MCPTimeoutError as e:
        print(f"Caught timeout: {e}")
```

### Simulating Network Errors

```javascript
// In React component
const { execute } = useSafeFetch()

try {
  await execute('http://localhost:9999/nonexistent', {}, 5000)
} catch (err) {
  // Should get "Network error: Unable to connect to the server"
}
```

## Key Principles

1. **Never Block**: Use timeouts on all async operations
2. **Never Crash**: Catch exceptions and return error objects
3. **Always Clean Up**: Use try/finally for resource cleanup
4. **Be Helpful**: Provide actionable error messages
5. **Log Everything**: Log full errors server-side for debugging
6. **Fail Gracefully**: Allow partial functionality when possible

## Inspector Issues Addressed

- **Issue #552**: UI no longer freezes on 500 errors (global exception handler)
- **Issue #623**: No more hanging on dependency issues (timeout protection)
- **Issue #698**: Error messages now include suggestions and recovery options

## Future Improvements

1. **Metrics**: Add error rate tracking
2. **Sentry Integration**: Send errors to error tracking service
3. **User Feedback**: Add "Report Issue" button to error modals
4. **Retry Policies**: Make retry configuration more flexible
5. **Circuit Breaker**: Stop retrying after repeated failures
