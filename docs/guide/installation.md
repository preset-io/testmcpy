# Installation Guide

Detailed installation instructions for testmcpy.

## System Requirements

### Python Version

testmcpy requires Python 3.9 through 3.12:

```bash
python --version  # Should show 3.9.x through 3.12.x
```

Python 3.13+ is not yet supported due to dependency compatibility.

### Operating Systems

- **macOS**: Fully supported
- **Linux**: Fully supported
- **Windows**: Supported with WSL (Windows Subsystem for Linux) recommended

### Virtual Environment

Always use a virtual environment to avoid dependency conflicts:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

## Installation Methods

### Method 1: From PyPI (Recommended)

Install the latest stable release:

```bash
# Basic installation
pip install testmcpy

# With web UI support
pip install 'testmcpy[server]'

# With Claude SDK support
pip install 'testmcpy[sdk]'

# With development tools
pip install 'testmcpy[dev]'

# All features
pip install 'testmcpy[all]'
```

### Method 2: From Source

For development or latest features:

```bash
# Clone repository
git clone https://github.com/preset-io/testmcpy.git
cd testmcpy

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Or with all features
pip install -e '.[all]'
```

### Method 3: Using pipx (Isolated Installation)

Install testmcpy as an isolated CLI tool:

```bash
# Install pipx if needed
pip install pipx
pipx ensurepath

# Install testmcpy
pipx install testmcpy

# Or with extras
pipx install 'testmcpy[all]'
```

## Installation Extras

### [server] - Web UI Support

Installs FastAPI, uvicorn, and dependencies for the web interface:

```bash
pip install 'testmcpy[server]'
```

Enables:
- `testmcpy serve` command
- Web-based UI at http://localhost:8000
- REST API endpoints

### [sdk] - Claude Agent SDK

Installs Anthropic's Agent SDK for advanced features:

```bash
pip install 'testmcpy[sdk]'
```

### [dev] - Development Tools

Installs testing, linting, and development dependencies:

```bash
pip install 'testmcpy[dev]'
```

Includes:
- pytest (testing framework)
- black (code formatter)
- mypy (type checker)
- ruff (linter)

### [all] - Everything

Install all optional features:

```bash
pip install 'testmcpy[all]'
```

## LLM Provider Setup

### Anthropic (Claude)

Best tool-calling accuracy, recommended for production:

```bash
# Get API key from: https://console.anthropic.com/
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Add to ~/.testmcpy
echo "ANTHROPIC_API_KEY=sk-ant-your-key" >> ~/.testmcpy
echo "DEFAULT_PROVIDER=anthropic" >> ~/.testmcpy
echo "DEFAULT_MODEL=claude-haiku-4-5" >> ~/.testmcpy
```

Available models:
- `claude-haiku-4-5` - Fast, cost-effective
- `claude-sonnet-4-5` - Balanced performance
- `claude-opus-4-1` - Highest capability

### OpenAI (GPT)

```bash
# Get API key from: https://platform.openai.com/api-keys
export OPENAI_API_KEY="sk-your-key-here"

# Add to ~/.testmcpy
echo "OPENAI_API_KEY=sk-your-key" >> ~/.testmcpy
echo "DEFAULT_PROVIDER=openai" >> ~/.testmcpy
echo "DEFAULT_MODEL=gpt-4-turbo" >> ~/.testmcpy
```

Available models:
- `gpt-4-turbo` - Latest GPT-4 with vision
- `gpt-4` - GPT-4 base model
- `gpt-3.5-turbo` - Faster, cheaper

### Ollama (Local, Free)

Run models locally without API costs:

```bash
# Install Ollama
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve

# Pull a model
ollama pull llama3.1:8b

# Configure testmcpy
echo "DEFAULT_PROVIDER=ollama" >> ~/.testmcpy
echo "DEFAULT_MODEL=llama3.1:8b" >> ~/.testmcpy
```

Available models:
- `llama3.1:8b` - Fast, good for development
- `llama3.1:70b` - More capable (requires more RAM)
- `mistral:7b` - Alternative option
- `codellama:13b` - Optimized for code

