# Quick Start Guide

Get started with testmcpy in minutes.

## Installation

### Basic Installation

```bash
# Install base package
pip install testmcpy

# With web UI support
pip install 'testmcpy[server]'

# All optional features
pip install 'testmcpy[all]'
```

### Requirements

- Python 3.9 - 3.12
- Virtual environment (recommended)
- An LLM API key (Anthropic, OpenAI, or local Ollama)

## First-Time Setup

### 1. Interactive Configuration

```bash
testmcpy setup
```

This wizard will guide you through:
- Selecting your LLM provider (Anthropic, OpenAI, or Ollama)
- Configuring your MCP service URL
- Setting up authentication
- Testing your connection

### 2. Manual Configuration

Create `~/.testmcpy` file:

```bash
# MCP Service
MCP_URL=http://localhost:5008/mcp/
MCP_AUTH_TOKEN=your_bearer_token

# LLM Provider - Choose one:
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...

# Or use OpenAI:
# DEFAULT_PROVIDER=openai
# DEFAULT_MODEL=gpt-4-turbo
# OPENAI_API_KEY=sk-...

# Or use Ollama (free, local):
# DEFAULT_PROVIDER=ollama
# DEFAULT_MODEL=llama3.1:8b
```

### 3. Verify Setup

```bash
# Check configuration
testmcpy config-cmd

# Test MCP connection
testmcpy tools

# Diagnose issues
testmcpy doctor
```

## Your First Test

### 1. Explore Available Tools

```bash
testmcpy tools
```

This lists all tools available from your MCP service.

### 2. Interactive Testing

```bash
testmcpy chat
```

Chat with your MCP service to understand how the LLM interacts with tools.

### 3. Automated Testing

Create your first test file `tests/my_first_test.yaml`:

```yaml
version: "1.0"
name: "My First Test"
description: "Testing basic MCP tool calling"

tests:
  - name: "test_tool_discovery"
    prompt: "What tools are available?"
    timeout: 10
    evaluators:
      - name: "execution_successful"

  - name: "test_basic_operation"
    prompt: "List all items"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_items"  # Replace with your tool name
      - name: "execution_successful"
```

Run the test:

```bash
testmcpy run tests/my_first_test.yaml
```

### 4. View Results

Tests will show:
- Which tools were called
- Whether evaluations passed
- Execution time and token usage
- Cost information

Example output:
```
Running Test Suite: My First Test
==================================================

Test: test_tool_discovery
Status: PASS
Duration: 2.3s
Tokens: 245 | Cost: $0.001

Test: test_basic_operation
Status: PASS
Tool Called: list_items
Duration: 3.1s
Tokens: 312 | Cost: $0.002

==================================================
Results: 2/2 tests passed (100.0%)
Total Time: 5.4s
Total Cost: $0.003
```

## Using the Web Interface

Launch the optional web UI:

```bash
pip install 'testmcpy[server]'
testmcpy serve
```

Open http://localhost:8000 to access:
- Visual MCP tool explorer
- Interactive chat interface
- Test management
- Real-time results

## Common Commands

```bash
# List available tools
testmcpy tools

# Run tests
testmcpy run tests/

# Run specific test file
testmcpy run tests/my_test.yaml

# Run with different model
testmcpy run tests/ --model claude-sonnet-4-5

# Interactive chat
testmcpy chat

# Start web UI
testmcpy serve

# View configuration
testmcpy config-cmd

# Show help
testmcpy --help
```

## Next Steps

- [Installation Guide](installation.md) - Detailed installation options
- [Development Guide](development.md) - Setting up for development
- [Architecture Overview](architecture.md) - Understanding how testmcpy works
- [Configuration Guide](configuration.md) - Advanced configuration options
- [Evaluator Reference](../api/evaluators.md) - All available evaluators
- [Example Tests](../examples/basic-test.md) - More test examples

## Quick Tips

1. **Start with simple tests**: Test basic tool selection before complex workflows
2. **Use verbose mode**: Add `--verbose` to see detailed execution logs
3. **Try different models**: Compare results with `--model` flag
4. **Check costs**: Monitor token usage and costs in output
5. **Use local models**: Try Ollama for free development testing

## Troubleshooting

### Installation Issues

```bash
# Verify Python version
python --version  # Should be 3.9-3.12

# Use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

### Connection Issues

```bash
# Check configuration
testmcpy config-cmd

# Test MCP connection
testmcpy tools

# Run diagnostics
testmcpy doctor
```

### Test Failures

```bash
# Run with verbose output
testmcpy run tests/ --verbose

# Check what tools were called
testmcpy run tests/my_test.yaml --verbose | grep "Tool"
```

## Getting Help

- [Documentation](../index.md) - Full documentation
- [GitHub Issues](https://github.com/preset-io/testmcpy/issues) - Report bugs
- [GitHub Discussions](https://github.com/preset-io/testmcpy/discussions) - Ask questions
