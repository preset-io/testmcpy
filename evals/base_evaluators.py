"""
Base evaluation functions for MCP Testing Framework.

These evaluators can be used to validate LLM responses and tool calling behavior.
"""

import json
import re
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class EvalResult:
    """Result from an evaluation function."""
    passed: bool
    score: float  # 0.0 to 1.0
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class BaseEvaluator(ABC):
    """Base class for all evaluators."""

    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """
        Evaluate based on the provided context.

        Args:
            context: Dictionary containing:
                - prompt: The original prompt
                - response: The LLM response
                - tool_calls: List of tool calls made
                - tool_results: Results from tool executions
                - metadata: Additional metadata

        Returns:
            EvalResult with pass/fail and details
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the evaluator."""
        pass

    @property
    def description(self) -> str:
        """Description of what this evaluator checks."""
        return ""


class WasMCPToolCalled(BaseEvaluator):
    """Check if an MCP tool was called."""

    def __init__(self, tool_name: Optional[str] = None):
        self.tool_name = tool_name

    @property
    def name(self) -> str:
        if self.tool_name:
            return f"was_tool_called:{self.tool_name}"
        return "was_any_tool_called"

    @property
    def description(self) -> str:
        if self.tool_name:
            return f"Checks if the '{self.tool_name}' tool was called"
        return "Checks if any MCP tool was called"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No tool calls found in response"
            )

        if self.tool_name:
            # Check for specific tool
            for call in tool_calls:
                if call.get("name") == self.tool_name:
                    return EvalResult(
                        passed=True,
                        score=1.0,
                        reason=f"Tool '{self.tool_name}' was called",
                        details={"tool_call": call}
                    )

            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was not called",
                details={"tools_called": [c.get("name") for c in tool_calls]}
            )

        # Any tool call is acceptable
        return EvalResult(
            passed=True,
            score=1.0,
            reason=f"{len(tool_calls)} tool(s) called",
            details={"tool_calls": tool_calls}
        )


class ExecutionSuccessful(BaseEvaluator):
    """Check if tool execution was successful (no errors)."""

    @property
    def name(self) -> str:
        return "execution_successful"

    @property
    def description(self) -> str:
        return "Checks if tool execution completed without errors"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        tool_results = context.get("tool_results", [])

        if not tool_results:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No tool execution results found"
            )

        errors = []
        for result in tool_results:
            if result.is_error:
                errors.append({
                    "tool": result.tool_call_id,
                    "error": result.error_message or "Unknown error"
                })

        if errors:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"{len(errors)} tool execution error(s) occurred",
                details={"errors": errors}
            )

        return EvalResult(
            passed=True,
            score=1.0,
            reason="All tool executions completed successfully",
            details={"successful_executions": len(tool_results)}
        )


class FinalAnswerContains(BaseEvaluator):
    """Check if the final answer contains expected content."""

    def __init__(self, expected_content: Union[str, List[str]], case_sensitive: bool = False):
        self.expected_content = expected_content if isinstance(expected_content, list) else [expected_content]
        self.case_sensitive = case_sensitive

    @property
    def name(self) -> str:
        return "final_answer_contains"

    @property
    def description(self) -> str:
        return f"Checks if final answer contains: {', '.join(self.expected_content)}"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        response = context.get("response", "")

        if not self.case_sensitive:
            response = response.lower()

        found = []
        not_found = []

        for content in self.expected_content:
            check_content = content if self.case_sensitive else content.lower()
            if check_content in response:
                found.append(content)
            else:
                not_found.append(content)

        score = len(found) / len(self.expected_content) if self.expected_content else 0.0

        if score == 1.0:
            return EvalResult(
                passed=True,
                score=score,
                reason="All expected content found in response",
                details={"found": found}
            )
        elif score > 0:
            return EvalResult(
                passed=False,
                score=score,
                reason=f"Partial match: {len(found)}/{len(self.expected_content)} items found",
                details={"found": found, "not_found": not_found}
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No expected content found in response",
                details={"not_found": not_found}
            )


