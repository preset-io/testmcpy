# Test File Format Reference

Complete reference for YAML/JSON test file format.

## Overview

testmcpy test files define test cases that validate LLM tool-calling behavior. Tests are written in YAML (recommended) or JSON format.

## Basic Structure

### YAML Format (Recommended)

```yaml
version: "1.0"
name: "Test Suite Name"
description: "Description of what this suite tests"

# Optional suite-level configuration
config:
  timeout: 30
  model: "claude-haiku-4-5"
  provider: "anthropic"

# Test definitions
tests:
  - name: "test_name"
    prompt: "Natural language instruction"
    timeout: 15
    evaluators:
      - name: "evaluator_name"
        args:
          param1: value1
          param2: value2
```

### JSON Format

```json
{
  "version": "1.0",
  "name": "Test Suite Name",
  "description": "Description of what this suite tests",
  "config": {
    "timeout": 30,
    "model": "claude-haiku-4-5"
  },
  "tests": [
    {
      "name": "test_name",
      "prompt": "Natural language instruction",
      "timeout": 15,
      "evaluators": [
        {
          "name": "evaluator_name",
          "args": {
            "param1": "value1"
          }
        }
      ]
    }
  ]
}
```

## Top-Level Fields

### `version` (required)

Schema version for the test file.

```yaml
version: "1.0"
```

**Current version**: `"1.0"`

### `name` (required)

Human-readable name for the test suite.

```yaml
name: "Chart Operations Test Suite"
```

**Best practices:**
- Use descriptive names
- Include what is being tested
- Keep under 100 characters

### `description` (optional)

Detailed description of the test suite purpose.

```yaml
description: |
  Tests chart creation, modification, and deletion operations
  using the Superset MCP service.
```

### `config` (optional)

Suite-level configuration that applies to all tests.

```yaml
config:
  timeout: 30              # Default timeout in seconds
  model: "claude-haiku-4-5"  # LLM model to use
  provider: "anthropic"    # LLM provider
  concurrency: 5           # Max concurrent tests
```

**Configuration options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout` | integer | 30 | Timeout in seconds |
| `model` | string | from config | LLM model name |
| `provider` | string | from config | LLM provider |
| `concurrency` | integer | 5 | Max concurrent tests |

**Note:** Test-level settings override suite-level config.

### `tests` (required)

Array of test case definitions.

```yaml
tests:
  - name: "test_1"
    # ... test definition
  - name: "test_2"
    # ... test definition
```

## Test Case Fields

### `name` (required)

Unique identifier for the test within the suite.

```yaml
name: "test_create_chart"
```

**Best practices:**
- Use descriptive names
- Use snake_case or kebab-case
- Include action being tested
- Keep under 100 characters

**Examples:**
- `test_create_chart`
- `test_list_datasets_with_filter`
- `test_error_handling_invalid_id`

### `prompt` (required)

Natural language instruction given to the LLM.

```yaml
prompt: "Create a bar chart showing sales by region using dataset 123"
```

**Best practices:**
- Be specific and clear
- Include relevant context
- Specify expected behavior
- Avoid ambiguity

**Good examples:**

```yaml
# Specific and clear
prompt: "List all datasets filtered by the name 'sales'"

# Includes context
prompt: "Using the dataset with ID 456, create a line chart showing revenue over time"

# Specifies expected behavior
prompt: "Get details for user ID 789, then update their email to test@example.com"
```

**Bad examples:**

```yaml
# Too vague
prompt: "Do something with datasets"

# Ambiguous
prompt: "Create a chart"  # What kind? Which dataset?

# Multiple unclear actions
prompt: "List datasets, create a chart, and also check something"
```

### `timeout` (optional)

Maximum time in seconds for test execution.

```yaml
timeout: 30  # 30 seconds
```

**Default:** 30 seconds (or suite-level config)

**When to adjust:**
- **Increase** for complex multi-step workflows
- **Decrease** for simple single-tool operations
- **Increase** for external API calls
- **Keep default** for most tests

**Examples:**

```yaml
# Fast operation
- name: "test_list_items"
  timeout: 10

# Complex workflow
- name: "test_multi_step_process"
  timeout: 60

# External API integration
- name: "test_third_party_api"
  timeout: 90
```

### `evaluators` (required)

Array of evaluators to check test results.

```yaml
evaluators:
  - name: "was_mcp_tool_called"
    args:
      tool_name: "create_chart"

  - name: "execution_successful"

  - name: "within_time_limit"
    args:
      max_seconds: 30
