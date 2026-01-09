# MCPClient Authentication Guide

The `MCPClient` class supports multiple authentication types that can be passed as parameters to the constructor. This provides flexibility for different authentication scenarios while maintaining backward compatibility with configuration-based authentication.

## Authentication Types

The `MCPClient` supports the following authentication types:

1. **Bearer Token** - Direct token authentication
2. **JWT** - Dynamic JWT token fetched from an API
3. **OAuth** - OAuth 2.0 client credentials flow
4. **None** - No authentication

## Usage

### Constructor Signature

```python
MCPClient(base_url: str | None = None, auth: dict[str, Any] | None = None)
```

**Parameters:**
- `base_url`: MCP service URL (optional, falls back to config)
- `auth`: Authentication configuration dictionary (optional, falls back to config)

## Authentication Configuration

### 1. Bearer Token Authentication

Use a static bearer token for authentication.

```python
auth = {
    "type": "bearer",
    "token": "your-bearer-token-here"
}

async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

**Required Fields:**
- `type`: Must be "bearer"
- `token`: Your bearer token string

### 2. JWT Authentication

Dynamically fetch a JWT token from an API endpoint.

```python
auth = {
    "type": "jwt",
    "api_url": "https://api.example.com/auth/token",
    "api_token": "your-api-token",
    "api_secret": "your-api-secret"
}

async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

**Required Fields:**
- `type`: Must be "jwt"
- `api_url`: JWT API endpoint URL
- `api_token`: API token for authentication
- `api_secret`: API secret for authentication

**How it works:**
1. Makes a POST request to `api_url` with credentials
2. Extracts the access token from the response
3. Uses the access token as a bearer token for MCP requests

### 3. OAuth Authentication

Use OAuth 2.0 client credentials flow.

```python
auth = {
    "type": "oauth",
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "token_url": "https://oauth.example.com/token",
    "scopes": ["read", "write"]  # Optional
}

async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

**Required Fields:**
- `type`: Must be "oauth"
- `client_id`: OAuth client ID
- `client_secret`: OAuth client secret
- `token_url`: OAuth token endpoint URL

**Optional Fields:**
- `scopes`: List of OAuth scopes (default: [])

**How it works:**
1. Makes a POST request to `token_url` with client credentials
2. Receives an access token
3. Uses the access token as a bearer token for MCP requests

### 4. No Authentication

Explicitly specify no authentication.

```python
auth = {
    "type": "none"
}

async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
    tools = await client.list_tools()
```

Alternatively, simply omit the `auth` parameter:

```python
async with MCPClient(base_url="http://localhost:5008/mcp") as client:
    tools = await client.list_tools()
```

## Configuration Fallback

When the `auth` parameter is not provided, `MCPClient` falls back to configuration-based authentication:

1. Checks for JWT configuration in config:
   - `MCP_AUTH_API_URL`
   - `MCP_AUTH_API_TOKEN`
   - `MCP_AUTH_API_SECRET`

2. Falls back to static token from config:
   - `MCP_AUTH_TOKEN`
   - `SUPERSET_MCP_TOKEN` (legacy)

3. No authentication if none configured

```python
# Uses config-based authentication
async with MCPClient(base_url="http://localhost:5008/mcp") as client:
    tools = await client.list_tools()
```

## Using with MCP Profiles

You can load authentication from MCP profiles and convert it to the auth parameter format:

```python
from testmcpy.mcp_profiles import load_profile

# Load profile
profile = load_profile("production")

if profile and profile.mcps:
    mcp = profile.mcps[0]

    # Convert AuthConfig to dict using helper method
    auth = mcp.auth.to_dict()

    async with MCPClient(base_url=mcp.mcp_url, auth=auth) as client:
        tools = await client.list_tools()
```

## Error Handling

The authentication system provides clear error messages for common issues:

### Missing Required Fields

```python
# Missing token field
auth = {"type": "bearer"}  # Error: Bearer auth requires 'token' field

# Missing JWT fields
auth = {
    "type": "jwt",
    "api_url": "https://api.example.com"
    # Missing api_token and api_secret
}
# Error: JWT auth requires 'api_url', 'api_token', and 'api_secret' fields
```

### Unknown Auth Type

```python
auth = {"type": "invalid"}
# Error: Unknown auth type: invalid
```

### Token Fetch Failures

```python
# JWT or OAuth token fetch failures
# Error: Failed to fetch JWT token: HTTP 401 Unauthorized
# Error: OAuth token fetch error: Connection timeout
```

## Logging

The authentication system logs helpful information to stderr:

```
[Auth] Using bearer token from parameter
[Auth] Token: eyJhbGciOiJIUzI1NiI...12345678

[Auth] Using dynamic JWT authentication from parameter
[Auth] Fetching JWT token from: https://api.example.com/auth/token
[Auth] JWT token fetched successfully (length: 250)

[Auth] Using OAuth authentication from parameter
[Auth] Fetching OAuth token from: https://oauth.example.com/token
[Auth] OAuth token fetched successfully (length: 200)

[Auth] No authentication (explicit)

[Auth] Using dynamic JWT authentication from config
[Auth] Using static bearer token from config
```

## Complete Examples

See `/examples/auth_examples.py` for complete working examples of all authentication types.

## Migration Guide

### From Config-Based to Parameter-Based

**Before (config-based):**
```python
# Requires MCP_AUTH_TOKEN in environment or config files
async with MCPClient() as client:
    ...
```

**After (parameter-based):**
```python
# Explicit auth parameter
auth = {"type": "bearer", "token": "my-token"}
async with MCPClient(auth=auth) as client:
    ...
```

### From Profile-Based

**Before (profile in config):**
```python
# Profile loaded from config system
async with MCPClient() as client:
    ...
```

**After (explicit profile loading):**
```python
from testmcpy.mcp_profiles import load_profile

profile = load_profile("my-profile")
mcp = profile.mcps[0]
auth = mcp.auth.to_dict()

async with MCPClient(base_url=mcp.mcp_url, auth=auth) as client:
    ...
```

## Best Practices

1. **Use parameter-based auth for programmatic control**: When you need to dynamically switch between different authentication methods or MCP services.

2. **Use config-based auth for simplicity**: When you have a single MCP service with static configuration.

3. **Use profiles for multiple environments**: When you need to manage multiple MCP services or environments (dev, staging, prod).

4. **Secure your credentials**: Never hardcode tokens or secrets in your code. Use environment variables or secure config files.

5. **Handle errors gracefully**: Always wrap MCP client usage in try-catch blocks to handle authentication failures.

```python
try:
    async with MCPClient(auth=auth) as client:
        tools = await client.list_tools()
except MCPError as e:
    print(f"Authentication or connection failed: {e}")
```
