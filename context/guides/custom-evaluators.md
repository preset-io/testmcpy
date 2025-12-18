# Custom Evaluators Guide

Learn how to create custom evaluators for domain-specific testing needs.

## Overview

While testmcpy includes many built-in evaluators, you may need custom logic for:
- Domain-specific validation (e.g., SQL syntax, data format)
- Business rule checking
- Complex multi-step verification
- Integration with external systems
- Custom metrics and scoring

## Basic Evaluator Structure

All evaluators extend the `BaseEvaluator` class:

```python
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any

class MyCustomEvaluator(BaseEvaluator):
    """One-line description of what this evaluator checks."""

    def __init__(self, param1: str, param2: int = 10):
        """Initialize with parameters from test YAML."""
        self.param1 = param1
        self.param2 = param2

    @property
    def name(self) -> str:
        """Unique identifier for this evaluator."""
        return "my_custom_evaluator"

    @property
    def description(self) -> str:
        """Human-readable description."""
        return f"Checks {self.param1} against threshold {self.param2}"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """
        Evaluate the test context.

        Args:
            context: Dictionary containing test execution data

        Returns:
            EvalResult with pass/fail status, score, and details
        """
        # Your evaluation logic here
        passed = True  # Your condition
        score = 1.0 if passed else 0.0

        return EvalResult(
            passed=passed,
            score=score,
            reason="Human-readable explanation",
            details={"additional": "metadata"}
        )
```

## Context Structure

The `context` dictionary contains all test execution data:

```python
context = {
    # Original test prompt
    "prompt": "Create a bar chart showing sales by region",

    # LLM's final response text
    "response": "I've created a bar chart for you...",

    # List of tool calls made
    "tool_calls": [
        {
            "name": "create_chart",
            "arguments": {
                "chart_type": "bar",
                "dataset_id": 123
            }
        }
    ],

    # Tool execution results
    "tool_results": [
        MCPToolResult(
            tool_call_id="call_123",
            content={"chart_id": 456, "url": "..."},
            is_error=False,
            error_message=None
        )
    ],

    # Metadata about execution
    "metadata": {
        "duration_seconds": 3.14,
        "model": "claude-haiku-4-5",
        "total_tokens": 1234,
        "cost": 0.005
    }
}
```

## Example 1: Simple Validation

Check if response contains valid email addresses:

```python
import re
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any

class ContainsValidEmail(BaseEvaluator):
    """Checks if response contains at least one valid email address."""

    def __init__(self, required: bool = True):
        self.required = required

    @property
    def name(self) -> str:
        return "contains_valid_email"

    @property
    def description(self) -> str:
        return "Validates that response contains valid email address(es)"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        response = context.get("response", "")

        # Email regex pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, response)

        if self.required:
            passed = len(emails) > 0
            reason = f"Found {len(emails)} email(s)" if passed else "No valid emails found"
        else:
            passed = True
            reason = f"Found {len(emails)} email(s) (optional check)"

        return EvalResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=reason,
            details={"emails_found": emails}
        )
```

**Usage in test:**

```yaml
tests:
  - name: "test_user_info"
    prompt: "Get contact information for user John Doe"
    evaluators:
      - name: "contains_valid_email"
        args:
          required: true
```

## Example 2: Domain-Specific Validation

Validate SQL query syntax:

