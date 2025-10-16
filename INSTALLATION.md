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

Create a `.env` file in your project directory:

```bash
# Default model to use for testing
DEFAULT_MODEL=claude-sonnet-4.5-20250929

# Default provider (anthropic, ollama, openai, local, claude-sdk)
DEFAULT_PROVIDER=anthropic

# MCP service URL
MCP_URL=http://localhost:5008/mcp/

# Anthropic/Claude API key (required for anthropic and claude-sdk providers)
ANTHROPIC_API_KEY=your-api-key-here

# MCP Authentication (optional - for authenticated MCP servers)
MCP_AUTH_TOKEN=your-bearer-token-here
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
