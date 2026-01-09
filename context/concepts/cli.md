# CLI Command Reference

Complete reference for all testmcpy command-line interface commands.

## Global Options

Available for all commands:

```bash
testmcpy [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS]
```

### `--version`

Show version and exit.

```bash
testmcpy --version
```

### `--help`

Show help message.

```bash
testmcpy --help
testmcpy COMMAND --help  # Command-specific help
```

## Commands

### `setup`

Interactive configuration wizard for first-time setup.

```bash
testmcpy setup
```

**What it does:**
- Guides through configuration
- Tests MCP connection
- Validates LLM provider credentials
- Creates `~/.testmcpy` config file

**Example Session:**

```
Welcome to testmcpy setup!

LLM Provider Selection:
1. Anthropic (Claude)
2. OpenAI (GPT)
3. Ollama (Local)

Select provider [1]: 1

Enter Anthropic API key: sk-ant-***

MCP Service URL: http://localhost:5008/mcp/
MCP Auth Token: ***

Testing configuration...
✓ LLM provider connected
✓ MCP service reachable
✓ Configuration saved to ~/.testmcpy

Setup complete! Try: testmcpy tools
```

### `tools`

List available MCP tools from your service.

```bash
testmcpy tools [OPTIONS]
```

**Options:**

- `--mcp-url TEXT` - Override MCP service URL
- `--mcp-auth-token TEXT` - Override auth token
- `--profile TEXT` - Use specific MCP profile
- `--verbose` - Show detailed tool information
- `--json` - Output in JSON format

**Examples:**

```bash
# List tools using default config
testmcpy tools

# List tools from specific URL
testmcpy tools --mcp-url http://localhost:5008/mcp/

# Use profile
testmcpy tools --profile staging

# Verbose output with full tool schemas
testmcpy tools --verbose

# JSON output for scripting
testmcpy tools --json | jq '.tools[0]'
```

**Output:**

```
Available MCP Tools:
====================

Tool: list_datasets
Description: List all available datasets
Parameters:
  - limit (optional): Maximum number of datasets to return
  - filter (optional): Filter datasets by name

Tool: create_chart
Description: Create a new chart
Parameters:
  - dataset_id (required): ID of the dataset
  - chart_type (required): Type of chart (bar, line, pie)
  - title (optional): Chart title

Total: 2 tools available
```

### `research`

Test LLM tool-calling capabilities interactively.

```bash
testmcpy research [OPTIONS]
```

**Options:**

- `--model TEXT` - LLM model to use
- `--provider TEXT` - LLM provider (anthropic, openai, ollama)
- `--profile TEXT` - MCP profile to use
- `--iterations INTEGER` - Number of test iterations (default: 5)
- `--verbose` - Show detailed execution logs

**What it does:**
- Tests different prompts with your MCP tools
- Analyzes tool selection accuracy
- Measures performance and cost
- Provides recommendations

**Example:**

```bash
testmcpy research --model claude-haiku-4-5 --iterations 10
```

**Output:**

```
Testing LLM Tool-Calling Capabilities
======================================

Iteration 1/10: Testing list_datasets
✓ Correct tool selected
Time: 2.3s | Tokens: 245 | Cost: $0.001

Iteration 2/10: Testing create_chart
✓ Correct tool selected
✓ Parameters correct
Time: 3.1s | Tokens: 312 | Cost: $0.002

...

Summary:
--------
Accuracy: 9/10 (90%)
Avg Time: 2.7s
Avg Cost: $0.0015
Total Cost: $0.015

Recommendations:
- Model performs well with tool selection
- Consider claude-haiku-4-5 for production (cost-effective)
```

### `run`

Execute test suites from YAML/JSON files.

```bash
testmcpy run PATH [OPTIONS]
```

**Arguments:**

- `PATH` - Path to test file or directory

**Options:**

- `--model TEXT` - LLM model to use
- `--provider TEXT` - LLM provider
- `--profile TEXT` - MCP profile
- `--timeout INTEGER` - Timeout in seconds (default: 30)
- `--concurrency INTEGER` - Number of concurrent tests (default: 5)
- `--verbose` - Show detailed execution logs
- `--output PATH` - Save results to file
- `--format TEXT` - Output format (text, json, html, markdown)
- `--filter TEXT` - Run only tests matching pattern
- `--fail-fast` - Stop on first failure

**Examples:**