```python
import sqlparse
from sqlparse.sql import Statement
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any

class SQLQueryValid(BaseEvaluator):
    """Validates SQL query syntax in tool calls or response."""

    def __init__(self, check_type: str = "SELECT"):
        """
        Args:
            check_type: Expected SQL statement type (SELECT, INSERT, UPDATE, etc.)
        """
        self.check_type = check_type.upper()

    @property
    def name(self) -> str:
        return "sql_query_valid"

    @property
    def description(self) -> str:
        return f"Validates SQL query syntax (expects {self.check_type})"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # Extract SQL from tool calls
        sql_query = None
        for tool_call in context.get("tool_calls", []):
            args = tool_call.get("arguments", {})
            if "sql" in args:
                sql_query = args["sql"]
                break
            elif "query" in args:
                sql_query = args["query"]
                break

        if not sql_query:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No SQL query found in tool calls",
                details={}
            )

        # Parse SQL
        try:
            parsed = sqlparse.parse(sql_query)
            if not parsed:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason="Could not parse SQL query",
                    details={"sql": sql_query}
                )

            statement = parsed[0]

            # Check statement type
            stmt_type = statement.get_type()
            if stmt_type != self.check_type:
                return EvalResult(
                    passed=False,
                    score=0.5,
                    reason=f"Expected {self.check_type}, got {stmt_type}",
                    details={"sql": sql_query, "type": stmt_type}
                )

            # Format query for readability
            formatted = sqlparse.format(
                sql_query,
                reindent=True,
                keyword_case='upper'
            )

            return EvalResult(
                passed=True,
                score=1.0,
                reason=f"Valid {stmt_type} query",
                details={
                    "sql": sql_query,
                    "formatted": formatted,
                    "type": stmt_type
                }
            )

        except Exception as e:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"SQL parsing error: {str(e)}",
                details={"sql": sql_query, "error": str(e)}
            )
```

**Usage:**

```yaml
tests:
  - name: "test_generate_sql"
    prompt: "Generate a SQL query to get all users created this month"
    evaluators:
      - name: "sql_query_valid"
        args:
          check_type: "SELECT"
```

## Example 3: Multi-Condition Evaluator

Check multiple related conditions:

```python
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any, List

class ChartCreationComplete(BaseEvaluator):
    """
    Validates that chart creation is complete:
    - Chart tool was called
    - Chart has valid ID
    - Response contains chart link
    - Response confirms success
    """

    @property
    def name(self) -> str:
        return "chart_creation_complete"

    @property
    def description(self) -> str:
        return "Validates complete chart creation workflow"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        checks = []
        score = 0.0
        details = {}

        # Check 1: Chart tool called
        tool_calls = context.get("tool_calls", [])
        chart_tool_called = any(
            tc.get("name") == "create_chart"
            for tc in tool_calls
        )
        checks.append(("chart_tool_called", chart_tool_called))
        if chart_tool_called:
            score += 0.25

        # Check 2: Valid chart ID in result
        chart_id = None
        for result in context.get("tool_results", []):
            if not result.is_error and isinstance(result.content, dict):
                chart_id = result.content.get("chart_id") or result.content.get("id")
                if chart_id:
                    break

        has_chart_id = chart_id is not None
        checks.append(("has_chart_id", has_chart_id))
        details["chart_id"] = chart_id
        if has_chart_id:
            score += 0.25

        # Check 3: Response contains link
        response = context.get("response", "")
        has_link = any(
            protocol in response.lower()
            for protocol in ["http://", "https://"]
        )
        checks.append(("has_link", has_link))
        if has_link:
            score += 0.25

        # Check 4: Success confirmation
        success_words = ["created", "successfully", "complete", "done"]
        has_confirmation = any(
            word in response.lower()
            for word in success_words
        )
        checks.append(("has_confirmation", has_confirmation))
        if has_confirmation:
            score += 0.25

        # Determine pass/fail
        passed = all(result for _, result in checks)

        # Build reason
        failed_checks = [name for name, result in checks if not result]
        if passed:
            reason = "Chart creation fully validated"
        else:
            reason = f"Failed checks: {', '.join(failed_checks)}"

        details["checks"] = dict(checks)

        return EvalResult(
            passed=passed,
            score=score,
            reason=reason,
            details=details
        )
```

**Usage:**

```yaml
tests:
  - name: "test_chart_creation"
    prompt: "Create a pie chart showing product categories"
    evaluators:
      - name: "chart_creation_complete"
```

## Example 4: Statistical Evaluator

Check numeric properties of results:

