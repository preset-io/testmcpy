# MCP Service Profiles

> **Note**: This documentation has been integrated into [guide/configuration.md](guide/configuration.md). This file is kept for backward compatibility but may be removed in a future version. Please update your bookmarks.

Manage multiple MCP service configurations (dev, staging, prod, etc.) using profile-based YAML configuration.

## Overview

MCP Profiles allow you to:
- **Manage multiple environments** in one file (dev, staging, prod, custom)
- **Keep secrets secure** in environment variables (referenced with `${VAR_NAME}`)
- **Switch between services** easily with `--profile` flag
- **Share configurations** safely (YAML with env var placeholders)

## Quick Start

### 1. Create Configuration File

Create `.mcp_services.yaml` in your project or home directory:

```bash
# Copy example file
cp .mcp_services.yaml.example .mcp_services.yaml

# Edit with your configurations
vim .mcp_services.yaml
```

### 2. Define Profiles

```yaml
# .mcp_services.yaml
default: local

profiles:
  local:
    name: "Local Development"
    mcp_url: "http://localhost:5008/mcp/"
    auth:
      type: "bearer"
      token: "${MCP_AUTH_TOKEN}"

  staging:
    name: "Staging Environment"
    mcp_url: "https://staging.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://staging.example.com/v1/auth/"
      api_token: "${STAGING_API_TOKEN}"
      api_secret: "${STAGING_API_SECRET}"

  prod:
    name: "Production"
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://api.example.com/v1/auth/"
      api_token: "${PROD_API_TOKEN}"
      api_secret: "${PROD_API_SECRET}"
```

**Default Selection:**
- The top-level `default: local` sets the default profile used when no --profile flag is specified
- This applies to both CLI commands and the web UI

### 3. Set Environment Variables

```bash
# Set secrets in environment
export MCP_AUTH_TOKEN="your-local-token"
export STAGING_API_TOKEN="your-staging-token"
export STAGING_API_SECRET="your-staging-secret"
export PROD_API_TOKEN="your-prod-token"
export PROD_API_SECRET="your-prod-secret"
```

### 4. Use Profiles

```bash
# Use default profile (local)
testmcpy tools

# Use specific profile
testmcpy tools --profile staging
testmcpy run tests/ --profile prod

# Run tests against staging
testmcpy run tests/critical.yaml --profile staging --model claude-sonnet-4-5
```

## Configuration Priority

Configuration is loaded in this order (highest to lowest priority):

1. **Command-line options** (`--profile`, `--mcp-url`, etc.)
2. **MCP Profile** from `.mcp_services.yaml`
3. **`.env`** in current directory
4. **`~/.testmcpy`** user config file
5. **Environment variables**
6. **Built-in defaults**

## File Locations

testmcpy searches for `.mcp_services.yaml` in:

1. Current directory
2. Parent directories (up to 5 levels)
3. Home directory (`~/.mcp_services.yaml`)

## Authentication Types

### Bearer Token

Simple static token authentication:

```yaml
profiles:
  simple:
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${MCP_TOKEN}"
```

### JWT (Dynamic Token Generation)

Fetch JWT dynamically from auth API:

```yaml
profiles:
  dynamic:
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://api.example.com/v1/auth/"
      api_token: "${API_TOKEN}"
      api_secret: "${API_SECRET}"
```

Tokens are cached for 50 minutes to avoid excessive API calls.

### OAuth (Future)

OAuth 2.0 flow (planned for future release):

```yaml
profiles:
  oauth-service:
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "oauth"
      client_id: "${CLIENT_ID}"
      client_secret: "${CLIENT_SECRET}"
      token_url: "https://api.example.com/oauth/token"
      scopes: ["mcp:read", "mcp:write"]
```

### No Authentication

For local development without auth:

```yaml
profiles:
  local-test:
    mcp_url: "http://localhost:5008/mcp/"
    auth:
      type: "none"
```

## Environment Variable Substitution

Use `${VAR_NAME}` syntax to reference environment variables:

```yaml
profiles:
  prod:
    mcp_url: "${PROD_MCP_URL}"  # Full URL from env
    auth:
      type: "jwt"
      api_url: "${PROD_AUTH_URL}"
      api_token: "${PROD_API_TOKEN}"
      api_secret: "${PROD_API_SECRET}"
```

With default values:

```yaml
profiles:
  dev:
    mcp_url: "${DEV_MCP_URL:-http://localhost:5008/mcp/}"
    # Uses env var if set, otherwise uses default
```

## Global Settings

Apply settings to all profiles:

```yaml
global:
  timeout: 30
  rate_limit:
    requests_per_minute: 60
  retry:
    max_attempts: 3
    backoff_multiplier: 2

profiles:
  # Profile-specific timeout overrides global
  fast:
    timeout: 10  # Override global timeout
    mcp_url: "http://fast.example.com/mcp/"
    # ... rest of config
```

## Security Best Practices

### ✅ DO

- **Keep secrets in environment variables**
- **Use `.gitignore`** for `.mcp_services.yaml` if it contains any sensitive data
- **Share `.mcp_services.yaml.example`** with `${VAR_NAME}` placeholders for team members
- **Use different secrets** for each environment (dev, staging, prod)
- **Rotate tokens** regularly

### ❌ DON'T

- **Don't commit secrets** to Git (use environment variables)
- **Don't share production secrets** in team chat or email
- **Don't reuse tokens** across environments

## Example Configurations

### Multi-Tenant SaaS

