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

## Install via Homebrew (Once Published)

```bash
# Add Preset tap
brew tap preset-io/tap

# Install testmcpy
brew install testmcpy

# Verify installation
testmcpy --help
```

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

To publish this formula to Homebrew:

1. Create a tag and release on GitHub:
```bash
git tag v0.1.0
git push origin v0.1.0
```

2. Download the release tarball and calculate SHA256:
```bash
wget https://github.com/preset-io/testmcpy/archive/refs/tags/v0.1.0.tar.gz
shasum -a 256 v0.1.0.tar.gz
```

3. Update `testmcpy.rb` with the correct SHA256

4. Create a Homebrew tap repository (if not exists):
```bash
# Create preset-io/homebrew-tap repository on GitHub
```

5. Add the formula to your tap:
```bash
cp testmcpy.rb /path/to/homebrew-tap/Formula/
cd /path/to/homebrew-tap
git add Formula/testmcpy.rb
git commit -m "Add testmcpy formula"
git push
```

6. Users can now install with:
```bash
brew tap preset-io/tap
brew install testmcpy
```

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
