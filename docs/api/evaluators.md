# Evaluator Reference

Complete reference for all available evaluators in testmcpy.

## Table of Contents

- [Basic Evaluators](#basic-evaluators)
- [Parameter Validation Evaluators](#parameter-validation-evaluators)
- [Content Validation Evaluators](#content-validation-evaluators)
- [Performance Evaluators](#performance-evaluators)
- [Domain-Specific Evaluators](#domain-specific-evaluators)

## Basic Evaluators

### `was_mcp_tool_called`

Checks if a specific MCP tool was called, or if any tool was called.

**Parameters:**
- `tool_name` (optional): Name of the specific tool to check for

**Examples:**

```yaml
# Check if any tool was called
- name: "was_mcp_tool_called"

# Check if specific tool was called
- name: "was_mcp_tool_called"
  args:
    tool_name: "list_datasets"
```

### `execution_successful`

Verifies that tool execution completed without errors.

**Parameters:** None

**Example:**

```yaml
- name: "execution_successful"
```

## Parameter Validation Evaluators

### `tool_called_with_parameter`

Checks if a tool was called with a specific parameter, optionally verifying the parameter's value.

**Parameters:**
- `tool_name` (required): Name of the tool
- `parameter_name` (required): Name of the parameter to check
- `parameter_value` (optional): Expected value of the parameter

**Examples:**

```yaml
# Check if parameter exists
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

# Check boolean parameter
- name: "tool_called_with_parameter"
  args:
    tool_name: "list_datasets"
    parameter_name: "force_refresh"
    parameter_value: true

# Check numeric parameter
- name: "tool_called_with_parameter"
  args:
    tool_name: "list_items"
    parameter_name: "limit"
    parameter_value: 10
```

### `tool_called_with_parameters`

Checks if a tool was called with multiple specific parameters.

**Parameters:**
- `tool_name` (required): Name of the tool
- `parameters` (required): Dictionary of parameter_name → expected_value
- `partial_match` (optional, default: false): If true, allows additional parameters beyond those specified

**Examples:**

```yaml
# Exact parameter match (no extra parameters allowed)
- name: "tool_called_with_parameters"
  args:
    tool_name: "search_books"
    parameters:
      author: "Smith"
      year: 2020
    partial_match: false

# Partial match (additional parameters allowed)
- name: "tool_called_with_parameters"
  args:
    tool_name: "list_items"
    parameters:
      sort: "name"
      order: "asc"
    partial_match: true
```

### `parameter_value_in_range`

Validates that a numeric parameter value falls within an acceptable range.

**Parameters:**
- `tool_name` (required): Name of the tool
- `parameter_name` (required): Name of the parameter
- `min_value` (optional): Minimum acceptable value (inclusive)
- `max_value` (optional): Maximum acceptable value (inclusive)

**Examples:**

```yaml
# Check parameter is within range
- name: "parameter_value_in_range"
  args:
    tool_name: "list_items"
    parameter_name: "limit"
    min_value: 1
    max_value: 100

# Check parameter is at least a certain value
- name: "parameter_value_in_range"
  args:
    tool_name: "get_user"
    parameter_name: "user_id"
    min_value: 1

# Check parameter doesn't exceed maximum
- name: "parameter_value_in_range"
  args:
    tool_name: "fetch_data"
    parameter_name: "timeout"
    max_value: 30
```

### `tool_call_count`

Verifies the number of times a tool (or all tools) was called.

**Parameters:**
- `tool_name` (optional): Specific tool to count. If omitted, counts all tool calls
- `expected_count` (optional): Exact number of calls expected
- `min_count` (optional): Minimum number of calls
- `max_count` (optional): Maximum number of calls

**Examples:**

```yaml
# Exact count for specific tool
- name: "tool_call_count"
  args:
    tool_name: "get_user"
    expected_count: 1

# Count range for any tools
- name: "tool_call_count"
  args:
    min_count: 2
    max_count: 4

# At least one tool should be called
- name: "tool_call_count"
  args:
    min_count: 1

# Specific tool called at least twice
- name: "tool_call_count"
  args:
    tool_name: "process_item"
    min_count: 2
```

## Content Validation Evaluators

### `final_answer_contains`

Checks if the LLM's final response contains expected content.

**Parameters:**
- `expected_content` (required): String or list of strings to search for
- `case_sensitive` (optional, default: false): Whether to perform case-sensitive matching

**Examples:**

```yaml
# Single string
- name: "final_answer_contains"
  args:
    expected_content: "dataset created"

# Multiple strings (all must be present)
- name: "final_answer_contains"
  args:
    expected_content:
      - "successfully"
      - "created"
      - "chart"

# Case-sensitive search
- name: "final_answer_contains"
  args:
    expected_content: "ERROR"
    case_sensitive: true
```

### `answer_contains_link`

Verifies that the response contains URL links.

**Parameters:**
- `expected_links` (optional): List of specific URL patterns to check for

**Examples:**

```yaml
# Check if any link is present
- name: "answer_contains_link"

# Check for specific links
- name: "answer_contains_link"
  args:
    expected_links:
      - "https://app.example.com/charts/"
      - "https://docs.example.com"
```

## Performance Evaluators

### `within_time_limit`

Ensures that test execution completed within a specified time limit.

**Parameters:**
- `max_seconds` (required): Maximum acceptable execution time in seconds

**Example:**

```yaml
- name: "within_time_limit"
  args:
    max_seconds: 10
```

### `token_usage_reasonable`

Validates that token usage and cost remain within acceptable limits.

**Parameters:**
- `max_tokens` (optional, default: 2000): Maximum token count
- `max_cost` (optional, default: 0.10): Maximum cost in USD

**Examples:**

```yaml
# Default limits
- name: "token_usage_reasonable"

# Custom limits
- name: "token_usage_reasonable"
  args:
    max_tokens: 5000
    max_cost: 0.25
```

## Domain-Specific Evaluators

### Superset/Preset Evaluators

#### `was_superset_chart_created`

Checks if a Superset chart was successfully created.

**Parameters:** None

**Example:**

```yaml
- name: "was_superset_chart_created"
```

#### `sql_query_valid`

Validates that generated SQL query is syntactically correct.

**Parameters:** None

**Example:**

```yaml
- name: "sql_query_valid"
```

## Composite Evaluators

### Running Multiple Evaluators

You can combine multiple evaluators in a single test. All evaluators must pass for the test to pass.

**Example:**

```yaml
tests:
  - name: "comprehensive_test"
    prompt: "Create a chart showing sales by region"
    timeout: 30
    evaluators:
      # Tool selection
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"

      # Parameter validation
      - name: "tool_called_with_parameter"
        args:
          tool_name: "create_chart"
          parameter_name: "chart_type"
          parameter_value: "bar"

      # Execution
      - name: "execution_successful"

      # Performance
      - name: "within_time_limit"
        args:
          max_seconds: 20

      # Cost
      - name: "token_usage_reasonable"
        args:
          max_tokens: 3000

      # Content
      - name: "final_answer_contains"
        args:
          expected_content:
            - "chart"
            - "created"
```

## Creating Custom Evaluators

To create your own evaluators, extend the `BaseEvaluator` class:

```python
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any

class MyCustomEvaluator(BaseEvaluator):
    """Description of what this evaluator checks."""

    def __init__(self, custom_param: str):
        self.custom_param = custom_param

    @property
    def name(self) -> str:
        return "my_custom_evaluator"

    @property
    def description(self) -> str:
        return f"Checks custom condition: {self.custom_param}"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # Access test context
        prompt = context.get("prompt")
        response = context.get("response")
        tool_calls = context.get("tool_calls", [])
        tool_results = context.get("tool_results", [])
        metadata = context.get("metadata", {})

        # Your evaluation logic here
        passed = True  # Your condition
        score = 1.0 if passed else 0.0

        return EvalResult(
            passed=passed,
            score=score,
            reason="Reason for pass/fail",
            details={"any": "additional info"}
        )
```

Then register it in the factory function:

```python
# In testmcpy/evals/base_evaluators.py
def create_evaluator(name: str, **kwargs) -> BaseEvaluator:
    evaluators = {
        # ... existing evaluators ...
        "my_custom_evaluator": MyCustomEvaluator,
    }
    return evaluators[name](**kwargs)
```

## Evaluator Context

All evaluators receive a context dictionary with the following keys:

```python
{
    "prompt": str,                    # Original prompt sent to LLM
    "response": str,                  # LLM's final response text
    "tool_calls": List[Dict],         # List of tool calls made
    "tool_results": List[MCPToolResult],  # Results from tool executions
    "metadata": {
        "duration_seconds": float,    # Total execution time
        "model": str,                 # Model used
        "total_tokens": int,          # Total tokens used
        "cost": float                 # Cost in USD
    }
}
```

### Tool Call Structure

```python
{
    "name": str,           # Tool name
    "arguments": Dict,     # Parameters passed to tool
}
```

### Tool Result Structure

```python
MCPToolResult(
    tool_call_id: str,
    content: Any,           # Result content
    is_error: bool,         # Whether execution failed
    error_message: str      # Error message if is_error=True
)
```

## Best Practices

### 1. Combine Complementary Evaluators

```yaml
evaluators:
  # Verify tool was called
  - name: "was_mcp_tool_called"
    args:
      tool_name: "create_item"

  # Verify parameters were correct
  - name: "tool_called_with_parameters"
    args:
      tool_name: "create_item"
      parameters:
        name: "Test Item"
      partial_match: true

  # Verify execution succeeded
  - name: "execution_successful"

  # Verify response content
  - name: "final_answer_contains"
    args:
      expected_content: ["created", "successfully"]
```

### 2. Use Parameter Ranges for Fuzzy Matching

When exact values aren't critical:

```yaml
- name: "parameter_value_in_range"
  args:
    tool_name: "list_items"
    parameter_name: "limit"
    min_value: 10
    max_value: 25
```

### 3. Test Edge Cases

```yaml
tests:
  # Normal case
  - name: "test_normal_operation"
    evaluators:
      - name: "execution_successful"

  # Edge case: empty results
  - name: "test_empty_results"
    evaluators:
      - name: "final_answer_contains"
        args:
          expected_content: ["no results", "empty", "not found"]

  # Edge case: maximum limit
  - name: "test_max_limit"
    evaluators:
      - name: "parameter_value_in_range"
        args:
          parameter_name: "limit"
          max_value: 1000
```

### 4. Performance Budgets

Set realistic performance expectations:

```yaml
evaluators:
  # Fast operations
  - name: "within_time_limit"
    args:
      max_seconds: 5

  # Token budget for simple queries
  - name: "token_usage_reasonable"
    args:
      max_tokens: 1000
      max_cost: 0.02
```

## Troubleshooting

### Evaluator Not Found

```
ValueError: Unknown evaluator: my_evaluator
```

Check spelling and available evaluators:
```bash
python -c "from testmcpy.evals.base_evaluators import create_evaluator; print(create_evaluator.__doc__)"
```

### Parameter Type Mismatch

Ensure parameter values match expected types:
```yaml
# ❌ Wrong - number as string
parameter_value: "10"

# ✅ Correct - number as number
parameter_value: 10

# ✅ Correct - boolean
parameter_value: true
```

### Test Always Fails

Run with `--verbose` to see detailed output:
```bash
testmcpy run tests/my_test.yaml --verbose
```

This shows:
- What tools were called
- What parameters were passed
- Evaluator pass/fail reasons
- Response content
