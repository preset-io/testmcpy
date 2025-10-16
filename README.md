# testmcpy - MCP Testing Framework

A comprehensive testing framework for validating LLM tool calling capabilities with MCP (Model Context Protocol) services, specifically designed for testing Superset operations.

## Quick Start

### Installation

**From source (development):**
```bash
git clone https://github.com/preset-io/testmcpy.git
cd testmcpy
pip install -e .
```

**From PyPI (once published):**
```bash
pip install testmcpy
```

**Via Homebrew (once published to PyPI):**
```bash
brew tap preset-io/testmcpy
brew install testmcpy
```

See [INSTALLATION.md](INSTALLATION.md) for detailed installation instructions and distribution options.

### Quick Usage

```bash
# First-time setup: Create user config file
testmcpy setup

# View current configuration
testmcpy config-cmd

# List MCP tools
testmcpy tools
testmcpy tools --detail --filter chart

# Research LLM capabilities
testmcpy research --model claude-sonnet-4.5-20250929 --provider anthropic

# Run test suites
testmcpy run tests/ --model claude-3-5-haiku-20241022 --provider anthropic

# Interactive chat
testmcpy chat --provider anthropic --model claude-sonnet-4.5-20250929

# Compare test results
testmcpy report reports/model1.yaml reports/model2.yaml

# Initialize new project
testmcpy init my_project
```

## Framework Structure

```
mcp_testing/
├── research/               # Research scripts for testing LLM capabilities
│   └── test_ollama_tools.py
├── src/                    # Core framework modules
│   ├── mcp_client.py      # MCP protocol client
│   ├── llm_integration.py # LLM provider abstraction
│   └── test_runner.py     # Test execution engine
├── evals/                  # Evaluation functions
│   └── base_evaluators.py # Standard evaluators
├── tests/                  # Test cases (YAML/JSON)
│   ├── basic_test.yaml
│   └── example_mcp_tests.yaml
├── reports/                # Test reports and comparisons
└── cli.py                  # CLI interface

```

## Writing Test Cases

Test cases are defined in YAML files:

```yaml
version: "1.0"
name: "My Test Suite"

tests:
  - name: "test_chart_creation"
    prompt: "Create a bar chart showing sales by region"
    expected_tools:
      - "create_chart"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"
      - name: "execution_successful"
      - name: "final_answer_contains"
        args:
          expected_content: ["chart", "created"]
      - name: "within_time_limit"
        args:
          max_seconds: 30
```

## Available Evaluators

### Generic Evaluators
- `was_mcp_tool_called` - Verify MCP tool was called
- `execution_successful` - Check for successful execution
- `final_answer_contains` - Validate response content
- `answer_contains_link` - Check for links in response
- `within_time_limit` - Verify performance
- `token_usage_reasonable` - Check token/cost efficiency

### Superset-Specific Evaluators
- `was_superset_chart_created` - Verify chart creation
- `sql_query_valid` - Validate SQL syntax

## Supported LLM Providers

### Anthropic (Recommended) ✅

The **Anthropic API** (`anthropic`) provider is recommended for most users:

```bash
# Add to ~/.testmcpy
ANTHROPIC_API_KEY=sk-ant-your-key-here
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-3-5-haiku-20241022
```

**Available Models:**
- `claude-sonnet-4.5-20250929` - Newest, most capable
- `claude-3-5-haiku-20241022` - Fast, cost-effective (recommended)
- `claude-3-5-sonnet-20241022` - Balanced performance
- All Claude models via API

**Features:**
- ✅ Full support for HTTP-based MCP services (like Superset MCP)
- ✅ Best tool calling accuracy
- ✅ Production-ready
- ✅ Simple API key setup

**Get an API key:** https://console.anthropic.com/

### Ollama (Local, Free)

For **local development** without API costs:

```bash
# 1. Install Ollama
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# 2. Start Ollama service
ollama serve

# 3. Pull a model with tool calling support
ollama pull llama3.1:8b

# 4. Configure testmcpy
# Add to ~/.testmcpy:
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b
```

**Recommended Models:**
- `llama3.1:8b` - Best tool calling support
- `mistral-nemo` - Good alternative
- `qwen2.5:7b` - Fast, smaller model

**Note:** Requires Ollama running locally. Not recommended for production testing (less reliable tool calling than Claude).

### OpenAI

```bash
# Add to ~/.testmcpy
OPENAI_API_KEY=sk-your-key-here
DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4-turbo
```

### Other Providers

- **Claude Agent SDK** (`claude-sdk`) - ⚠️ Only for stdio-based MCP servers (not HTTP)
- **Local** (`local`) - Transformers-based local models
- **Claude CLI** (`claude-cli`) - Uses Claude Code binary

## Configuration

testmcpy uses a multi-layer configuration system with clear priority ordering:

**Priority Order (highest to lowest):**
1. Command-line options
2. `.env` file in current directory
3. `~/.testmcpy` user configuration file
4. Environment variables
5. Built-in defaults

### First-Time Setup

Create your user configuration file with helpful comments:

```bash
testmcpy setup
```

This creates `~/.testmcpy` with examples for all configuration options. Edit the file to add your API keys and preferences.

### View Current Configuration

```bash
testmcpy config-cmd
```

This displays all configuration values with their sources and checks which config files exist.

### Configuration Files

#### User Config: `~/.testmcpy`

Create with `testmcpy setup`, or manually create `~/.testmcpy` to set your personal defaults:

```bash
# MCP Service Configuration
MCP_URL=http://localhost:5008/mcp/

# Option 1: Static Bearer Token
MCP_AUTH_TOKEN=your_token_here

# Option 2: Dynamic JWT Token (for Preset/Superset)
# MCP_AUTH_API_URL=https://api.app.preset.io/v1/auth/
# MCP_AUTH_API_TOKEN=your_preset_api_token
# MCP_AUTH_API_SECRET=your_preset_api_secret

# Default LLM Settings
DEFAULT_MODEL=claude-3-5-haiku-20241022
DEFAULT_PROVIDER=anthropic

# API Keys
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

See [`.testmcpy.example`](.testmcpy.example) for a complete example with detailed comments.

#### Project Config: `.env`

Create `.env` in your project directory to override user defaults:

```bash
# Project-specific settings
MCP_URL=https://my-project.mcp.example.com/mcp/
MCP_AUTH_TOKEN=project_specific_token
DEFAULT_MODEL=claude-sonnet-4.5-20250929
```

### Authentication Options

testmcpy supports two methods for MCP authentication:

**1. Static Bearer Token** (simplest):
```bash
MCP_AUTH_TOKEN=your_bearer_token
```

**2. Dynamic JWT Generation** (for Preset/Superset):

Instead of manually managing JWT tokens, configure API credentials and testmcpy will automatically fetch and cache JWT tokens:

```bash
MCP_AUTH_API_URL=https://api.app.preset.io/v1/auth/
MCP_AUTH_API_TOKEN=your_api_token
MCP_AUTH_API_SECRET=your_api_secret
```

When configured, testmcpy will:
- Call the auth API with your credentials
- Extract the JWT access token from the response
- Cache the token for 50 minutes (tokens typically expire in 1 hour)
- Automatically refresh when needed

**Note:** Static `MCP_AUTH_TOKEN` takes priority. If both are configured, the static token is used.

### Environment Variables

All configuration keys can also be set via environment variables:

```bash
# For Claude providers
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI provider
export OPENAI_API_KEY="sk-..."

# MCP service
export MCP_URL="http://localhost:5008/mcp/"
export MCP_AUTH_TOKEN="your_token"

# Or use dynamic token generation
export MCP_AUTH_API_URL="https://api.app.preset.io/v1/auth/"
export MCP_AUTH_API_TOKEN="your_api_token"
export MCP_AUTH_API_SECRET="your_api_secret"

# Default LLM settings
export DEFAULT_MODEL="claude-sonnet-4.5-20250929"
export DEFAULT_PROVIDER="anthropic"
```

## Development Status

### Phase 0: Research & Prototype ✅
- [x] Research local LLM options with tool calling
- [x] Build minimal Python script for LLM+MCP integration
- [x] Validate tool calling with selected LLM
- [x] Create basic framework structure

### Phase 1: Foundation (In Progress)
- [x] CLI framework with typer + rich
- [x] Basic test execution engine
- [x] MCP protocol client
- [x] LLM provider abstraction
- [x] Core evaluation functions
- [ ] Integration with existing Superset tests

### Phase 2: Core Features (Planned)
- [ ] Multi-model comparison support
- [ ] Advanced reporting with charts
- [ ] Test suite versioning
- [ ] Parallel test execution

### Phase 3: Advanced Capabilities (Future)
- [ ] CI/CD integration
- [ ] Interactive test development mode
- [ ] Performance profiling
- [ ] Cost optimization insights

## Known Limitations

- **Claude SDK Provider**: Only supports stdio-based MCP servers (command-line tools)
  - **Not compatible** with HTTP-based MCP services (like Superset MCP)
  - Use `anthropic` provider for HTTP MCP services
- **HTTP MCP Services**: Use `anthropic` provider (fully supported)
- **Ollama models**: Require specific formatting for reliable tool calling
- **CPU-only execution**: May be slow for larger local models
- **Tool calling accuracy**: Varies by model (Claude models generally most reliable)
- **Cost**: Claude API providers (`anthropic`) incur API costs; consider using Ollama for development

## Contributing

This framework follows the patterns established by promptimize and superset-sup. When contributing:

1. Use modern Python practices (type hints, async/await)
2. Follow the existing code style
3. Add tests for new evaluators
4. Document new features in this README

## License

Same as the parent promptimize project.