```python
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any, List
import statistics

class DatasetSizeReasonable(BaseEvaluator):
    """
    Checks that dataset queries return reasonable number of rows.
    Useful for catching queries that might return too much data.
    """

    def __init__(self, min_rows: int = 1, max_rows: int = 10000):
        self.min_rows = min_rows
        self.max_rows = max_rows

    @property
    def name(self) -> str:
        return "dataset_size_reasonable"

    @property
    def description(self) -> str:
        return f"Checks dataset has {self.min_rows}-{self.max_rows} rows"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # Extract row count from tool results
        row_count = None

        for result in context.get("tool_results", []):
            if result.is_error:
                continue

            content = result.content
            if isinstance(content, dict):
                # Try common field names
                row_count = (
                    content.get("row_count") or
                    content.get("count") or
                    content.get("total_rows") or
                    content.get("size")
                )

                # Or count list items
                if row_count is None and "data" in content:
                    if isinstance(content["data"], list):
                        row_count = len(content["data"])

            elif isinstance(content, list):
                row_count = len(content)

            if row_count is not None:
                break

        if row_count is None:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="Could not determine dataset size",
                details={}
            )

        # Check range
        in_range = self.min_rows <= row_count <= self.max_rows

        if in_range:
            reason = f"Dataset size {row_count} is within range"
            score = 1.0
        else:
            reason = f"Dataset size {row_count} outside range [{self.min_rows}, {self.max_rows}]"
            # Partial credit if close
            if row_count < self.min_rows:
                score = max(0.0, row_count / self.min_rows)
            else:
                score = max(0.0, 1.0 - ((row_count - self.max_rows) / self.max_rows))

        return EvalResult(
            passed=in_range,
            score=score,
            reason=reason,
            details={
                "row_count": row_count,
                "min_rows": self.min_rows,
                "max_rows": self.max_rows
            }
        )
```

**Usage:**

```yaml
tests:
  - name: "test_dataset_query"
    prompt: "Query the sales dataset for last month"
    evaluators:
      - name: "dataset_size_reasonable"
        args:
          min_rows: 10
          max_rows: 1000
```

## Example 5: Integration Evaluator

Validate against external system:

```python
import requests
from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult
from typing import Dict, Any

class ResourceExistsInAPI(BaseEvaluator):
    """
    Validates that resource created by tool actually exists in API.
    Makes HTTP request to verify.
    """

    def __init__(self, api_url: str, resource_type: str):
        """
        Args:
            api_url: Base API URL
            resource_type: Type of resource (chart, dashboard, etc.)
        """
        self.api_url = api_url.rstrip('/')
        self.resource_type = resource_type

    @property
    def name(self) -> str:
        return "resource_exists_in_api"

    @property
    def description(self) -> str:
        return f"Validates {self.resource_type} exists in API"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # Extract resource ID from tool results
        resource_id = None

        for result in context.get("tool_results", []):
            if result.is_error:
                continue

            if isinstance(result.content, dict):
                resource_id = (
                    result.content.get("id") or
                    result.content.get(f"{self.resource_type}_id")
                )
                if resource_id:
                    break

        if not resource_id:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No resource ID found in tool results",
                details={}
            )

        # Check if resource exists in API
        url = f"{self.api_url}/{self.resource_type}s/{resource_id}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                return EvalResult(
                    passed=True,
                    score=1.0,
                    reason=f"{self.resource_type} {resource_id} exists in API",
                    details={
                        "resource_id": resource_id,
                        "api_url": url,
                        "status_code": 200
                    }
                )
            elif response.status_code == 404:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason=f"{self.resource_type} {resource_id} not found in API",
                    details={
                        "resource_id": resource_id,
                        "api_url": url,
                        "status_code": 404
                    }
                )
            else:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason=f"API returned status {response.status_code}",
                    details={
                        "resource_id": resource_id,
                        "api_url": url,
                        "status_code": response.status_code
                    }
                )

        except requests.RequestException as e:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"API request failed: {str(e)}",
                details={
                    "resource_id": resource_id,
                    "api_url": url,
                    "error": str(e)
                }
            )
```

**Usage:**

```yaml
tests:
  - name: "test_chart_persisted"
    prompt: "Create a chart and save it"
    evaluators:
      - name: "resource_exists_in_api"
        args:
          api_url: "https://api.example.com/v1"
          resource_type: "chart"
```

## Registering Custom Evaluators