```

**All evaluators must pass for test to pass.**

See [Evaluator Reference](evaluators.md) for complete list.

### `metadata` (optional)

Additional metadata for organizational purposes.

```yaml
metadata:
  priority: "high"
  category: "chart_operations"
  tags: ["charts", "creation", "regression"]
  jira_ticket: "PROJ-123"
  author: "john@example.com"
```

**Not used by testmcpy**, but helpful for:
- Test organization
- Filtering and reporting
- Documentation
- Integration with other tools

### `skip` (optional)

Skip this test.

```yaml
skip: true
skip_reason: "Waiting for bug fix in PROJ-456"
```

**When to skip:**
- Known failing tests (with bug ticket)
- Tests for features not yet implemented
- Environment-specific tests
- Temporarily problematic tests

### `retry` (optional)

Retry configuration for flaky tests.

```yaml
retry:
  max_attempts: 3
  backoff_multiplier: 2
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_attempts` | integer | 1 | Maximum number of attempts |
| `backoff_multiplier` | float | 1 | Multiplier for delay between retries |

**Use sparingly** - flaky tests should be fixed, not retried.

## Complete Example

```yaml
version: "1.0"
name: "Library MCP Service - Complete Test Suite"
description: |
  Comprehensive tests for the Library MCP service.
  Tests cover book management, search, and checkout workflows.

config:
  timeout: 30
  model: "claude-haiku-4-5"
  provider: "anthropic"
  concurrency: 5

tests:
  # Basic functionality
  - name: "test_list_books"
    prompt: "Show me all available books in the library"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_books"
      - name: "execution_successful"
      - name: "within_time_limit"
        args:
          max_seconds: 10
    metadata:
      priority: "high"
      category: "basic_operations"
      tags: ["books", "list"]

  # Parameter validation
  - name: "test_search_with_author_filter"
    prompt: "Find all books written by 'Jane Smith' published after 2020"
    timeout: 20
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"

      - name: "tool_called_with_parameter"
        args:
          tool_name: "search_books"
          parameter_name: "author"
          parameter_value: "Jane Smith"

      - name: "tool_called_with_parameter"
        args:
          tool_name: "search_books"
          parameter_name: "year_from"
          parameter_value: 2020

      - name: "execution_successful"

      - name: "final_answer_contains"
        args:
          expected_content: ["books", "Jane Smith"]
    metadata:
      priority: "high"
      category: "search"
      tags: ["books", "search", "filters"]

  # Multi-step workflow
  - name: "test_checkout_workflow"
    prompt: |
      Find the book titled 'The Great Gatsby', then check it out
      for user ID 12345 with a due date 14 days from now.
    timeout: 45
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

      - name: "tool_called_with_parameter"
        args:
          tool_name: "checkout_book"
          parameter_name: "user_id"
          parameter_value: 12345

      - name: "execution_successful"

      - name: "final_answer_contains"
        args:
          expected_content: ["checked out", "due date"]
    metadata:
      priority: "high"
      category: "workflows"
      tags: ["books", "checkout", "multi-step"]

  # Error handling
  - name: "test_invalid_book_id"
    prompt: "Get details for book with ID 999999 (which doesn't exist)"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_book_details"

      - name: "final_answer_contains"
        args:
          expected_content: ["not found", "does not exist", "invalid"]
    metadata:
      priority: "medium"
      category: "error_handling"
      tags: ["books", "errors", "edge_cases"]

  # Performance test
  - name: "test_search_performance"
    prompt: "Search for all books with 'python' in the title"
    timeout: 10
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"

      - name: "within_time_limit"
        args:
          max_seconds: 5

      - name: "token_usage_reasonable"
        args:
          max_tokens: 1000
          max_cost: 0.02

      - name: "execution_successful"
    metadata:
      priority: "medium"
      category: "performance"
      tags: ["books", "search", "performance"]

  # Skipped test
  - name: "test_advanced_filtering"
    skip: true
    skip_reason: "Waiting for advanced filter implementation (PROJ-789)"
    prompt: "Find books using complex multi-field filters"
    evaluators:
      - name: "execution_successful"
    metadata:
      priority: "low"
      category: "future"
      tags: ["books", "search", "advanced"]
