# Client Usage Guide: Testing Your MCP Service with testmcpy

> **Note**: This documentation has moved to [examples/ci-cd-integration.md](examples/ci-cd-integration.md). This file is kept for backward compatibility but may be removed in a future version. Please update your bookmarks.

This guide shows how to use `testmcpy` to test your MCP service from a separate test repository or within your MCP service repo.

## Table of Contents

- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Writing Tests](#writing-tests)
- [Running Tests Locally](#running-tests-locally)
- [CI/CD Integration](#cicd-integration)
- [Advanced Evaluators](#advanced-evaluators)

## Quick Start

### 1. Install testmcpy

In your test repository or MCP service repo:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install testmcpy
pip install testmcpy

# Or install with all features
pip install 'testmcpy[all]'
```

### 2. Configure testmcpy

Create a `.env` file in your project root:

```bash
# MCP Service Configuration
MCP_URL=http://localhost:5008/mcp/
MCP_AUTH_TOKEN=your_bearer_token_here

# LLM Provider (choose one)
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Or use OpenAI
# DEFAULT_PROVIDER=openai
# DEFAULT_MODEL=gpt-4-turbo
# OPENAI_API_KEY=sk-your-key-here

# Or use Ollama (free, local)
# DEFAULT_PROVIDER=ollama
# DEFAULT_MODEL=llama3.1:8b
```

**Security Note:** Never commit `.env` files to git. Add to `.gitignore`:

```bash
echo ".env" >> .gitignore
```

### 3. Create Your First Test

Create `tests/basic_functionality.yaml`:

```yaml
version: "1.0"
name: "Basic MCP Service Tests"
description: "Tests core functionality of your MCP service"

tests:
  - name: "test_tool_discovery"
    prompt: "What tools are available?"
    timeout: 10
    evaluators:
      - name: "execution_successful"

  - name: "test_basic_query"
    prompt: "List all available items"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_items"  # Replace with your tool name
      - name: "execution_successful"
```

### 4. Run Tests

```bash
# Run all tests
testmcpy run tests/ --model claude-haiku-4-5

# Run specific test file
testmcpy run tests/basic_functionality.yaml

# Run with verbose output
testmcpy run tests/ --verbose

# Run with specific model
testmcpy run tests/ --model gpt-4-turbo --provider openai
```

## Project Structure

### Option A: Separate Test Repository

Recommended for testing third-party MCP services or keeping tests isolated:

```
my-mcp-service-tests/
├── .env                          # Configuration (not committed)
├── .env.example                  # Example configuration
├── .gitignore                    # Ignore .env, venv, etc.
├── requirements.txt              # Python dependencies
├── README.md                     # Test documentation
├── .github/
│   └── workflows/
│       └── test.yml              # CI/CD workflow
├── tests/
│   ├── basic_functionality.yaml
│   ├── advanced_features.yaml
│   ├── parameter_validation.yaml
│   └── edge_cases.yaml
└── reports/                      # Test results (gitignored)
    └── .gitkeep
```

**requirements.txt:**
```txt
testmcpy[all]>=0.2.0
```

### Option B: Tests Within MCP Service Repository

Recommended if you own/maintain the MCP service:

```
my-mcp-service/
├── src/                          # Your MCP service code
│   └── ...
├── mcp_tests/                    # testmcpy tests
│   ├── .env.example
│   ├── tests/
│   │   ├── basic_functionality.yaml
│   │   └── parameter_validation.yaml
│   └── README.md
├── .github/
│   └── workflows/
│       ├── service-tests.yml     # Your service's unit tests
│       └── mcp-integration-tests.yml  # testmcpy integration tests
└── requirements-test.txt         # Include testmcpy
```

## Writing Tests

### Basic Test Structure

```yaml
version: "1.0"
name: "Test Suite Name"
description: "Description of what this suite tests"

tests:
  - name: "test_descriptive_name"
    prompt: "Natural language instruction for the LLM"
    timeout: 15  # seconds
    evaluators:
      - name: "evaluator_name"
        args:
          param1: value1
          param2: value2
```

### Common Test Patterns

#### 1. Tool Selection Test

Verify LLM chooses the correct tool:

```yaml
- name: "test_correct_tool_selection"
  prompt: "List all datasets"
  timeout: 10
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_datasets"
    - name: "execution_successful"
```

#### 2. Parameter Validation Test

Check that specific parameters are passed correctly:

```yaml
- name: "test_parameter_values"
  prompt: "Show me 20 items sorted by name"
  timeout: 15
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_items"
    - name: "tool_called_with_parameter"
      args:
        tool_name: "list_items"
        parameter_name: "limit"
        parameter_value: 20
    - name: "tool_called_with_parameter"
      args:
        tool_name: "list_items"
        parameter_name: "sort_by"
        parameter_value: "name"
    - name: "execution_successful"
```

#### 3. Multi-Tool Workflow Test

Verify LLM can chain multiple tools:

```yaml
- name: "test_multi_step_workflow"
  prompt: "First list all users, then get details for user ID 123"
  timeout: 30
  evaluators:
    - name: "tool_call_count"
      args:
        min_count: 2
        max_count: 2
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_users"
    - name: "was_mcp_tool_called"
      args:
        tool_name: "get_user_details"
    - name: "execution_successful"
```

#### 4. Error Handling Test

Test graceful handling of invalid inputs:

```yaml
- name: "test_invalid_input_handling"
  prompt: "Get user with ID -999"
  timeout: 15
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "get_user"
    # Note: We don't use execution_successful here as we expect an error
    - name: "final_answer_contains"
      args:
        expected_content: ["not found", "invalid", "error"]
```

## Running Tests Locally

### Basic Commands

```bash
# Run all tests in directory
testmcpy run tests/

# Run specific test file
testmcpy run tests/basic_functionality.yaml

# Run with verbose output to see tool calls and responses
testmcpy run tests/ --verbose

# Run with different model
testmcpy run tests/ --model claude-sonnet-4-5

# Run with cost tracking
testmcpy run tests/ --verbose  # Cost shown in output
```

### Testing During Development

```bash
# Terminal 1: Run your MCP service
./run-mcp-service.sh

# Terminal 2: Run testmcpy tests
testmcpy run tests/basic_functionality.yaml --verbose
```

### Comparing Models

Test how different LLMs perform with your MCP tools:

```bash
# Test with Claude Haiku (fast, cheap)
testmcpy run tests/ --model claude-haiku-4-5 --provider anthropic

# Test with GPT-4 (more expensive, potentially better)
testmcpy run tests/ --model gpt-4-turbo --provider openai

# Test with local Llama (free, no API costs)
testmcpy run tests/ --model llama3.1:8b --provider ollama

# Generate comparison report
testmcpy report reports/
```

## CI/CD Integration

### GitHub Actions

Create `.github/workflows/mcp-tests.yml`:

```yaml
name: MCP Integration Tests

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main]
  schedule:
    # Run daily at 2 AM UTC
    - cron: '0 2 * * *'

jobs:
  test-mcp-service:
    runs-on: ubuntu-latest

    services:
      # If your MCP service runs as a container
      mcp-service:
        image: your-org/mcp-service:latest
        ports:
          - 5008:5008
        env:
          DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install testmcpy[all]

      - name: Wait for MCP service
        run: |
          timeout 60 bash -c 'until curl -f http://localhost:5008/health; do sleep 2; done'

      - name: Run testmcpy tests
        env:
          MCP_URL: http://localhost:5008/mcp/
          MCP_AUTH_TOKEN: ${{ secrets.MCP_AUTH_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DEFAULT_PROVIDER: anthropic
          DEFAULT_MODEL: claude-haiku-4-5
        run: |
          testmcpy run tests/ --verbose

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: reports/
          retention-days: 30
```

### Required GitHub Secrets

Add these secrets to your repository (Settings → Secrets → Actions):

- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `MCP_AUTH_TOKEN`: Bearer token for your MCP service
- `TEST_DATABASE_URL`: (if needed) Database connection for tests

### GitLab CI/CD

Create `.gitlab-ci.yml`:

```yaml
mcp-integration-tests:
  image: python:3.11

  services:
    - name: your-org/mcp-service:latest
      alias: mcp-service

  variables:
    MCP_URL: "http://mcp-service:5008/mcp/"
    DEFAULT_PROVIDER: "anthropic"
    DEFAULT_MODEL: "claude-haiku-4-5"

  before_script:
    - pip install testmcpy[all]

  script:
    - testmcpy run tests/ --verbose

  artifacts:
    when: always
    paths:
      - reports/
    expire_in: 30 days

  only:
    - main
    - merge_requests
```

## Advanced Evaluators

### Parameter Inspection

Check if specific parameters were passed:

```yaml
evaluators:
  # Check parameter exists
  - name: "tool_called_with_parameter"
    args:
      tool_name: "search_items"
      parameter_name: "query"

  # Check parameter has specific value
  - name: "tool_called_with_parameter"
    args:
      tool_name: "search_items"
      parameter_name: "query"
      parameter_value: "example search"

  # Check multiple parameters
  - name: "tool_called_with_parameters"
    args:
      tool_name: "search_items"
      parameters:
        query: "example"
        limit: 10
        sort: "relevance"
      partial_match: true  # Allow additional parameters
```

### Parameter Range Validation

Ensure parameter values are within acceptable ranges:

```yaml
evaluators:
  - name: "parameter_value_in_range"
    args:
      tool_name: "list_items"
      parameter_name: "limit"
      min_value: 1
      max_value: 100
```

### Tool Call Counting

Verify how many times tools are called:

```yaml
evaluators:
  # Exact count
  - name: "tool_call_count"
    args:
      tool_name: "get_item"
      expected_count: 1

  # Count range (useful for multi-step workflows)
  - name: "tool_call_count"
    args:
      min_count: 2
      max_count: 4

  # Count all tool calls
  - name: "tool_call_count"
    args:
      min_count: 1  # At least one tool should be called
```

### Response Content Validation

Check that responses contain expected information:

```yaml
evaluators:
  - name: "final_answer_contains"
    args:
      expected_content:
        - "dataset"
        - "created"
      case_sensitive: false

  - name: "answer_contains_link"
    args:
      expected_links:
        - "https://your-app.com"
```

### Performance & Cost Limits

Set boundaries for execution time and token usage:

```yaml
evaluators:
  - name: "within_time_limit"
    args:
      max_seconds: 10

  - name: "token_usage_reasonable"
    args:
      max_tokens: 5000
      max_cost: 0.05
```

## Best Practices

### 1. Test Organization

- **Group related tests**: Keep tests for similar functionality together
- **Use descriptive names**: Test names should clearly indicate what they test
- **Start simple**: Basic tool selection tests before complex workflows

### 2. Test Coverage

Ensure you test:
- ✅ Tool selection (does LLM choose the right tool?)
- ✅ Parameter mapping (are parameters correctly inferred?)
- ✅ Required vs optional parameters
- ✅ Error handling (invalid inputs, missing parameters)
- ✅ Multi-step workflows (tool chaining)
- ✅ Edge cases (empty results, large datasets, etc.)

### 3. Environment Management

```bash
# Use environment-specific configs
cp .env.example .env.dev
cp .env.example .env.ci

# Load appropriate config
export ENV_FILE=.env.dev
testmcpy run tests/
```

### 4. Cost Management

```bash
# Use cheaper models for development
DEFAULT_MODEL=claude-haiku-4-5  # Fast & cheap

# Use better models for critical tests
DEFAULT_MODEL=claude-sonnet-4-5  # More accurate

# Use local models for frequent testing
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.1:8b  # Free!
```

### 5. Debugging Failed Tests

```bash
# Run with verbose output
testmcpy run tests/failing_test.yaml --verbose

# Check what tools were called
testmcpy run tests/failing_test.yaml --verbose | grep "Tool Calls"

# Verify MCP service is responding
testmcpy tools  # List available tools

# Test in interactive mode
testmcpy chat  # Chat with your MCP service
```

## Example: Complete Test Suite

Here's a complete example for a hypothetical "Library MCP Service":

```yaml
version: "1.0"
name: "Library MCP Service - Full Test Suite"
description: "Comprehensive tests for the Library MCP service"

tests:
  # Basic functionality
  - name: "test_list_books"
    prompt: "Show me all available books"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_books"
      - name: "execution_successful"

  # Parameter validation
  - name: "test_search_with_filters"
    prompt: "Find books by author 'Smith' published after 2020"
    timeout: 20
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "tool_called_with_parameter"
        args:
          tool_name: "search_books"
          parameter_name: "author"
          parameter_value: "Smith"
      - name: "tool_called_with_parameter"
        args:
          tool_name: "search_books"
          parameter_name: "year_from"
          parameter_value: 2020
      - name: "execution_successful"

  # Multi-step workflow
  - name: "test_checkout_workflow"
    prompt: "Find the book 'Python Programming', then check it out for user 123"
    timeout: 30
    evaluators:
      - name: "tool_call_count"
        args:
          min_count: 2
          max_count: 3
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "was_mcp_tool_called"
        args:
          tool_name: "checkout_book"
      - name: "execution_successful"

  # Error handling
  - name: "test_invalid_book_id"
    prompt: "Get details for book ID 999999"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_book_details"
      - name: "final_answer_contains"
        args:
          expected_content: ["not found", "does not exist"]

  # Performance
  - name: "test_search_performance"
    prompt: "Search for books with 'python' in the title"
    timeout: 10
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "within_time_limit"
        args:
          max_seconds: 5
      - name: "execution_successful"
```

## Troubleshooting

### Tests Not Running

```bash
# Verify installation
testmcpy --version

# Check configuration
testmcpy config-cmd

# Diagnose issues
testmcpy doctor

# Test MCP connection
testmcpy tools
```

### Rate Limiting

If you hit API rate limits:

```bash
# Use local models
DEFAULT_PROVIDER=ollama testmcpy run tests/

# Reduce test frequency
# Add delays between tests in CI (runs are already rate-limited)

# Use cheaper models
DEFAULT_MODEL=claude-haiku-4-5 testmcpy run tests/
```

### Environment Issues

```bash
# Verify Python version (3.9-3.12 supported)
python --version

# Reinstall in clean environment
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install testmcpy[all]
```

## Next Steps

- Read the [Evaluator Reference](./EVALUATOR_REFERENCE.md) for all available evaluators
- Check out [example test files](../tests/) for more patterns
- Join the [GitHub Discussions](https://github.com/preset-io/testmcpy/discussions) for help

## Support

- **Issues**: https://github.com/preset-io/testmcpy/issues
- **Discussions**: https://github.com/preset-io/testmcpy/discussions
- **Documentation**: https://github.com/preset-io/testmcpy
