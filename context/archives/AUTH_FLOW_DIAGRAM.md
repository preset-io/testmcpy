# MCPClient Authentication Flow Diagram

## Authentication Setup Flow

```
MCPClient.__init__(base_url, auth)
    |
    ├── Store auth_config parameter
    ├── Store base_url
    └── Set auth = None (will be set in initialize())

MCPClient.initialize()
    |
    ├── Call _setup_auth()
    |   |
    |   ├── Check if auth_config provided?
    |   |   |
    |   |   YES ──> Process auth parameter
    |   |   |       |
    |   |   |       ├── type == "bearer" ──> Return BearerAuth(token)
    |   |   |       |
    |   |   |       ├── type == "jwt" ──> Call _fetch_jwt_token()
    |   |   |       |                       |
    |   |   |       |                       ├── POST to api_url with credentials
    |   |   |       |                       ├── Extract access_token from response
    |   |   |       |                       └── Return BearerAuth(access_token)
    |   |   |       |
    |   |   |       ├── type == "oauth" ──> Call _fetch_oauth_token()
    |   |   |       |                         |
    |   |   |       |                         ├── POST to token_url (client credentials)
    |   |   |       |                         ├── Extract access_token from response
    |   |   |       |                         └── Return BearerAuth(access_token)
    |   |   |       |
    |   |   |       ├── type == "none" ──> Return None
    |   |   |       |
    |   |   |       └── type == unknown ──> Raise MCPError
    |   |   |
    |   |   NO ──> Fall back to config
    |   |          |
    |   |          ├── Check for dynamic JWT in config
    |   |          |   (MCP_AUTH_API_URL, MCP_AUTH_API_TOKEN, MCP_AUTH_API_SECRET)
    |   |          |   YES ──> Call _fetch_jwt_token() with config values
    |   |          |
    |   |          ├── Check for static token in config
    |   |          |   (MCP_AUTH_TOKEN or SUPERSET_MCP_TOKEN)
    |   |          |   YES ──> Return BearerAuth(token)
    |   |          |
    |   |          └── NO auth configured ──> Return None
    |   |
    |   └── Return BearerAuth or None
    |
    ├── Set self.auth = result from _setup_auth()
    ├── Create FastMCP Client with auth
    └── Test connection
```

## Auth Parameter Priority

```
1. HIGHEST PRIORITY: auth parameter to __init__()
   ↓ (if not provided)
2. Dynamic JWT from config (MCP_AUTH_API_URL, etc.)
   ↓ (if not configured)
3. Static token from config (MCP_AUTH_TOKEN)
   ↓ (if not configured)
4. LOWEST PRIORITY: No authentication
```

## JWT Token Fetch Flow

```
_fetch_jwt_token(api_url, api_token, api_secret)
    |
    ├── Create async HTTP client
    ├── POST to api_url
    |   Headers: Content-Type: application/json
    |   Body: {"name": api_token, "secret": api_secret}
    |
    ├── Receive response
    |   |
    |   ├── Check for {"payload": {"access_token": "..."}}
    |   ├── OR check for {"access_token": "..."}
    |   └── Extract token
    |
    ├── Log success
    └── Return access_token string
```

## OAuth Token Fetch Flow

```
_fetch_oauth_token(client_id, client_secret, token_url, scopes)
    |
    ├── Create async HTTP client
    ├── POST to token_url
    |   Headers: Content-Type: application/x-www-form-urlencoded
    |   Body: grant_type=client_credentials
    |         client_id=...
    |         client_secret=...
    |         scope=... (space-separated scopes)
    |
    ├── Receive response
    |   └── Extract {"access_token": "..."}
    |
    ├── Log success
    └── Return access_token string
```

## Usage Patterns

### Pattern 1: Direct Auth Parameter

```python
auth = {"type": "bearer", "token": "..."}
client = MCPClient(base_url="...", auth=auth)
    ↓
auth parameter used directly
    ↓
BearerAuth created with token
```

### Pattern 2: Profile-Based Auth

```python
profile = load_profile("production")
mcp = profile.mcps[0]
auth = mcp.auth.to_dict()
client = MCPClient(base_url=mcp.mcp_url, auth=auth)
    ↓
AuthConfig converted to dict
    ↓
auth parameter used
    ↓
BearerAuth or token fetch as needed
```

### Pattern 3: Config Fallback

```python
client = MCPClient()
    ↓
No auth parameter
    ↓
Check config for JWT settings
    ↓
Check config for static token
    ↓
BearerAuth created from config or None
```

## Error Handling

```
MCPClient.initialize()
    |
    └── _setup_auth()
        |
        ├── Missing required field ──> Raise MCPError with helpful message
        |
        ├── Unknown auth type ──> Raise MCPError("Unknown auth type: ...")
        |
        ├── _fetch_jwt_token() fails ──> Raise MCPError("Failed to fetch JWT token: ...")
        |
        └── _fetch_oauth_token() fails ──> Raise MCPError("Failed to fetch OAuth token: ...")
```

## Logging Output

```
Parameter-based auth:
  [Auth] Using bearer token from parameter
  [Auth] Token: eyJhbGciOiJIUzI1NiI...12345678

  [Auth] Using dynamic JWT authentication from parameter
  [Auth] Fetching JWT token from: https://api.example.com/auth/token
  [Auth] JWT token fetched successfully (length: 250)

  [Auth] Using OAuth authentication from parameter
  [Auth] Fetching OAuth token from: https://oauth.example.com/token
  [Auth] OAuth token fetched successfully (length: 200)

Config-based auth:
  [Auth] Using dynamic JWT authentication from config
  [Auth] Fetching JWT token from: https://api.example.com/auth/token
  [Auth] JWT token fetched successfully (length: 250)

  [Auth] Using static bearer token from config
  [Auth] Token: eyJhbGciOiJIUzI1NiI...12345678

No auth:
  [Auth] No authentication (explicit)
  [Auth] No authentication configured
```