```yaml
default: customer-a

profiles:
  customer-a:
    name: "Customer A Production"
    mcp_url: "https://customer-a.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${CUSTOMER_A_TOKEN}"

  customer-b:
    name: "Customer B Production"
    mcp_url: "https://customer-b.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${CUSTOMER_B_TOKEN}"

  demo:
    name: "Demo Environment"
    mcp_url: "https://demo.example.com/mcp/"
    auth:
      type: "none"
```

### CI/CD Pipeline

```yaml
default: ci

profiles:
  ci:
    name: "CI/CD Environment"
    mcp_url: "${CI_MCP_URL}"
    auth:
      type: "jwt"
      api_url: "${CI_AUTH_URL}"
      api_token: "${CI_API_TOKEN}"
      api_secret: "${CI_API_SECRET}"
```

In CI/CD (GitHub Actions, GitLab CI):

```yaml
# .github/workflows/test.yml
env:
  CI_MCP_URL: ${{ secrets.CI_MCP_URL }}
  CI_AUTH_URL: ${{ secrets.CI_AUTH_URL }}
  CI_API_TOKEN: ${{ secrets.CI_API_TOKEN }}
  CI_API_SECRET: ${{ secrets.CI_API_SECRET }}

steps:
  - run: testmcpy run tests/ --profile ci
```

### Development Team

```yaml
# Shared .mcp_services.yaml.example (committed to Git)
default: local

profiles:
  local:
    name: "Local Development"
    mcp_url: "http://localhost:5008/mcp/"
    auth:
      type: "none"

  dev-shared:
    name: "Shared Dev Server"
    mcp_url: "https://dev.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${SHARED_DEV_TOKEN}"  # Team gets this from secure vault

  personal-dev:
    name: "Personal Dev Instance"
    mcp_url: "${MY_DEV_URL}"  # Each dev has their own
    auth:
      type: "bearer"
      token: "${MY_DEV_TOKEN}"
```

## Migrating from Environment Variables

### Before (Environment Variables Only)

```bash
# ~/.testmcpy
MCP_URL=https://staging.example.com/mcp/
MCP_AUTH_API_URL=https://staging.example.com/v1/auth/
MCP_AUTH_API_TOKEN=staging-token
MCP_AUTH_API_SECRET=staging-secret
```

### After (With Profiles)

```yaml
# .mcp_services.yaml
default: staging

profiles:
  staging:
    mcp_url: "https://staging.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://staging.example.com/v1/auth/"
      api_token: "${STAGING_TOKEN}"
      api_secret: "${STAGING_SECRET}"

  prod:
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://api.example.com/v1/auth/"
      api_token: "${PROD_TOKEN}"
      api_secret: "${PROD_SECRET}"
```

```bash
# Environment variables (much cleaner!)
export STAGING_TOKEN="staging-token"
export STAGING_SECRET="staging-secret"
export PROD_TOKEN="prod-token"
export PROD_SECRET="prod-secret"
```

Now you can easily switch:

```bash
testmcpy run tests/ --profile staging
testmcpy run tests/ --profile prod
```

## Backwards Compatibility

Existing configurations continue to work:
- Environment variables (`MCP_URL`, `MCP_AUTH_TOKEN`, etc.)
- `~/.testmcpy` config file
- `.env` files

Profiles are **optional** - if no `.mcp_services.yaml` exists, testmcpy falls back to the previous behavior.

## Troubleshooting

### Profile Not Found

```bash
$ testmcpy tools --profile nonexistent
Warning: Failed to load MCP profile 'nonexistent': Profile not found
# Falls back to environment variables or defaults
```

### Missing Environment Variables

If `${VAR_NAME}` is not set, it resolves to empty string:

```yaml
token: "${MISSING_TOKEN}"  # Resolves to ""
```

Use defaults to prevent this:

```yaml
token: "${TOKEN:-default-dev-token}"
```

### Check Configuration

See which profile and values are being used:

```bash
testmcpy config-cmd
```

Output shows source of each config value:

```
MCP_URL: https://staging.example.com/mcp/ (Profile: staging)
MCP_AUTH_API_URL: https://staging.example.com/v1/auth/ (Profile: staging)
DEFAULT_MODEL: claude-haiku-4-5 (~/.testmcpy)
```

## Advanced Usage

### Profile-Specific Test Suites

```bash
# tests/integration/
├── local.yaml        # Tests for local dev
├── staging.yaml      # Tests for staging
└── prod.yaml         # Tests for prod

# Run appropriate tests for each environment
testmcpy run tests/integration/local.yaml --profile local
testmcpy run tests/integration/staging.yaml --profile staging
testmcpy run tests/integration/prod.yaml --profile prod
```

### Override Profile Settings

Command-line options override profile settings:

```bash
# Use staging profile but override URL
testmcpy tools --profile staging --mcp-url http://localhost:5008/mcp/
```

### Multiple Config Files

For large teams, split configurations:

```bash
# .mcp_services.yaml (team shared, committed)
default: local
profiles:
  local:
    # ... local config

# .mcp_services.local.yaml (personal, gitignored)
profiles:
  my-dev:
    # ... personal dev config
```

Note: Currently only `.mcp_services.yaml` is supported. Multiple file support may be added in future.

## CLI Commands (Planned)

```bash
# List available profiles
testmcpy profiles

# Show profile details
testmcpy profiles show staging

# Validate configuration
testmcpy profiles validate
```

## Integration with CI/CD

See [CI/CD Integration Guide](./examples/ci-cd/README.md) for complete examples with profiles.

## See Also

- [Client Usage Guide](./CLIENT_USAGE_GUIDE.md) - Complete testing guide
- [Configuration Reference](../README.md#configuration) - All config options
- [CI/CD Examples](../examples/ci-cd/) - GitHub Actions & GitLab CI
