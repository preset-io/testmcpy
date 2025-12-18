# Basic Test Examples

Simple, practical examples to get started with testmcpy testing.

## Example 1: Simple Tool Selection Test

The most basic test - verify the LLM selects the correct tool.

```yaml
version: "1.0"
name: "Basic Tool Selection"
description: "Test that LLM chooses the right tool"

tests:
  - name: "test_list_datasets"
    prompt: "Show me all available datasets"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"
      - name: "execution_successful"
```

**What this tests:**
- LLM understands the prompt
- LLM selects the correct tool
- Tool executes without errors

## Example 2: Parameter Validation

Test that the LLM passes correct parameters.

```yaml
version: "1.0"
name: "Parameter Validation Tests"

tests:
  - name: "test_list_with_limit"
    prompt: "Show me 10 datasets"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"

      - name: "tool_called_with_parameter"
        args:
          tool_name: "list_datasets"
          parameter_name: "limit"
          parameter_value: 10

      - name: "execution_successful"

  - name: "test_search_with_filter"
    prompt: "Find datasets with 'sales' in the name"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"

      - name: "tool_called_with_parameter"
        args:
          tool_name: "list_datasets"
          parameter_name: "filter"
          parameter_value: "sales"

      - name: "execution_successful"
```

**What this tests:**
- LLM extracts parameters from natural language
- Parameters have correct values
- Tool executes with those parameters

## Example 3: Response Content Validation

Verify the LLM's response contains expected information.

```yaml
version: "1.0"
name: "Response Content Tests"

tests:
  - name: "test_create_chart_response"
    prompt: "Create a bar chart showing sales by region"
    timeout: 30
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"

      - name: "execution_successful"

      - name: "final_answer_contains"
        args:
          expected_content:
            - "chart"
            - "created"
          case_sensitive: false

      - name: "answer_contains_link"
```

**What this tests:**
- Tool is called correctly
- Response includes confirmation message
- Response contains chart link

## Example 4: Multi-Step Workflow

Test the LLM's ability to chain multiple tool calls.

```yaml
version: "1.0"
name: "Multi-Step Workflow Tests"

tests:
  - name: "test_search_and_get_details"
    prompt: |
      First, search for datasets containing 'customer',
      then get the full details of the first result.
    timeout: 45
    evaluators:
      # Verify two tool calls were made
      - name: "tool_call_count"
        args:
          min_count: 2
          max_count: 2

      # Verify search was called
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"

      # Verify get_details was called
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_dataset_details"

      - name: "execution_successful"

      - name: "final_answer_contains"
        args:
          expected_content: ["dataset", "details"]
```

**What this tests:**
- LLM understands multi-step instructions
- LLM chains tools in correct order
- LLM uses output from first tool in second call

## Example 5: Error Handling

Test graceful handling of errors.

```yaml
version: "1.0"
name: "Error Handling Tests"

tests:
  - name: "test_invalid_dataset_id"
    prompt: "Get details for dataset with ID 999999"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_dataset_details"

      # Note: We don't check execution_successful
      # because we expect an error

      - name: "final_answer_contains"
        args:
          expected_content:
            - "not found"
            - "does not exist"
            - "invalid"

  - name: "test_missing_required_parameter"
    prompt: "Create a chart"  # Intentionally vague
    timeout: 15
    evaluators:
      # LLM should either:
      # 1. Ask for clarification, or
      # 2. Call tool with reasonable defaults

      - name: "final_answer_contains"
        args:
          expected_content:
            - "dataset"
            - "chart type"
            - "which"
            - "specify"
```

**What this tests:**
- LLM handles tool errors gracefully
- LLM provides helpful error messages
- LLM asks for clarification when needed

## Example 6: Performance and Cost Testing

Ensure tests complete within time and budget constraints.

```yaml
version: "1.0"
name: "Performance Tests"

config:
  timeout: 30

tests:
  - name: "test_fast_operation"
    prompt: "List all datasets"
    timeout: 10
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"

      - name: "within_time_limit"
        args:
          max_seconds: 5

      - name: "token_usage_reasonable"
        args:
          max_tokens: 1000
          max_cost: 0.01

      - name: "execution_successful"

  - name: "test_complex_operation"
    prompt: |
      Create a dashboard with three charts:
      1. Bar chart of sales by region
      2. Line chart of revenue over time
      3. Pie chart of product categories
    timeout: 60
    evaluators:
      - name: "tool_call_count"
        args:
          min_count: 3
          max_count: 4

      - name: "within_time_limit"
        args:
          max_seconds: 45

      - name: "token_usage_reasonable"
        args:
          max_tokens: 5000
          max_cost: 0.10

      - name: "execution_successful"
```

**What this tests:**
- Operations complete in reasonable time
- Token usage stays within budget
- Cost per test is acceptable

## Example 7: Complete Test Suite

A comprehensive test suite combining all techniques.

