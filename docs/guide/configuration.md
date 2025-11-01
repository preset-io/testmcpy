# Configuration Guide

Complete guide to configuring testmcpy for different environments and use cases.

## Configuration System

testmcpy uses a layered configuration system with clear priorities:

### Priority Order (Highest to Lowest)

1. **Command-line options** - Override everything
2. **MCP Profile** - From `.mcp_services.yaml`
3. **`.env`** - In current directory
4. **`~/.testmcpy`** - User configuration file
5. **Environment variables** - System environment
6. **Built-in defaults** - Fallback values

Later sources provide defaults for earlier sources.

## Configuration Files

### User Configuration (`~/.testmcpy`)

Global configuration file in your home directory:

```bash
# MCP Service Configuration
MCP_URL=http://localhost:5008/mcp/
MCP_AUTH_TOKEN=your_bearer_token_here

# Or use JWT authentication
# MCP_AUTH_API_URL=https://api.example.com/v1/auth/
# MCP_AUTH_API_TOKEN=your_api_token
# MCP_AUTH_API_SECRET=your_api_secret

# LLM Provider Configuration
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-your-key

# Optional Settings
DEFAULT_TIMEOUT=30
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### Project Configuration (`.env`)

Project-specific configuration (add to `.gitignore`):

```bash
# .env
MCP_URL=http://localhost:5008/mcp/
DEFAULT_MODEL=llama3.1:8b
DEFAULT_PROVIDER=ollama
```

### Profile Configuration (`.mcp_services.yaml`)

Multi-environment configuration with profiles (detailed below).

## Configuration Options

### MCP Service Settings

#### `MCP_URL`

URL of your MCP service endpoint.

```bash
MCP_URL=http://localhost:5008/mcp/
```

**Examples:**
- Local: `http://localhost:5008/mcp/`
- Staging: `https://staging.example.com/mcp/`
- Production: `https://api.example.com/mcp/`

#### `MCP_AUTH_TOKEN`

Bearer token for MCP service authentication.

```bash
MCP_AUTH_TOKEN=your_bearer_token_here
```

Use this for simple static token authentication.

#### JWT Authentication (Alternative)

For dynamic JWT token generation:

```bash
MCP_AUTH_API_URL=https://api.example.com/v1/auth/
MCP_AUTH_API_TOKEN=your_api_token
MCP_AUTH_API_SECRET=your_api_secret
```

testmcpy will:
1. Fetch JWT token from auth API
2. Cache token for 50 minutes
3. Automatically refresh when expired

### LLM Provider Settings

#### `DEFAULT_PROVIDER`

LLM provider to use.

```bash
DEFAULT_PROVIDER=anthropic  # or openai, ollama
```

**Options:**
- `anthropic` - Claude models (recommended for tool calling)
- `openai` - GPT models
- `ollama` - Local models

#### `DEFAULT_MODEL`

Model to use by default.

```bash
# Anthropic models
DEFAULT_MODEL=claude-haiku-4-5       # Fast, cost-effective
DEFAULT_MODEL=claude-sonnet-4-5      # Balanced
DEFAULT_MODEL=claude-opus-4-1        # Most capable

# OpenAI models
DEFAULT_MODEL=gpt-4-turbo
DEFAULT_MODEL=gpt-4
DEFAULT_MODEL=gpt-3.5-turbo

# Ollama models
DEFAULT_MODEL=llama3.1:8b
DEFAULT_MODEL=llama3.1:70b
DEFAULT_MODEL=mistral:7b
```

#### Provider API Keys

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Ollama (no key needed)
OLLAMA_BASE_URL=http://localhost:11434  # Optional, default is localhost
```

### Performance Settings

#### `DEFAULT_TIMEOUT`

Timeout for test execution in seconds.

```bash
DEFAULT_TIMEOUT=30  # Default: 30 seconds
```

Can be overridden per-test in YAML:

```yaml
tests:
  - name: "long_running_test"
    timeout: 60  # Override for this test
```

#### `RATE_LIMIT_REQUESTS_PER_MINUTE`

Rate limit for API requests.

```bash
RATE_LIMIT_REQUESTS_PER_MINUTE=60  # Default: 60
```

Prevents hitting provider rate limits.

### Logging Settings

#### `LOG_LEVEL`

Logging verbosity.

```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Levels:**
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages
- `ERROR`: Error messages
- `CRITICAL`: Critical failures

#### `LOG_FILE`

Write logs to file.

```bash
LOG_FILE=/path/to/testmcpy.log
```

## MCP Profiles

Manage multiple environments with profile-based configuration.