class AnswerContainsLink(BaseEvaluator):
    """Check if the answer contains expected links."""

    def __init__(self, expected_links: Optional[List[str]] = None):
        self.expected_links = expected_links

    @property
    def name(self) -> str:
        return "answer_contains_link"

    @property
    def description(self) -> str:
        return "Checks if answer contains expected links"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        response = context.get("response", "")

        # Extract all URLs from response
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        found_links = re.findall(url_pattern, response)

        if not self.expected_links:
            # Just check if any links exist
            if found_links:
                return EvalResult(
                    passed=True,
                    score=1.0,
                    reason=f"Found {len(found_links)} link(s) in response",
                    details={"links": found_links}
                )
            else:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason="No links found in response"
                )

        # Check for specific links
        found_expected = []
        missing = []

        for expected_link in self.expected_links:
            if any(expected_link in link for link in found_links):
                found_expected.append(expected_link)
            else:
                missing.append(expected_link)

        score = len(found_expected) / len(self.expected_links) if self.expected_links else 0.0

        if score == 1.0:
            return EvalResult(
                passed=True,
                score=score,
                reason="All expected links found",
                details={"found": found_expected}
            )
        else:
            return EvalResult(
                passed=False,
                score=score,
                reason=f"Missing {len(missing)} expected link(s)",
                details={"found": found_expected, "missing": missing, "all_links": found_links}
            )


class WithinTimeLimit(BaseEvaluator):
    """Check if execution completed within time limit."""

    def __init__(self, max_seconds: float):
        self.max_seconds = max_seconds

    @property
    def name(self) -> str:
        return f"within_time_limit:{self.max_seconds}s"

    @property
    def description(self) -> str:
        return f"Checks if execution completed within {self.max_seconds} seconds"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        duration = context.get("metadata", {}).get("duration_seconds", 0)

        if duration <= 0:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="Duration information not available"
            )

        if duration <= self.max_seconds:
            return EvalResult(
                passed=True,
                score=1.0 - (duration / self.max_seconds) * 0.5,  # Higher score for faster execution
                reason=f"Completed in {duration:.2f}s (limit: {self.max_seconds}s)",
                details={"duration": duration}
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Exceeded time limit: {duration:.2f}s > {self.max_seconds}s",
                details={"duration": duration, "limit": self.max_seconds}
            )


class TokenUsageReasonable(BaseEvaluator):
    """Check if token usage is reasonable."""

    def __init__(self, max_tokens: int = 2000, max_cost: float = 0.10):
        self.max_tokens = max_tokens
        self.max_cost = max_cost

    @property
    def name(self) -> str:
        return "token_usage_reasonable"

    @property
    def description(self) -> str:
        return f"Checks if token usage is reasonable (max: {self.max_tokens} tokens, ${self.max_cost})"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        metadata = context.get("metadata", {})
        tokens_used = metadata.get("total_tokens", 0)
        cost = metadata.get("cost", 0.0)

        if tokens_used <= 0:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="Token usage information not available"
            )

        issues = []
        if tokens_used > self.max_tokens:
            issues.append(f"Token usage ({tokens_used}) exceeds limit ({self.max_tokens})")

        if cost > self.max_cost:
            issues.append(f"Cost (${cost:.4f}) exceeds limit (${self.max_cost})")

        if issues:
            return EvalResult(
                passed=False,
                score=max(0, 1.0 - (tokens_used / self.max_tokens - 1.0)),
                reason="; ".join(issues),
                details={"tokens_used": tokens_used, "cost": cost}
            )

        return EvalResult(
            passed=True,
            score=1.0 - (tokens_used / self.max_tokens) * 0.5,  # Higher score for fewer tokens
            reason=f"Token usage reasonable: {tokens_used} tokens, ${cost:.4f}",
            details={"tokens_used": tokens_used, "cost": cost}
        )


# Superset-specific evaluators

