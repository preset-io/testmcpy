# Installation Guide

## Install from Source (Development)

```bash
# Clone the repository
git clone https://github.com/preset-io/testmcpy.git
cd testmcpy

# Install in editable mode
pip install -e .

# Verify installation
testmcpy --help
```

## Install from PyPI (Once Published)

```bash
pip install testmcpy
```

## Install via Homebrew (Once Published to PyPI)

```bash
# Tap this repository
brew tap preset-io/testmcpy

# Install testmcpy
brew install testmcpy

# Verify installation
testmcpy --help
```

**Note**: Homebrew installation requires testmcpy to be published on PyPI first. The formula automatically fetches the package from PyPI.

## Usage Examples

```bash
# List all MCP tools
testmcpy tools

# List tools with detailed schemas
testmcpy tools --detail

# Filter tools by name
testmcpy tools --filter chart

# Output as JSON
testmcpy tools --format json

# Output as YAML
testmcpy tools --format yaml

# Use custom MCP server URL
testmcpy tools --mcp-url https://your-mcp-server.com/mcp
```

## Configuration

### Quick Setup (Recommended)

Use the interactive setup wizard to create configuration files:

```bash
testmcpy setup
```

This will guide you through:
- **LLM Provider setup**: Choose between Claude (Anthropic), GPT-4 (OpenAI), or local Ollama models
- **MCP Service setup**: Configure your MCP server URL and authentication
- **API Key management**: Automatically detects keys from environment (ANTHROPIC_API_KEY, OPENAI_API_KEY) and saves them to `.llm_providers.yaml`

The setup command creates two YAML files in your current directory with all necessary configuration.

### LLM Provider Configuration (.llm_providers.yaml)

The setup command creates `.llm_providers.yaml` in your project directory to configure LLM models and providers:

```yaml
default: prod

profiles:
  prod:
    name: "Production"
    description: "High-quality models for production use"
    providers:
      - name: "Claude claude-sonnet-4-5"
        provider: "anthropic"
        model: "claude-sonnet-4-5"
        api_key: "your-anthropic-api-key-here"  # API key stored directly
        timeout: 60
        default: true
```

You can also reference environment variables using `api_key: "${ANTHROPIC_API_KEY}"` syntax.

See `.llm_providers.yaml.example` for more examples including Ollama, OpenAI, and multiple profiles.

### MCP Server Configuration (.mcp_services.yaml)

The setup command creates `.mcp_services.yaml` in your project directory for MCP server profiles:

```yaml
default: prod

profiles:
  prod:
    name: "Production"
    description: "Production MCP service"
    mcps:
      - name: "Preset Superset"
        mcp_url: "https://your-workspace.preset.io/mcp"
        auth:
          auth_type: "jwt"  # or "bearer" or "none"
          api_url: "https://api.app.preset.io/v1/auth/"
          api_token: "your-api-token"
          api_secret: "your-api-secret"
        timeout: 30
        rate_limit_rpm: 60
        default: true
```

See `.mcp_services.yaml.example` for more configuration examples.

### Configuration Priority

Configuration values are loaded in this order (highest priority first):
1. CLI options (e.g., `--model`, `--provider`)
2. LLM Profile (`.llm_providers.yaml`)
3. MCP Profile (`.mcp_services.yaml`)
4. Environment variables (`.env` file or system environment)

### Re-running Setup

The setup command is **idempotent** - it's safe to run multiple times. Use `--force` to overwrite existing configuration files:

```bash
testmcpy setup --force
```

## Publishing to Homebrew

This repository includes a Homebrew formula in the `Formula/` directory, making it both the source repo and the Homebrew tap.

### Steps to enable Homebrew installation:

1. **Publish to PyPI first** (required):
```bash
python -m build
python -m twine upload dist/*
```

2. **Update the formula with PyPI SHA256**:
```bash
# Download from PyPI
wget https://files.pythonhosted.org/packages/source/t/testmcpy/testmcpy-0.1.0.tar.gz

# Calculate SHA256
shasum -a 256 testmcpy-0.1.0.tar.gz

# Update Formula/testmcpy.rb with the SHA256 hash
```

3. **Commit and push the updated formula**:
```bash
git add Formula/testmcpy.rb
git commit -m "Update Homebrew formula with PyPI SHA256"
git push
```

4. **Users can now install with**:
```bash
brew tap preset-io/testmcpy
brew install testmcpy
```

The formula uses `virtualenv_install_with_resources` which automatically installs testmcpy and all dependencies from PyPI into a Homebrew-managed virtual environment.

## Publishing to PyPI

To publish to PyPI:

1. Install build tools:
```bash
pip install build twine
```

2. Build the package:
```bash
python -m build
```

3. Upload to PyPI:
```bash
python -m twine upload dist/*
```

4. Users can now install with:
```bash
pip install testmcpy
```

## Development

To contribute to testmcpy:

```bash
# Clone and install in development mode
git clone https://github.com/preset-io/testmcpy.git
cd testmcpy
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .

# Lint code
flake8
```