### Creating Profile Configuration

Create `.mcp_services.yaml` in your project:

```yaml
# Default profile to use
default: local

# Global settings (apply to all profiles)
global:
  timeout: 30
  rate_limit:
    requests_per_minute: 60

# Profile definitions
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

### Using Profiles

```bash
# Use default profile
testmcpy tools

# Use specific profile
testmcpy tools --profile staging
testmcpy run tests/ --profile prod

# Override profile settings
testmcpy tools --profile staging --mcp-url http://localhost:5008/mcp/
```

### Authentication Types

#### Bearer Token

Simple static token:

```yaml
auth:
  type: "bearer"
  token: "${TOKEN}"
```

#### JWT (Dynamic)

Fetch token from auth API:

```yaml
auth:
  type: "jwt"
  api_url: "https://api.example.com/v1/auth/"
  api_token: "${API_TOKEN}"
  api_secret: "${API_SECRET}"
```

Tokens are cached for 50 minutes.

#### No Authentication

For local development:

```yaml
auth:
  type: "none"
```

### Environment Variable Substitution

Use `${VAR_NAME}` to reference environment variables:

```yaml
profiles:
  prod:
    mcp_url: "${PROD_MCP_URL}"
    auth:
      type: "bearer"
      token: "${PROD_TOKEN}"
```

With default values:

```yaml
profiles:
  dev:
    mcp_url: "${DEV_MCP_URL:-http://localhost:5008/mcp/}"
    # Uses env var if set, otherwise uses default
```

### Profile Discovery

testmcpy searches for `.mcp_services.yaml` in:

1. Current directory
2. Parent directories (up to 5 levels)
3. Home directory (`~/.mcp_services.yaml`)

### Sharing Profile Configuration

**Recommended approach:**

1. Commit `.mcp_services.yaml.example` with placeholders:

```yaml
# .mcp_services.yaml.example
default: local

profiles:
  local:
    mcp_url: "http://localhost:5008/mcp/"
    auth:
      type: "bearer"
      token: "${MCP_AUTH_TOKEN}"

  prod:
    mcp_url: "${PROD_MCP_URL}"
    auth:
      type: "jwt"
      api_token: "${PROD_TOKEN}"
      api_secret: "${PROD_SECRET}"
```

2. Copy and customize:

```bash
cp .mcp_services.yaml.example .mcp_services.yaml
# Edit .mcp_services.yaml with your values
```

3. Add to `.gitignore`:

```bash
echo ".mcp_services.yaml" >> .gitignore
```

4. Share environment variables securely (e.g., password manager, vault)

## Configuration for Different Scenarios

### Local Development

```bash
# ~/.testmcpy
MCP_URL=http://localhost:5008/mcp/
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b
LOG_LEVEL=DEBUG
```

Use free local models for development.

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
env:
  MCP_URL: ${{ secrets.MCP_URL }}
  MCP_AUTH_TOKEN: ${{ secrets.MCP_AUTH_TOKEN }}
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  DEFAULT_PROVIDER: anthropic
  DEFAULT_MODEL: claude-haiku-4-5
  DEFAULT_TIMEOUT: 60
```

Use environment variables for secrets.

### Multi-Tenant SaaS

```yaml
# .mcp_services.yaml
profiles:
  customer-a:
    name: "Customer A"
    mcp_url: "https://customer-a.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${CUSTOMER_A_TOKEN}"

  customer-b:
    name: "Customer B"
    mcp_url: "https://customer-b.example.com/mcp/"
    auth:
      type: "bearer"
      token: "${CUSTOMER_B_TOKEN}"
```

### Testing Different Models

```bash
# Compare models on same tests
testmcpy run tests/ --model claude-haiku-4-5 --output haiku_results.json
testmcpy run tests/ --model claude-sonnet-4-5 --output sonnet_results.json
testmcpy run tests/ --model gpt-4-turbo --provider openai --output gpt4_results.json

# Generate comparison report
testmcpy report haiku_results.json sonnet_results.json gpt4_results.json
```

## Command-Line Options

All configuration can be overridden via command-line:

```bash
# MCP settings
testmcpy tools --mcp-url http://localhost:5008/mcp/
testmcpy tools --mcp-auth-token your_token

# LLM settings
testmcpy run tests/ --model claude-sonnet-4-5
testmcpy run tests/ --provider openai

# Performance settings
testmcpy run tests/ --timeout 60
testmcpy run tests/ --concurrency 5

# Output settings
testmcpy run tests/ --verbose
testmcpy run tests/ --output results.json
testmcpy run tests/ --format json
```

