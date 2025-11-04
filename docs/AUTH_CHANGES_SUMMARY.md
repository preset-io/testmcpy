# MCPClient Authentication Changes Summary

## Overview

The `MCPClient` class has been updated to support all authentication types (bearer, JWT, OAuth) passed as parameters to the constructor. This provides greater flexibility and control over authentication while maintaining backward compatibility with existing configuration-based authentication.

## Changes Made

### 1. Updated MCPClient Constructor

**File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/src/mcp_client.py`

**Before:**
```python
def __init__(self, base_url: str | None = None):
    self.base_url = base_url or get_config().mcp_url
    self.client = None
    self._tools_cache = None
    self.auth = self._load_auth_token()
```

**After:**
```python
def __init__(self, base_url: str | None = None, auth: dict[str, Any] | None = None):
    self.base_url = base_url or get_config().mcp_url
    self.auth_config = auth  # Store the auth config
    self.client = None
    self._tools_cache = None
    self.auth: BearerAuth | None = None  # Will be set in initialize()
```

**Changes:**
- Added `auth` parameter to accept authentication configuration
- Changed `self.auth` to be set during initialization instead of construction
- Stored auth config in `self.auth_config` for later processing

### 2. Implemented JWT Token Fetching

**New Method:** `async def _fetch_jwt_token()`

**Features:**
- Fetches JWT token from API endpoint
- Supports both `{"payload": {"access_token": "..."}}` and `{"access_token": "..."}` response formats
- Proper error handling with MCPError exceptions
- Logging of token fetch operations

**Parameters:**
- `api_url`: JWT API endpoint URL
- `api_token`: API token for authentication
- `api_secret`: API secret for authentication

### 3. Implemented OAuth Token Fetching

**New Method:** `async def _fetch_oauth_token()`

**Features:**
- Implements OAuth 2.0 client credentials flow
- Supports optional scopes
- Proper error handling with MCPError exceptions
- Logging of OAuth operations

**Parameters:**
- `client_id`: OAuth client ID
- `client_secret`: OAuth client secret
- `token_url`: OAuth token endpoint URL
- `scopes`: Optional list of OAuth scopes

### 4. Replaced _load_auth_token() with _setup_auth()

**Old Method:** `def _load_auth_token()` (synchronous)
**New Method:** `async def _setup_auth()` (async)

**Features:**
- Checks for auth parameter first (priority)
- Falls back to config-based authentication if no parameter provided
- Supports all auth types: bearer, jwt, oauth, none
- Comprehensive error messages for missing fields
- Detailed logging of auth method being used

**Auth Type Support:**

1. **Bearer Token:**
   ```python
   {"type": "bearer", "token": "..."}
   ```

2. **JWT:**
   ```python
   {"type": "jwt", "api_url": "...", "api_token": "...", "api_secret": "..."}
   ```

3. **OAuth:**
   ```python
   {"type": "oauth", "client_id": "...", "client_secret": "...", "token_url": "...", "scopes": [...]}
   ```

4. **None:**
   ```python
   {"type": "none"}
   ```

### 5. Updated initialize() Method

**File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/src/mcp_client.py`

**Changes:**
- Added call to `await self._setup_auth()` before creating the FastMCP client
- Sets `self.auth` with the result of authentication setup
- Ensures auth is configured before client connection

**Before:**
```python
async def initialize(self):
    self.client = Client(self.base_url, auth=self.auth)
    await self.client.__aenter__()
```

**After:**
```python
async def initialize(self):
    self.auth = await self._setup_auth()
    self.client = Client(self.base_url, auth=self.auth)
    await self.client.__aenter__()
```

### 6. Added AuthConfig.to_dict() Helper Method