```bash
# Run all tests in directory
testmcpy run tests/

# Run specific test file
testmcpy run tests/chart_tests.yaml

# Run with specific model
testmcpy run tests/ --model claude-sonnet-4-5

# Run with different provider
testmcpy run tests/ --provider openai --model gpt-4-turbo

# Use profile
testmcpy run tests/ --profile staging

# Increase timeout for slow tests
testmcpy run tests/ --timeout 60

# Run with higher concurrency
testmcpy run tests/ --concurrency 10

# Verbose output
testmcpy run tests/ --verbose

# Save results to JSON
testmcpy run tests/ --output results.json --format json

# Run only tests matching pattern
testmcpy run tests/ --filter "test_create_*"

# Stop on first failure
testmcpy run tests/ --fail-fast
```

**Output:**

```
Running Test Suite: Chart Operations
=====================================

Test: test_create_chart
✓ PASS
  ✓ was_mcp_tool_called: create_chart was called
  ✓ execution_successful: No errors
  ✓ within_time_limit: 3.1s < 30s
  Time: 3.1s | Tokens: 312 | Cost: $0.002

Test: test_list_datasets
✓ PASS
  ✓ was_mcp_tool_called: list_datasets was called
  ✓ execution_successful: No errors
  Time: 2.3s | Tokens: 245 | Cost: $0.001

=====================================
Results: 2/2 tests passed (100.0%)
Total Time: 5.4s
Total Cost: $0.003
```

### `chat`

Interactive chat interface with MCP tools.

```bash
testmcpy chat [OPTIONS]
```

**Options:**

- `--model TEXT` - LLM model to use
- `--provider TEXT` - LLM provider
- `--profile TEXT` - MCP profile
- `--system-prompt TEXT` - Custom system prompt

**Commands in chat:**

- `/tools` - List available tools
- `/clear` - Clear conversation history
- `/cost` - Show token usage and cost
- `/help` - Show help
- `/exit` or `/quit` - Exit chat

**Example:**

```bash
testmcpy chat --model claude-haiku-4-5
```

**Session:**

```
testmcpy Chat (press Ctrl+C or type /exit to quit)
Connected to MCP service: http://localhost:5008/mcp/
Model: claude-haiku-4-5
Available tools: 5

You: List all datasets
Assistant: I'll fetch the available datasets for you.
[Tool Call: list_datasets(limit=10)]
[Tool Result: Found 3 datasets]

Here are the available datasets:
1. Sales Data (id: 123)
2. Customer Data (id: 456)
3. Inventory Data (id: 789)

You: Create a bar chart for Sales Data
Assistant: I'll create a bar chart using the Sales Data dataset.
[Tool Call: create_chart(dataset_id=123, chart_type="bar", title="Sales Chart")]
[Tool Result: Chart created successfully]

Chart created! View it here: https://example.com/charts/abc123

You: /cost
Tokens used: 1,234 | Cost: $0.006

You: /exit
Goodbye!
```

### `serve`

Start web UI server.

```bash
testmcpy serve [OPTIONS]
```

**Options:**

- `--host TEXT` - Host to bind to (default: 127.0.0.1)
- `--port INTEGER` - Port to bind to (default: 8000)
- `--reload` - Enable auto-reload for development

**Examples:**

```bash
# Start server on default port
testmcpy serve

# Bind to all interfaces
testmcpy serve --host 0.0.0.0

# Use custom port
testmcpy serve --port 3000

# Development mode with auto-reload
testmcpy serve --reload
```

**Output:**

```
Starting testmcpy Web UI...
Server running at: http://localhost:8000
Press Ctrl+C to stop
```

**Features:**
- Visual MCP tool explorer
- Interactive chat interface
- Test management and execution
- Real-time results display

### `report`

Generate comparison reports from test results.

```bash
testmcpy report [FILES...] [OPTIONS]
```

**Arguments:**

- `FILES...` - One or more result files to compare

**Options:**

- `--output PATH` - Output file path
- `--format TEXT` - Report format (html, markdown, json)
- `--open` - Open report in browser (HTML only)

**Examples:**

```bash
# Compare results from different models
testmcpy report haiku_results.json sonnet_results.json gpt4_results.json

# Generate HTML report
testmcpy report results*.json --format html --output comparison.html

# Generate and open HTML report
testmcpy report results*.json --format html --open

# Generate markdown report
testmcpy report results*.json --format markdown --output REPORT.md
```

**Report Contents:**
- Test pass/fail rates per model
- Performance comparison
- Cost comparison
- Accuracy metrics
- Detailed test breakdowns

### `config-cmd`

View current configuration.

```bash
testmcpy config-cmd [OPTIONS]
```

**Options:**

- `--verbose` - Show all configuration sources
- `--profile TEXT` - Show configuration for specific profile

**Examples:**

```bash
# Show current configuration
testmcpy config-cmd

# Verbose output with sources
testmcpy config-cmd --verbose

# Show specific profile configuration
testmcpy config-cmd --profile staging
```