```

## Test File Organization

### Single File

Small projects can use a single test file:

```
tests/
└── all_tests.yaml
```

### Multiple Files by Feature

Organize tests by feature or component:

```
tests/
├── basic_operations.yaml
├── search_functionality.yaml
├── checkout_workflows.yaml
├── admin_operations.yaml
└── error_handling.yaml
```

### Hierarchical Organization

Large projects can use subdirectories:

```
tests/
├── unit/
│   ├── books.yaml
│   ├── users.yaml
│   └── checkout.yaml
├── integration/
│   ├── full_workflows.yaml
│   └── api_integration.yaml
├── performance/
│   └── load_tests.yaml
└── regression/
    └── bug_fixes.yaml
```

## YAML Tips

### Multi-line Strings

Use `|` for multi-line strings:

```yaml
prompt: |
  This is a long prompt that spans
  multiple lines for readability.
  Line breaks are preserved.
```

Use `>` to fold lines:

```yaml
description: >
  This text will be folded into a single line
  with spaces replacing line breaks.
```

### Comments

```yaml
# This is a comment
tests:
  - name: "test_example"
    prompt: "Test prompt"
    evaluators:
      - name: "execution_successful"
```

### Anchors and References

Reuse configuration with YAML anchors:

```yaml
# Define reusable evaluator sets
x-common-evaluators: &common-evals
  - name: "execution_successful"
  - name: "within_time_limit"
    args:
      max_seconds: 30

tests:
  - name: "test_1"
    prompt: "First test"
    evaluators:
      <<: *common-evals  # Reuse common evaluators
      - name: "was_mcp_tool_called"
        args:
          tool_name: "specific_tool"

  - name: "test_2"
    prompt: "Second test"
    evaluators:
      <<: *common-evals  # Reuse again
```

## Validation

### Schema Validation

testmcpy validates test files against schema:

```bash
# Validate test file
testmcpy run tests/my_tests.yaml --validate-only
```

### Common Errors

**Missing required field:**

```yaml
# ❌ Missing 'name' field
tests:
  - prompt: "Test prompt"
    evaluators: []
```

**Invalid evaluator:**

```yaml
# ❌ Unknown evaluator
evaluators:
  - name: "invalid_evaluator_name"
```

**Type mismatch:**

```yaml
# ❌ timeout should be integer, not string
timeout: "30"

# ✅ Correct
timeout: 30
```

**Invalid YAML syntax:**

```yaml
# ❌ Indentation error
tests:
- name: "test"
prompt: "Test"  # Should be indented
```

## Best Practices

### 1. Test Naming

```yaml
# ✅ Good names
- name: "test_create_chart_with_valid_dataset"
- name: "test_list_items_filters_by_status"
- name: "test_error_handling_missing_parameter"

# ❌ Bad names
- name: "test1"
- name: "chart_test"
- name: "TestCreateChart"  # Don't use PascalCase
```

### 2. Test Organization

```yaml
# ✅ Group related tests
tests:
  # Basic operations
  - name: "test_list_items"
  - name: "test_get_item"
  - name: "test_search_items"

  # CRUD operations
  - name: "test_create_item"
  - name: "test_update_item"
  - name: "test_delete_item"

  # Error handling
  - name: "test_invalid_id"
  - name: "test_missing_parameter"
```

### 3. Evaluator Selection

```yaml
# ✅ Use multiple complementary evaluators
evaluators:
  # Verify correct tool called
  - name: "was_mcp_tool_called"
    args:
      tool_name: "create_item"

  # Verify parameters
  - name: "tool_called_with_parameters"
    args:
      tool_name: "create_item"
      parameters:
        name: "Test Item"
      partial_match: true

  # Verify execution
  - name: "execution_successful"

  # Verify response
  - name: "final_answer_contains"
    args:
      expected_content: ["created", "successfully"]

  # Verify performance
  - name: "within_time_limit"
    args:
      max_seconds: 30
```

### 4. Prompt Design

```yaml
# ✅ Clear, specific prompts
prompt: "List all users with admin role, sorted by creation date"

# ✅ Include context when needed
prompt: "Using dataset ID 123, create a bar chart showing monthly sales"

# ❌ Vague prompts
prompt: "Do something with users"

# ❌ Too complex (split into multiple tests)
prompt: "List users, create a report, send email, and log the activity"
```

### 5. Comments and Documentation

```yaml
tests:
  # Test basic dataset listing
  # Verifies that list_datasets tool is correctly called
  # and returns valid results
  - name: "test_list_datasets"
    prompt: "Show me all available datasets"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"
      - name: "execution_successful"
```

## Related Documentation

- [Evaluator Reference](evaluators.md) - All available evaluators
- [CLI Reference](cli.md) - Command-line options
- [Examples](../examples/basic-test.md) - Example test files