```yaml
version: "1.0"
name: "Library Service - Complete Test Suite"
description: |
  Complete test coverage for a library management MCP service.
  Includes basic operations, workflows, error handling, and performance tests.

config:
  timeout: 30
  model: "claude-haiku-4-5"
  provider: "anthropic"

tests:
  # --- Basic Operations ---

  - name: "test_list_books"
    prompt: "Show me all books in the library"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_books"
      - name: "execution_successful"
      - name: "within_time_limit"
        args:
          max_seconds: 10

  - name: "test_search_books"
    prompt: "Find books by author 'John Smith'"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "tool_called_with_parameter"
        args:
          tool_name: "search_books"
          parameter_name: "author"
          parameter_value: "John Smith"
      - name: "execution_successful"

  - name: "test_get_book_details"
    prompt: "Get details for book ID 12345"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_book_details"
      - name: "tool_called_with_parameter"
        args:
          tool_name: "get_book_details"
          parameter_name: "book_id"
          parameter_value: 12345
      - name: "execution_successful"

  # --- Parameter Validation ---

  - name: "test_search_multiple_criteria"
    prompt: "Find books by author 'Jane Doe' published after 2020, limit to 20 results"
    timeout: 20
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "tool_called_with_parameters"
        args:
          tool_name: "search_books"
          parameters:
            author: "Jane Doe"
            year_from: 2020
            limit: 20
          partial_match: true
      - name: "execution_successful"

  - name: "test_limit_in_range"
    prompt: "Show me 50 books"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_books"
      - name: "parameter_value_in_range"
        args:
          tool_name: "list_books"
          parameter_name: "limit"
          min_value: 1
          max_value: 100
      - name: "execution_successful"

  # --- Multi-Step Workflows ---

  - name: "test_checkout_workflow"
    prompt: |
      Find the book 'The Great Gatsby', then check it out
      for user ID 123 with a 14-day loan period.
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
          parameter_value: 123
      - name: "execution_successful"
      - name: "final_answer_contains"
        args:
          expected_content: ["checked out", "due date"]

  - name: "test_search_and_compare"
    prompt: |
      Search for all books by 'George Orwell',
      then get detailed information about each book found.
    timeout: 60
    evaluators:
      - name: "tool_call_count"
        args:
          min_count: 2
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_book_details"
      - name: "execution_successful"

  # --- Error Handling ---

  - name: "test_invalid_book_id"
    prompt: "Get details for book ID 999999999"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "get_book_details"
      - name: "final_answer_contains"
        args:
          expected_content:
            - "not found"
            - "does not exist"

  - name: "test_checkout_unavailable_book"
    prompt: "Check out book ID 12345 which is already checked out"
    timeout: 15
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "checkout_book"
      - name: "final_answer_contains"
        args:
          expected_content:
            - "unavailable"
            - "already checked out"
            - "not available"

  # --- Performance Tests ---

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
      - name: "token_usage_reasonable"
        args:
          max_tokens: 1000
          max_cost: 0.02
      - name: "execution_successful"

  # --- Response Quality ---

  - name: "test_helpful_response"
    prompt: "What books are available in the science fiction category?"
    timeout: 20
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "search_books"
      - name: "execution_successful"
      - name: "final_answer_contains"
        args:
          expected_content:
            - "science fiction"
            - "available"
```

## Running These Examples

### Run Single Example

```bash
# Save example to file
cat > test_basic.yaml << 'EOF'
version: "1.0"
name: "Basic Test"
tests:
  - name: "test_list_datasets"
    prompt: "Show me all datasets"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"
      - name: "execution_successful"
EOF

# Run the test
testmcpy run test_basic.yaml
```

### Run with Different Models

```bash
# Test with fast model
testmcpy run test_basic.yaml --model claude-haiku-4-5

# Test with more capable model
testmcpy run test_basic.yaml --model claude-sonnet-4-5

# Test with local model (free)
testmcpy run test_basic.yaml --model llama3.1:8b --provider ollama
```

### Run with Verbose Output

```bash
testmcpy run test_basic.yaml --verbose
```

## Tips for Writing Good Tests

### 1. Start Simple

Begin with basic tool selection tests:

```yaml
- name: "test_simple"
  prompt: "List all items"
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_items"
    - name: "execution_successful"
```

### 2. Add Parameter Validation

Then verify parameters:

```yaml
- name: "test_with_params"
  prompt: "List 10 items"
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_items"
    - name: "tool_called_with_parameter"
      args:
        tool_name: "list_items"
        parameter_name: "limit"
        parameter_value: 10
    - name: "execution_successful"
```

### 3. Test Edge Cases

Don't forget error scenarios:

```yaml
- name: "test_edge_case"
  prompt: "Get item with invalid ID"
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "get_item"
    - name: "final_answer_contains"
      args:
        expected_content: ["not found", "invalid"]
```

### 4. Use Descriptive Names

```yaml
# ✅ Good
- name: "test_list_items_with_pagination"

# ❌ Bad
- name: "test1"
```

### 5. Be Specific in Prompts

```yaml
# ✅ Good - Clear and specific
prompt: "Get details for user ID 123"

# ❌ Bad - Too vague
prompt: "Get user"
```

## Next Steps

- [Evaluator Reference](../api/evaluators.md) - Learn about all evaluators
- [Test Format](../api/test-format.md) - Complete YAML format reference
- [Custom Evaluators](custom-evaluators.md) - Write your own evaluators
- [CI/CD Integration](ci-cd-integration.md) - Run tests in CI/CD