### Option 1: Modify Factory Function

Edit `testmcpy/evals/base_evaluators.py`:

```python
def create_evaluator(name: str, **kwargs) -> BaseEvaluator:
    """Factory function to create evaluators."""
    evaluators = {
        # Built-in evaluators
        "was_mcp_tool_called": WasMCPToolCalled,
        "execution_successful": ExecutionSuccessful,
        # ... other built-ins ...

        # Your custom evaluators
        "contains_valid_email": ContainsValidEmail,
        "sql_query_valid": SQLQueryValid,
        "chart_creation_complete": ChartCreationComplete,
        "dataset_size_reasonable": DatasetSizeReasonable,
        "resource_exists_in_api": ResourceExistsInAPI,
    }

    if name not in evaluators:
        raise ValueError(f"Unknown evaluator: {name}")

    return evaluators[name](**kwargs)
```

### Option 2: Plugin System (Future)

Future versions will support dynamic loading:

```python
# my_evaluators.py
from testmcpy.evals import register_evaluator

@register_evaluator
class MyCustomEvaluator(BaseEvaluator):
    # ...
```

## Testing Custom Evaluators

Write unit tests for your evaluators:

```python
# tests/test_my_evaluators.py
import pytest
from my_evaluators import ContainsValidEmail

def test_contains_valid_email_pass():
    """Test evaluator with valid email in response."""
    evaluator = ContainsValidEmail(required=True)

    context = {
        "prompt": "Get user email",
        "response": "The user's email is john@example.com",
        "tool_calls": [],
        "tool_results": [],
        "metadata": {}
    }

    result = evaluator.evaluate(context)

    assert result.passed
    assert result.score == 1.0
    assert "john@example.com" in result.details["emails_found"]

def test_contains_valid_email_fail():
    """Test evaluator with no email in response."""
    evaluator = ContainsValidEmail(required=True)

    context = {
        "response": "No email found",
        "tool_calls": [],
        "tool_results": [],
        "metadata": {}
    }

    result = evaluator.evaluate(context)

    assert not result.passed
    assert result.score == 0.0
    assert len(result.details["emails_found"]) == 0
```

Run tests:

```bash
pytest tests/test_my_evaluators.py
```

## Best Practices

### 1. Single Responsibility

Each evaluator should check one thing:

```python
# ✅ Good - Single responsibility
class HasChartID(BaseEvaluator):
    """Checks if result contains chart ID."""
    pass

class ChartLinkValid(BaseEvaluator):
    """Validates chart link format."""
    pass

# ❌ Bad - Too many responsibilities
class ChartEverything(BaseEvaluator):
    """Checks ID, link, title, type, and data."""
    pass
```

### 2. Clear Error Messages

Provide helpful feedback:

```python
# ✅ Good
reason = f"Expected parameter 'limit' to be between {min_val} and {max_val}, got {actual_val}"

# ❌ Bad
reason = "Invalid parameter"
```

### 3. Detailed Results

Include useful debugging information:

```python
return EvalResult(
    passed=False,
    score=0.5,
    reason="Partial match found",
    details={
        "expected": expected_values,
        "actual": actual_values,
        "matched": matched_values,
        "missing": missing_values
    }
)
```

### 4. Handle Missing Data

Gracefully handle incomplete context:

```python
tool_calls = context.get("tool_calls", [])  # Default to empty list
if not tool_calls:
    return EvalResult(
        passed=False,
        score=0.0,
        reason="No tool calls found",
        details={}
    )
```

### 5. Type Hints

Use type hints for clarity:

```python
from typing import Dict, Any, List, Optional

def evaluate(self, context: Dict[str, Any]) -> EvalResult:
    response: str = context.get("response", "")
    tool_calls: List[Dict] = context.get("tool_calls", [])
    # ...
```

## Next Steps

- [Evaluator Reference](../api/evaluators.md) - See all built-in evaluators
- [Test Format](../api/test-format.md) - Learn test YAML format
- [Basic Examples](basic-test.md) - Simple test examples
- [Development Guide](../guide/development.md) - Contributing guidelines
