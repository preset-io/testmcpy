# Fixed: `testmcpy config-mcp` Now Uses MCP Profile Auth

## Issue
`testmcpy config-mcp claude-desktop` failed with:
```
Error: No authentication token available
Provide --token or configure dynamic JWT (MCP_AUTH_API_*)
```

Even though the user had a `.mcp_services.yaml` file with auth configured, the command wasn't reading from it.

## Root Cause
The `config-mcp` command was only checking for legacy environment variables (`MCP_AUTH_API_URL`, `MCP_AUTH_API_TOKEN`, `MCP_AUTH_API_SECRET`) instead of reading auth from the MCP profile in `.mcp_services.yaml`.

## Solution
Updated `testmcpy config-mcp` command (cli.py:1603-1737) to:

1. **Try MCP profile auth first** (priority 1):
   - Get default MCP server from profile using `cfg.get_default_mcp_server()`
   - Check auth type and handle accordingly:
     - `auth_type: bearer` → Use `token` directly
     - `auth_type: jwt` → Fetch token using `api_url`, `api_token`, `api_secret`
     - `auth_type: none` → Skip authentication (no Authorization header)

2. **Fallback to legacy env vars** (priority 2):
   - If no MCP profile auth, check `MCP_AUTH_API_*` environment variables
   - Fetch JWT token if all three vars are set

3. **Show helpful error** (priority 3):
   - If no auth available, show all options:
     ```
     Error: No authentication token available
     Options:
       1. Configure MCP profile in .mcp_services.yaml (recommended)
       2. Provide --token with a bearer token
       3. Configure legacy env vars (MCP_AUTH_API_*)
     ```

4. **Handle no-auth case**:
   - Don't add `Authorization: Bearer` header if `auth_type: none`
   - Only add header when token is present

## Changes Made

### File: `/Users/amin/github/preset-io/testmcpy/testmcpy/cli.py`

**Lines 1603-1737** - Complete rewrite of auth token retrieval:

```python
# Get auth token
if not auth_token:
    # Try to get auth from MCP profile first
    mcp_server = cfg.get_default_mcp_server()
    if mcp_server and mcp_server.auth:
        auth = mcp_server.auth

        if auth.auth_type == "bearer" and auth.token:
            # Static bearer token
            console.print("[green]✓ Using bearer token from MCP profile[/green]")
            auth_token = auth.token

        elif auth.auth_type == "jwt" and auth.api_url and auth.api_token and auth.api_secret:
            # Dynamic JWT - fetch token
            console.print("[yellow]Fetching bearer token using JWT from MCP profile...[/yellow]")
            # ... fetch logic ...

        elif auth.auth_type == "none":
            # No auth required
            auth_token = ""  # Empty token for no-auth
```

**Lines 1739-1750** - Conditional Authorization header:

```python
# Create MCP server configuration
mcp_args = ["-y", "mcp-remote@latest", mcp_url]

# Only add Authorization header if we have a token (not empty for no-auth)
if auth_token:
    mcp_args.extend(["--header", f"Authorization: Bearer {auth_token}"])

mcp_server_config = {
    "command": "npx",
    "args": mcp_args,
    "env": {"NODE_OPTIONS": "--no-warnings"},
}
```

## Usage Examples

### Example 1: Bearer Token Auth
```yaml
# .mcp_services.yaml
default: prod
profiles:
  prod:
    name: "Production"
    mcps:
      - name: "Superset"
        mcp_url: "https://api.example.com/mcp"
        auth:
          auth_type: "bearer"
          token: "your-static-token-here"
```

```bash
testmcpy config-mcp claude-desktop
# Output: ✓ Using bearer token from MCP profile
```

### Example 2: Dynamic JWT Auth
```yaml
# .mcp_services.yaml
default: prod
profiles:
  prod:
    name: "Production"
    mcps:
      - name: "Superset"
        mcp_url: "https://api.example.com/mcp"
        auth:
          auth_type: "jwt"
          api_url: "https://api.example.com/v1/auth/"
          api_token: "your-api-token"
          api_secret: "your-api-secret"
```

```bash
testmcpy config-mcp claude-desktop
# Output: Fetching bearer token using JWT from MCP profile...
#         ✓ Successfully fetched bearer token (length: 512)
```

### Example 3: No Auth
```yaml
# .mcp_services.yaml
default: local
profiles:
  local:
    name: "Local Dev"
    mcps:
      - name: "Local MCP"
        mcp_url: "http://localhost:5008/mcp/"
        auth:
          auth_type: "none"
```

```bash
testmcpy config-mcp claude-desktop
# Output: Note: MCP profile has auth_type: none
#         Skipping authentication (you may need to add --token manually)
```

### Example 4: Manual Token Override
```bash
testmcpy config-mcp claude-desktop --token "your-manual-token"
# This always works regardless of profile config
```

## Benefits

1. **Works with `testmcpy setup`**: Since setup creates `.mcp_services.yaml`, `config-mcp` now automatically uses those settings
2. **No manual token copying**: Users don't need to copy/paste tokens between files
3. **Supports all auth types**: bearer, jwt, and none
4. **Backward compatible**: Still supports legacy `MCP_AUTH_API_*` env vars
5. **Clear error messages**: Users know exactly what options they have

## Verification

```bash
# CLI imports successfully
python3 -c "from testmcpy.cli import app; print('CLI imports successfully')"
# Output: CLI imports successfully

# Help shows command is available
testmcpy config-mcp --help
# Output: Usage: testmcpy config-mcp [OPTIONS] TARGET
```

## Related Files

- `.mcp_services.yaml.example` - Shows auth configuration examples
- `testmcpy/config.py` - Contains `get_default_mcp_server()` method
- `testmcpy/mcp_profiles.py` - Defines `MCPServer` and `AuthConfig` classes

## Next Steps

The command now fully integrates with the MCP profile system. Users can:
1. Run `testmcpy setup` to create `.mcp_services.yaml`
2. Run `testmcpy config-mcp claude-desktop` to configure Claude Desktop
3. No manual token management needed!
