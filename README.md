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

- **Claude Agent SDK** (`claude-sdk`) - Official Anthropic SDK ⚠️ **Limited MCP Support**
  - claude-sonnet-4.5-20250929 (newest, most capable)
  - claude-sonnet-4-20250514
  - claude-3-5-sonnet-20241022
  - claude-3-5-haiku-20241022
  - All Claude models
  - Requires: `ANTHROPIC_API_KEY` environment variable
  - Features: Native tool calling, streaming, hooks
  - **Note**: Designed for stdio-based MCP servers, **not HTTP-based services**
  - **For HTTP MCP (like Superset)**: Use `anthropic` provider instead

- **Anthropic API** (`anthropic`) - Direct API integration ✅ **Recommended for HTTP MCP**
  - claude-sonnet-4.5-20250929 (newest, recommended)
  - claude-sonnet-4-20250514
  - claude-3-5-sonnet-20241022
  - claude-3-5-haiku-20241022 (fast, cost-effective)
  - claude-3-opus-20240229
  - All Claude models via API
  - Requires: `ANTHROPIC_API_KEY` environment variable
  - **Full support for HTTP-based MCP services** (like Superset MCP)
  - Best choice for production testing with MCP tools

- **Ollama** (`ollama`) - Local models with tool calling support
  - llama3.1:8b (recommended)
  - mistral-nemo
  - qwen2.5:7b

- **OpenAI** (`openai`) - GPT models via API
  - Requires: `OPENAI_API_KEY` environment variable

- **Local** (`local`) - Transformers-based local models

- **Claude CLI** (`claude-cli`) - Claude Code CLI interface
  - Uses Claude Code binary

## Configuration

### Environment Variables

```bash
# For Claude providers (claude-sdk, anthropic)
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI provider
export OPENAI_API_KEY="sk-..."

# MCP service URL (optional, defaults to http://localhost:5008/mcp/)
export MCP_URL="http://localhost:5008/mcp/"

# Default model and provider (optional)
export DEFAULT_MODEL="claude-sonnet-4.5-20250929"
export DEFAULT_PROVIDER="anthropic"
```

### Configuration File

Create `mcp_test_config.yaml`:

```yaml
mcp_url: "http://localhost:5008/mcp"
default_model: "claude-sonnet-4.5-20250929"
default_provider: "anthropic"
evaluators:
  timeout: 30
  max_tokens: 2000
  max_cost: 0.10
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