**Output:**

```
Current Configuration:
======================

MCP Service:
  URL: http://localhost:5008/mcp/ (Profile: local)
  Auth: Bearer token (Environment)

LLM Provider:
  Provider: anthropic (~/.testmcpy)
  Model: claude-haiku-4-5 (~/.testmcpy)
  API Key: sk-ant-*** (~/.testmcpy)

Settings:
  Timeout: 30s (Default)
  Rate Limit: 60 req/min (Default)
  Log Level: INFO (Default)
```

### `doctor`

Diagnose installation and configuration issues.

```bash
testmcpy doctor
```

**What it checks:**

- Python version
- testmcpy installation
- Configuration file validity
- Required settings present
- API keys configured
- MCP service reachable
- LLM provider accessible
- Network connectivity
- Dependencies installed

**Example Output:**

```
testmcpy Doctor
===============

✓ Python version: 3.11.5 (supported)
✓ testmcpy version: 0.2.1
✓ Configuration file: ~/.testmcpy (valid)
✓ MCP URL configured: http://localhost:5008/mcp/
✓ MCP service reachable: OK
✓ LLM provider: anthropic
✓ API key configured: Yes
✓ LLM provider accessible: OK
✓ All dependencies installed: OK

All checks passed! testmcpy is ready to use.
```

**If issues found:**

```
testmcpy Doctor
===============

✓ Python version: 3.11.5 (supported)
✓ testmcpy version: 0.2.1
✗ Configuration file: ~/.testmcpy (missing)
  → Run 'testmcpy setup' to create configuration
✗ MCP service reachable: Connection refused
  → Check that MCP service is running
  → Verify MCP_URL is correct
✓ LLM provider: anthropic
✗ API key configured: No
  → Set ANTHROPIC_API_KEY in ~/.testmcpy

Issues found. Please address the above errors.
```

## Common Workflows

### First Time Setup

```bash
# 1. Run setup wizard
testmcpy setup

# 2. Test connection
testmcpy tools

# 3. Try interactive chat
testmcpy chat

# 4. Run tests
testmcpy run tests/
```

### Running Tests in CI/CD

```bash
# Run tests with environment variables
export MCP_URL=${{ secrets.MCP_URL }}
export MCP_AUTH_TOKEN=${{ secrets.MCP_AUTH_TOKEN }}
export ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}

testmcpy run tests/ --format json --output results.json --fail-fast
```

### Comparing Models

```bash
# Test with multiple models
testmcpy run tests/ --model claude-haiku-4-5 --output haiku.json
testmcpy run tests/ --model claude-sonnet-4-5 --output sonnet.json
testmcpy run tests/ --model gpt-4-turbo --provider openai --output gpt4.json

# Generate comparison report
testmcpy report haiku.json sonnet.json gpt4.json --format html --open
```

### Testing Different Environments

```bash
# Test local environment
testmcpy run tests/ --profile local

# Test staging
testmcpy run tests/ --profile staging

# Test production (read-only tests)
testmcpy run tests/read_only/ --profile prod
```

## Environment Variables

All options can be set via environment variables:

| Environment Variable | CLI Option | Description |
|---------------------|------------|-------------|
| `MCP_URL` | `--mcp-url` | MCP service URL |
| `MCP_AUTH_TOKEN` | `--mcp-auth-token` | MCP auth token |
| `DEFAULT_PROVIDER` | `--provider` | LLM provider |
| `DEFAULT_MODEL` | `--model` | LLM model |
| `DEFAULT_TIMEOUT` | `--timeout` | Timeout in seconds |
| `LOG_LEVEL` | - | Logging level |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `OPENAI_API_KEY` | - | OpenAI API key |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - all tests passed |
| 1 | Failure - one or more tests failed |
| 2 | Error - configuration or connection error |
| 3 | Invalid usage - incorrect command or options |

## Shell Completion

Enable shell completion for bash/zsh:

```bash
# For bash
eval "$(_TESTMCPY_COMPLETE=bash_source testmcpy)" >> ~/.bashrc

# For zsh
eval "$(_TESTMCPY_COMPLETE=zsh_source testmcpy)" >> ~/.zshrc

# For fish
eval (env _TESTMCPY_COMPLETE=fish_source testmcpy) >> ~/.config/fish/completions/testmcpy.fish
```

## Related Documentation

- [Quick Start Guide](../guide/quickstart.md) - Getting started
- [Configuration Guide](../guide/configuration.md) - Configuration options
- [Evaluator Reference](evaluators.md) - Available evaluators
- [Test Format](test-format.md) - YAML test file format
