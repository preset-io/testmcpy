<p align="center">
  <img src="docs/logos/logo.svg" alt="testmcpy logo" width="600">
</p>

<p align="center">
  <strong>Test and benchmark LLMs with MCP tools in minutes.</strong>
</p>

<p align="center">
  A testing framework for validating how LLMs call tools via Model Context Protocol (MCP) - compare Claude, GPT-4, Llama, and other models' accuracy, cost, and performance.
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://pypi.org/project/testmcpy/"><img src="https://img.shields.io/badge/pypi-testmcpy-blue" alt="PyPI"></a>
</p>

<!-- TODO: Take screenshot of CLI running tests with colorful output -->
![CLI Test Runner](context/images/cli-test-runner.png)

<!-- TODO: Take screenshot of Web UI MCP Explorer page showing tools list -->
![Web UI Explorer](context/images/web-ui-explorer.png)

---

**[Documentation](context/)** • **[Examples](examples/)** • **[Contributing](CONTRIBUTING.md)** • **[Discussions](https://github.com/preset-io/testmcpy/discussions)**

---

## Why testmcpy?

- **Validate tool calling**: Ensure LLMs call the right tools with correct parameters
- **Compare models**: Find the best price/performance balance for your use case
- **Prevent regressions**: Catch breaking changes in your MCP service with CI/CD
- **Optimize costs**: Track token usage and identify the most cost-effective models

## Quick Start

```bash
# Install testmcpy
pip install testmcpy

# Run interactive setup
testmcpy setup

# Start testing
testmcpy chat                     # Interactive chat with MCP tools
testmcpy research                 # Test LLM tool-calling capabilities
testmcpy run tests/              # Run your test suite
```

That's it! No complex configuration needed to get started.

## Key Features

### Interactive TUI Dashboard (NEW!)
Beautiful terminal interface for MCP testing - no browser required:

```bash
testmcpy dash                    # Launch interactive dashboard
testmcpy dash --auto-refresh     # Live connection monitoring
testmcpy dash --profile prod     # Use specific MCP profile
```

**TUI Features:**
- Real-time MCP connection status
- Interactive tool exploration
- Live test execution with progress
- Configuration editor
- Global search across tools, tests, and settings
- Help system with keyboard shortcuts (press `?`)
- Multiple themes (default, light, high contrast)

**Quick CLI Commands (no TUI):**
```bash
testmcpy profiles                # List MCP profiles (table)
testmcpy status                  # Connection status check
testmcpy explore-cli             # Browse tools (non-interactive)
```

<!-- TODO: Take screenshot of TUI dashboard (testmcpy dash) showing home screen -->
![TUI Dashboard](context/images/tui-dashboard.png)

### Multi-Provider Support
Test with **Claude**, **GPT-4**, **Llama**, and other models. Works with both paid APIs and free local models via Ollama.

<!-- TODO: Take screenshot of LLM provider selection in Web UI or TUI -->
![Model Selector](context/images/model-selector.png)

### Built-in Evaluators
Comprehensive validation out of the box:
- **Tool Selection**: Did the LLM call the right tool?
- **Parameter Validation**: Were correct parameters passed?
- **Execution Success**: Did the tool call complete without errors?
- **Performance**: Response time and token usage tracking
- **Cost Analysis**: Monitor API costs across test runs

<!-- TODO: Take screenshot of test results in Reports page or CLI output -->
![Test Results](context/images/test-results.png)

### Beautiful CLI & Web UI
- **Rich terminal UI**: Progress bars, colored output, formatted tables
- **Optional web interface**: Visual tool explorer and interactive chat
- **Real-time feedback**: Watch tests execute with live updates

When you start testmcpy, you're greeted with a beautiful terminal interface:

```
  ▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█
   █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █

  🧪 Test  •  📊 Benchmark  •  ✓ Validate
  MCP Testing Framework
```

<!-- TODO: Take screenshot of CLI startup banner or chat interface -->
![CLI Interface](context/images/cli-interface.png)

### YAML Test Definitions
Define test suites as code for repeatable, version-controlled testing:

```yaml
version: "1.0"
name: "Chart Operations Test Suite"

tests:
  - name: "test_create_chart"
    prompt: "Create a bar chart showing sales by region"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"
      - name: "execution_successful"
```

## Use Cases

Perfect for:

- **LLM Benchmarking**: Compare tool-calling accuracy across Claude, GPT-4, and Llama
- **MCP Service Testing**: Validate your MCP integrations work correctly
- **Regression Prevention**: Catch breaking changes in CI/CD pipelines
- **Model Selection**: Make data-driven decisions about which LLM to use
- **Cost Optimization**: Find the best price/performance balance for your workload
- **Parameter Validation**: Ensure LLMs pass correct parameters to your tools

## Architecture

testmcpy connects your LLM provider to your MCP service and validates the interactions:

```mermaid
graph TB
    subgraph "CLI Interface"
        CLI[testmcpy CLI]
        WebUI[Web UI - Optional]
    end

    subgraph "Core Framework"
        TestRunner[Test Runner]
        Evaluators[Evaluators]
        Config[Configuration Manager]
    end

    subgraph "LLM Providers"
        Anthropic[Anthropic API]
        OpenAI[OpenAI API]
        Ollama[Ollama Local]
    end

    subgraph "MCP Integration"
        MCPClient[MCP Client]
        MCPService[MCP Service<br/>HTTP/SSE]
    end

    CLI --> TestRunner
    WebUI --> TestRunner
    TestRunner --> Config
    TestRunner --> Evaluators
    TestRunner --> Anthropic
    TestRunner --> OpenAI
    TestRunner --> Ollama
    Anthropic --> MCPClient
    OpenAI --> MCPClient
    Ollama --> MCPClient
    MCPClient --> MCPService

    style CLI fill:#4A90E2
    style WebUI fill:#4A90E2
    style TestRunner fill:#50E3C2
    style MCPClient fill:#F5A623
    style MCPService fill:#BD10E0
```

**How it works:**
1. Define test cases in YAML with prompts and expected behavior
2. testmcpy sends prompts to your chosen LLM (Claude, GPT-4, Llama, etc.)
3. LLM calls tools via MCP protocol to your service
4. Evaluators validate tool selection, parameters, execution, and performance
5. Get detailed pass/fail results with metrics and cost analysis

## Installation

```bash
# Install base package
pip install testmcpy

# With web UI support
pip install 'testmcpy[server]'

# All optional features
pip install 'testmcpy[all]'
```

**Requirements:** Python 3.9-3.12 (3.13+ not yet supported)

## Getting Started

### 1. Configuration

Run the interactive setup wizard to create configuration files:

```bash
testmcpy setup
```

This will guide you through:
- **LLM Provider setup**: Choose between Claude (Anthropic), GPT-4 (OpenAI), or local Ollama models
- **MCP Service setup**: Configure your MCP server URL and authentication
- **API Key management**: Detects keys from environment and saves them to `.llm_providers.yaml`

The setup command creates two files in your current directory:

**`.llm_providers.yaml`** - LLM configuration with API keys:

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

**`.mcp_services.yaml`** - MCP server profiles:

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

**Configuration priority:** CLI options > LLM Profile (.llm_providers.yaml) > MCP Profile (.mcp_services.yaml) > `.env` > Environment variables

**Note:** The setup command is **idempotent** - it's safe to run multiple times. Use `--force` to overwrite existing files.

### 2. Test Your MCP Service

```bash
# List available MCP tools
testmcpy tools

# Interactive chat to explore your tools
testmcpy chat

# Run automated research on tool-calling capabilities
testmcpy research --model claude-haiku-4-5
```

### 3. Create Test Suites

Define tests in YAML (`tests/my_tests.yaml`):

```yaml
version: "1.0"
name: "My MCP Service Tests"

tests:
  - name: "test_tool_selection"
    prompt: "Create a bar chart showing sales by region"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"
      - name: "execution_successful"
      - name: "within_time_limit"
        args:
          max_seconds: 30
```

Run your tests:

```bash
testmcpy run tests/ --model claude-haiku-4-5
```

## Documentation

### Core Guides
- **[Evaluator Reference](context/concepts/evaluators.md)** - All available evaluators and usage examples
- **[Architecture](context/concepts/architecture.md)** - System design and data flow
- **[MCP Profiles](context/concepts/mcp-profiles.md)** - Managing multiple MCP service configurations

### Examples
- **[Basic Tests](examples/)** - Simple test cases to get started
- **[CI/CD Integration](examples/ci-cd/)** - GitHub Actions and GitLab CI configurations
- **[Custom Evaluators](examples/)** - Building your own validation logic

### Commands Reference

| Command | Description |
|---------|-------------|
| `testmcpy dash` | **Launch interactive TUI dashboard** |
| `testmcpy setup` | Interactive configuration wizard |
| `testmcpy profiles` | List MCP profiles (table) |
| `testmcpy status` | Show MCP connection status |
| `testmcpy explore-cli` | Browse tools (non-interactive) |
| `testmcpy explorer` | Launch TUI tool explorer |
| `testmcpy tools` | List available MCP tools |
| `testmcpy research` | Test LLM tool-calling capabilities |
| `testmcpy run <path>` | Execute test suite |
| `testmcpy chat` | Interactive chat with MCP tools |
| `testmcpy serve` | Start web UI server |
| `testmcpy report` | Compare test results across models |
| `testmcpy config-cmd` | View current configuration |
| `testmcpy doctor` | Diagnose installation issues |

### TUI Keyboard Shortcuts

**Global Navigation:**
- `h` - Home screen
- `e` - Explorer (MCP tools)
- `5` - Configuration
- `?` - Help modal
- `/` - Global search
- `q` - Quit (with confirmation)
- `F5` - Refresh

**Home Screen:**
- `1-5` - Quick actions (Tests, Explorer, Chat, Optimize, Config)
- `p` - Switch profile
- `Space` - Connect/disconnect

**Explorer:**
- `↑↓` or `j/k` - Navigate
- `Enter` - View details
- `t` - Create test
- `o` - Optimize docs

**Configuration:**
- `Tab` - Next field
- `s` - Save changes
- `q` - Quit without saving

## LLM Providers

Configure LLM providers in `.llm_providers.yaml`. See `.llm_providers.yaml.example` for examples.

### Anthropic (Recommended)
Best tool-calling accuracy, native MCP support:

```bash
# Set API key in .env or ~/.testmcpy
ANTHROPIC_API_KEY=sk-ant-your-key
```

```yaml
# Configure in .llm_providers.yaml
prod:
  name: "Production"
  providers:
    - name: "Claude Sonnet 4.5"
      provider: "anthropic"
      model: "claude-sonnet-4-5"
      api_key_env: "ANTHROPIC_API_KEY"
      default: true
```

**Available models:** `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-1`

### Ollama (Free, Local)
Perfect for development without API costs:

```bash
# Install Ollama
brew install ollama  # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama and pull a model
ollama serve
ollama pull llama3.1:8b
```

```yaml
# Configure in .llm_providers.yaml
local:
  name: "Local Only"
  providers:
    - name: "Ollama Llama"
      provider: "ollama"
      model: "llama3.1:8b"
      base_url: "http://localhost:11434"
      default: true
```

### OpenAI
```bash
# Set API key in .env or ~/.testmcpy
OPENAI_API_KEY=sk-your-key
```

```yaml
# Configure in .llm_providers.yaml
openai:
  name: "OpenAI"
  providers:
    - name: "GPT-4"
      provider: "openai"
      model: "gpt-4-turbo"
      api_key_env: "OPENAI_API_KEY"
      default: true
```

## Built-in Evaluators

testmcpy includes comprehensive evaluators for validating LLM behavior:

### Tool Calling
- `was_mcp_tool_called` - Verify specific tool was invoked
- `tool_call_count` - Validate number of tool calls
- `tool_called_with_parameter` - Check specific parameter was passed
- `tool_called_with_parameters` - Validate multiple parameters
- `parameter_value_in_range` - Ensure numeric parameters are valid

### Execution
- `execution_successful` - Check for errors or failures
- `within_time_limit` - Performance validation
- `final_answer_contains` - Validate response content

### Cost & Performance
- `token_usage_reasonable` - Cost efficiency validation
- Performance metrics automatically tracked

**Extensible:** Easily add custom evaluators for your domain-specific needs.

See **[Evaluator Reference](context/concepts/evaluators.md)** for complete documentation.

## For MCP Service Developers

Integrate testmcpy into your MCP service for automated testing:

```bash
# Install testmcpy in your project
pip install testmcpy[all]

# Create tests for your MCP tools
cat > tests/my_service_tests.yaml <<EOF
version: "1.0"
name: "My MCP Service Tests"
tests:
  - name: "test_tool_selection"
    prompt: "List all items"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_items"
      - name: "execution_successful"
EOF

# Run tests in CI/CD
testmcpy run tests/ --model claude-haiku-4-5
```

**[Getting Started Guide](context/guides/getting-started.md)** - Complete integration guide for your MCP service

**[CI/CD Examples](examples/ci-cd/)** - GitHub Actions and GitLab CI configurations

## Web Interface

Optional React-based UI for visual testing:

<!-- TODO: Take screenshot of Web UI dashboard showing MCP tools explorer -->
![Web UI Dashboard](context/images/web-ui-dashboard.png)

```bash
# Install with UI support
pip install 'testmcpy[server]'

# Start server
testmcpy serve
```

Features:
- Visual MCP tool explorer
- Interactive chat interface
- Test management and execution
- Real-time results display

Access at `http://localhost:8000`

## Examples

Check out the `examples/` directory for:

- **Basic test suites** - Simple examples to get started
- **CI/CD integration** - GitHub Actions and GitLab CI workflows
- **Custom evaluators** - Building domain-specific validation
- **Multi-model comparison** - Benchmarking different LLMs

## Contributing

We welcome contributions! Whether it's bug reports, feature requests, documentation improvements, or code contributions.

**[Read the Contributing Guide](CONTRIBUTING.md)** to get started.

Quick guidelines:
- Follow Black code formatting (100 char line length)
- Add tests for new features
- Ensure multi-provider compatibility (test with Ollama, Claude, GPT)
- Document your changes
- Be respectful and collaborative

## Contributors

Built with contributions from:

<!-- Add contributor images here when ready -->

Want to see your name here? Check out our [Contributing Guide](CONTRIBUTING.md)!

## Community & Support

- **Issues**: [Report bugs or request features](https://github.com/preset-io/testmcpy/issues)
- **Discussions**: [Ask questions and share ideas](https://github.com/preset-io/testmcpy/discussions)
- **Documentation**: Browse the [context/](context/) directory
- **Examples**: Explore [examples/](examples/) for sample code

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

By contributing, you agree that your contributions will be licensed under Apache 2.0.

---

## Acknowledgments

Built to enable better LLM testing and integration with Model Context Protocol services.

Special thanks to the MCP community and all our contributors!