**File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/mcp_profiles.py`

**New Method:** `def to_dict(self) -> dict[str, Any]`

**Purpose:**
- Converts `AuthConfig` dataclass to dictionary format for `MCPClient`
- Makes it easy to use profile-based auth with the new parameter system

**Example:**
```python
profile = load_profile("production")
mcp = profile.mcps[0]
auth = mcp.auth.to_dict()  # Convert to dict
client = MCPClient(base_url=mcp.mcp_url, auth=auth)
```

## New Files Created

### 1. Documentation

**File:** `/Users/amin/github/preset-io/testmcpy/docs/AUTHENTICATION.md`

**Contents:**
- Comprehensive guide to all authentication types
- Usage examples for each auth type
- Configuration fallback behavior
- Error handling guide
- Migration guide from old to new approach
- Best practices

### 2. Examples

**File:** `/Users/amin/github/preset-io/testmcpy/examples/auth_examples.py`

**Contents:**
- Working examples for all authentication types
- Bearer token example
- JWT authentication example
- OAuth authentication example
- No auth example
- Config fallback example
- Profile-based authentication example

### 3. Unit Tests

**File:** `/Users/amin/github/preset-io/testmcpy/tests/test_mcp_client_auth.py`

**Contents:**
- Test for auth parameter storage
- Tests for all auth types (bearer, JWT, OAuth, none)
- Tests for missing required fields
- Tests for unknown auth types
- Tests for token fetch success scenarios
- Tests for config fallback
- Tests for AuthConfig.to_dict() helper

## Backward Compatibility

✅ **Fully backward compatible** - All existing code continues to work:

1. **No auth parameter**: Falls back to config-based authentication
2. **Config-based auth**: Still supported via environment variables and config files
3. **Profile-based auth**: Still supported, now with easier direct usage via `to_dict()`

**Example of backward compatibility:**
```python
# Old code - still works
async with MCPClient() as client:
    tools = await client.list_tools()

# New code - more explicit control
auth = {"type": "bearer", "token": "my-token"}
async with MCPClient(auth=auth) as client:
    tools = await client.list_tools()
```

## Usage Examples

### Bearer Token
```python
auth = {"type": "bearer", "token": "your-token"}
async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

### JWT
```python
auth = {
    "type": "jwt",
    "api_url": "https://api.example.com/auth/token",
    "api_token": "token",
    "api_secret": "secret"
}
async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

### OAuth
```python
auth = {
    "type": "oauth",
    "client_id": "client-id",
    "client_secret": "client-secret",
    "token_url": "https://oauth.example.com/token",
    "scopes": ["read", "write"]
}
async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

### From Profile
```python
from testmcpy.mcp_profiles import load_profile

profile = load_profile("production")
mcp = profile.mcps[0]
auth = mcp.auth.to_dict()

async with MCPClient(base_url=mcp.mcp_url, auth=auth) as client:
    tools = await client.list_tools()
```

## Error Handling

All authentication methods include proper error handling:

- **Missing required fields**: Clear error messages indicating which fields are missing
- **Token fetch failures**: HTTP errors and connection issues are caught and wrapped in MCPError
- **Unknown auth types**: Validation of auth type with helpful error message

## Logging

Comprehensive logging to stderr for debugging:

```
[Auth] Using bearer token from parameter
[Auth] Token: eyJhbGciOiJIUzI1NiI...12345678

[Auth] Using dynamic JWT authentication from parameter
[Auth] Fetching JWT token from: https://api.example.com/auth/token
[Auth] JWT token fetched successfully (length: 250)

[Auth] Using OAuth authentication from parameter
[Auth] Fetching OAuth token from: https://oauth.example.com/token
[Auth] OAuth token fetched successfully (length: 200)
```

## Testing

All functionality is covered by unit tests in:
- `/Users/amin/github/preset-io/testmcpy/tests/test_mcp_client_auth.py`

Run tests with:
```bash
pytest tests/test_mcp_client_auth.py -v
```

## Benefits

1. **Flexibility**: Choose authentication method per client instance
2. **Programmatic Control**: Dynamically switch between auth methods
3. **Better Testing**: Mock different auth scenarios easily
4. **Explicit Configuration**: No hidden behavior from config files
5. **Profile Integration**: Easy integration with MCP profiles
6. **Backward Compatible**: Existing code continues to work

## Migration Path

**No migration required** - Existing code works as-is!

**Optional upgrade** to explicit auth:

**Before:**
```python
# Set MCP_AUTH_TOKEN in environment
export MCP_AUTH_TOKEN="my-token"

# Use client
async with MCPClient() as client:
    ...
```

**After (optional):**
```python
# Explicit auth in code
auth = {"type": "bearer", "token": "my-token"}
async with MCPClient(auth=auth) as client:
    ...
```

## Summary

The MCPClient class now provides:

✅ Parameter-based authentication for all types (bearer, JWT, OAuth)
✅ Dynamic token fetching for JWT and OAuth
✅ Backward compatibility with config-based auth
✅ Comprehensive error handling and logging
✅ Helper methods for profile integration
✅ Complete documentation and examples
✅ Full unit test coverage

All requirements from the original specification have been met!