See [Ollama library](https://ollama.com/library) for more models.

## Verification

### Check Installation

```bash
# Verify installation
testmcpy --version

# Check available commands
testmcpy --help

# View configuration
testmcpy config-cmd

# Run diagnostics
testmcpy doctor
```

### Test MCP Connection

```bash
# List available tools (requires MCP service)
testmcpy tools

# Interactive chat
testmcpy chat
```

## Configuration

### Configuration Files

testmcpy searches for configuration in this order:

1. **Command-line options** (highest priority)
2. **`.env`** in current directory
3. **`~/.testmcpy`** user config file
4. **Environment variables**
5. **Built-in defaults** (lowest priority)

### Basic Configuration (~/.testmcpy)

```bash
# MCP Service
MCP_URL=http://localhost:5008/mcp/
MCP_AUTH_TOKEN=your_bearer_token

# LLM Provider
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-your-key

# Optional: Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Optional: Timeouts
DEFAULT_TIMEOUT=30
```

### Environment-Specific Configuration

Use `.env` files for different environments:

```bash
# .env.dev
MCP_URL=http://localhost:5008/mcp/
DEFAULT_MODEL=llama3.1:8b  # Use free local model for dev

# .env.staging
MCP_URL=https://staging.example.com/mcp/
DEFAULT_MODEL=claude-haiku-4-5

# .env.prod
MCP_URL=https://api.example.com/mcp/
DEFAULT_MODEL=claude-sonnet-4-5
```

Load with:

```bash
# Load environment-specific config
source .env.dev
testmcpy run tests/
```

### Profile-Based Configuration

For managing multiple environments, use profiles:

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
    name: "Staging"
    mcp_url: "https://staging.example.com/mcp/"
    auth:
      type: "jwt"
      api_url: "https://staging.example.com/v1/auth/"
      api_token: "${STAGING_TOKEN}"
      api_secret: "${STAGING_SECRET}"
```

Use with:

```bash
testmcpy tools --profile staging
testmcpy run tests/ --profile prod
```

See [Configuration Guide](configuration.md) for complete details.

## Upgrading

### Upgrade from PyPI

```bash
pip install --upgrade testmcpy

# Or with extras
pip install --upgrade 'testmcpy[all]'
```

### Upgrade from Source

```bash
cd testmcpy
git pull
pip install -e '.[all]'
```

### Check for Updates

```bash
pip list --outdated | grep testmcpy
```

## Uninstalling

```bash
# Remove testmcpy
pip uninstall testmcpy

# Remove configuration (optional)
rm ~/.testmcpy
rm -rf ~/.testmcpy_cache
```

## Troubleshooting

### Python Version Issues

```bash
# Check Python version
python --version

# If wrong version, use specific version
python3.11 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Permission Errors

```bash
# Don't use sudo with pip
# Instead, use --user flag or virtual environment

# With --user flag
pip install --user testmcpy[all]

# Or use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Dependency Conflicts

```bash
# Create fresh virtual environment
deactivate  # If in existing venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install testmcpy[all]
```

### SSL Certificate Errors

```bash
# Update certificates (macOS)
/Applications/Python\ 3.11/Install\ Certificates.command

# Or upgrade pip and certifi
pip install --upgrade pip certifi
```

### Network/Proxy Issues

```bash
# Set proxy if needed
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# Install with proxy
pip install --proxy=http://proxy.example.com:8080 testmcpy[all]
```

## Platform-Specific Notes

### macOS

```bash
# Install Python with Homebrew
brew install python@3.11

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Linux (Ubuntu/Debian)

```bash
# Install Python and venv
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Windows (with WSL)

```bash
# Install WSL if not already installed
wsl --install

# Inside WSL, follow Linux instructions
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
python3.11 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Windows (Native)

```bash
# Install Python from python.org
# Then in PowerShell or Command Prompt:

# Create virtual environment
python -m venv venv
venv\Scripts\activate
pip install testmcpy[all]
```

## Docker Installation (Optional)

Run testmcpy in Docker:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install testmcpy
RUN pip install testmcpy[all]

# Copy tests
COPY tests/ /app/tests/
COPY .env /app/.env

# Run tests
CMD ["testmcpy", "run", "tests/"]
```

Build and run:

```bash
docker build -t testmcpy .
docker run --env-file .env testmcpy
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get started quickly
- [Configuration Guide](configuration.md) - Advanced configuration
- [Development Guide](development.md) - Set up for development
- [Architecture Overview](architecture.md) - Understand the system