## Viewing Configuration

### Check Current Configuration

```bash
testmcpy config-cmd
```

Output shows:

```
Configuration Sources:
======================
MCP_URL: http://localhost:5008/mcp/ (Profile: local)
MCP_AUTH_TOKEN: *** (Environment)
DEFAULT_PROVIDER: anthropic (~/.testmcpy)
DEFAULT_MODEL: claude-haiku-4-5 (~/.testmcpy)
ANTHROPIC_API_KEY: sk-ant-*** (~/.testmcpy)
DEFAULT_TIMEOUT: 30 (Default)
```

Shows where each value comes from.

### Validate Configuration

```bash
testmcpy doctor
```

Checks:
- Configuration file syntax
- Required settings present
- API keys valid
- MCP service reachable
- LLM provider accessible

## Best Practices

### 1. Security

- **Never commit secrets** to version control
- Use **environment variables** for sensitive data
- Use **`.gitignore`** for `.env` and `.mcp_services.yaml`
- **Share `.example` files** with placeholders
- **Rotate tokens** regularly

### 2. Organization

- **User config (`~/.testmcpy`)**: Personal defaults
- **Project config (`.env`)**: Project-specific overrides
- **Profile config (`.mcp_services.yaml`)**: Multi-environment setup
- **Command-line**: Ad-hoc overrides

### 3. Cost Management

```bash
# Development: Use free local models
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b

# Testing: Use cost-effective models
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-haiku-4-5

# Production: Use best models
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-sonnet-4-5
```

### 4. Performance

```bash
# Increase concurrency for faster test runs
testmcpy run tests/ --concurrency 10

# Increase timeout for complex tests
DEFAULT_TIMEOUT=60

# Rate limit to avoid hitting API limits
RATE_LIMIT_REQUESTS_PER_MINUTE=50
```

## Troubleshooting

### Configuration Not Loading

```bash
# Check configuration search paths
testmcpy config-cmd --verbose

# Verify file permissions
ls -la ~/.testmcpy
ls -la .env

# Check file syntax
cat ~/.testmcpy | grep -v '^#' | grep .
```

### Profile Not Found

```bash
# List available profiles
grep "^  [a-z]" .mcp_services.yaml

# Use --profile with exact name
testmcpy tools --profile staging  # Not Staging
```

### Environment Variables Not Expanding

```bash
# Check variable is set
echo $MCP_AUTH_TOKEN

# Export if needed
export MCP_AUTH_TOKEN="your-token"

# Verify in config
testmcpy config-cmd | grep TOKEN
```

### Authentication Failing

```bash
# Test MCP connection
testmcpy tools --verbose

# Check token validity
curl -H "Authorization: Bearer $MCP_AUTH_TOKEN" $MCP_URL

# Regenerate JWT
# JWT tokens are cached, wait or restart to fetch new one
```

## Migrating Configurations

### From Environment Variables to Profiles

**Before:**

```bash
# Multiple env files
# .env.dev
MCP_URL=http://localhost:5008/mcp/

# .env.staging
MCP_URL=https://staging.example.com/mcp/

# .env.prod
MCP_URL=https://api.example.com/mcp/
```

**After:**

```yaml
# .mcp_services.yaml
profiles:
  dev:
    mcp_url: "http://localhost:5008/mcp/"
  staging:
    mcp_url: "https://staging.example.com/mcp/"
  prod:
    mcp_url: "https://api.example.com/mcp/"
```

### From Static Tokens to JWT

**Before:**

```bash
MCP_AUTH_TOKEN=static-token-here
```

**After:**

```yaml
profiles:
  prod:
    mcp_url: "https://api.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://api.example.com/v1/auth/"
      api_token: "${API_TOKEN}"
      api_secret: "${API_SECRET}"
```

## Advanced Configuration

### Custom Headers

Add custom HTTP headers (future feature):

```yaml
profiles:
  custom:
    mcp_url: "https://api.example.com/mcp/"
    headers:
      X-Custom-Header: "value"
      X-Request-ID: "${REQUEST_ID}"
```

### Proxy Configuration

Configure HTTP proxy:

```bash
# Environment variables
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
export NO_PROXY=localhost,127.0.0.1

testmcpy tools
```

### Custom CA Certificates

For self-signed certificates:

```bash
export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
testmcpy tools
```

## Related Documentation

- [MCP Profiles Documentation](../../docs/MCP_PROFILES.md) - Detailed profile system docs
- [Quick Start](quickstart.md) - Getting started
- [Installation Guide](installation.md) - Installation options
- [Architecture](architecture.md) - System architecture