class WasSupersetChartCreated(BaseEvaluator):
    """Check if a Superset chart was created."""

    @property
    def name(self) -> str:
        return "was_superset_chart_created"

    @property
    def description(self) -> str:
        return "Checks if a Superset chart was successfully created"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])
        tool_results = context.get("tool_results", [])

        # Look for chart creation tool calls
        chart_tools = ["create_chart", "add_chart", "new_chart"]
        chart_created = False
        chart_id = None

        for i, call in enumerate(tool_calls):
            if any(tool in call.get("name", "") for tool in chart_tools):
                if i < len(tool_results):
                    result = tool_results[i]
                    if not result.is_error:
                        chart_created = True
                        # Try to extract chart ID from result
                        content = result.content or ""
                        if isinstance(content, str):
                            # Look for chart ID pattern
                            import re
                            match = re.search(r'chart[_\s]?id[:\s]+(\d+)', content, re.IGNORECASE)
                            if match:
                                chart_id = match.group(1)

        if chart_created:
            return EvalResult(
                passed=True,
                score=1.0,
                reason="Chart was successfully created",
                details={"chart_id": chart_id} if chart_id else None
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No chart creation detected"
            )


class SQLQueryValid(BaseEvaluator):
    """Check if generated SQL query is syntactically valid."""

    @property
    def name(self) -> str:
        return "sql_query_valid"

    @property
    def description(self) -> str:
        return "Checks if generated SQL query is syntactically valid"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        response = context.get("response", "")

        # Extract SQL from response (look for code blocks or SQL patterns)
        sql_pattern = r'```sql\n(.*?)\n```|SELECT\s+.*?FROM\s+.*?(?:;|\n|$)'
        sql_matches = re.findall(sql_pattern, response, re.DOTALL | re.IGNORECASE)

        if not sql_matches:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No SQL query found in response"
            )

        # Basic SQL validation
        sql_query = sql_matches[0] if isinstance(sql_matches[0], str) else sql_matches[0][0]
        sql_query = sql_query.strip()

        # Check for basic SQL structure
        required_keywords = ["SELECT", "FROM"]
        has_required = all(
            keyword in sql_query.upper()
            for keyword in required_keywords
        )

        if has_required:
            return EvalResult(
                passed=True,
                score=1.0,
                reason="SQL query appears syntactically valid",
                details={"query": sql_query[:200]}  # First 200 chars
            )
        else:
            return EvalResult(
                passed=False,
                score=0.5,
                reason="SQL query may have syntax issues",
                details={"query": sql_query[:200]}
            )


# Composite evaluator for running multiple evaluations

class CompositeEvaluator(BaseEvaluator):
    """Run multiple evaluators and combine results."""

    def __init__(self, evaluators: List[BaseEvaluator], require_all: bool = False):
        self.evaluators = evaluators
        self.require_all = require_all

    @property
    def name(self) -> str:
        return "composite_evaluator"

    @property
    def description(self) -> str:
        mode = "all" if self.require_all else "any"
        return f"Composite evaluator requiring {mode} to pass"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        results = []
        total_score = 0.0

        for evaluator in self.evaluators:
            result = evaluator.evaluate(context)
            results.append({
                "evaluator": evaluator.name,
                "passed": result.passed,
                "score": result.score,
                "reason": result.reason
            })
            total_score += result.score

        avg_score = total_score / len(self.evaluators) if self.evaluators else 0.0
        passed_count = sum(1 for r in results if r["passed"])

        if self.require_all:
            passed = passed_count == len(self.evaluators)
            reason = f"All evaluators passed" if passed else f"{passed_count}/{len(self.evaluators)} evaluators passed"
        else:
            passed = passed_count > 0
            reason = f"{passed_count}/{len(self.evaluators)} evaluators passed"

        return EvalResult(
            passed=passed,
            score=avg_score,
            reason=reason,
            details={"results": results}
        )


# Factory function for creating evaluators

def create_evaluator(name: str, **kwargs) -> BaseEvaluator:
    """Factory function to create evaluators by name."""
    evaluators = {
        "was_mcp_tool_called": WasMCPToolCalled,
        "execution_successful": ExecutionSuccessful,
        "final_answer_contains": FinalAnswerContains,
        "answer_contains_link": AnswerContainsLink,
        "within_time_limit": WithinTimeLimit,
        "token_usage_reasonable": TokenUsageReasonable,
        "was_superset_chart_created": WasSupersetChartCreated,
        "sql_query_valid": SQLQueryValid,
    }

    if name not in evaluators:
        raise ValueError(f"Unknown evaluator: {name}")

    return evaluators[name](**kwargs)