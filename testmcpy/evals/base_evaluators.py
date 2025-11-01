"""
Base evaluation functions for testmcpy.

These evaluators can be used to validate LLM responses and tool calling behavior.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    """Result from an evaluation function."""

    passed: bool
    score: float  # 0.0 to 1.0
    reason: str | None = None
    details: dict[str, Any] | None = None


class BaseEvaluator(ABC):
    """Base class for all evaluators."""

    @abstractmethod
    def evaluate(self, context: dict[str, Any]) -> EvalResult:
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

    def __init__(self, tool_name: str | None = None):
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

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return EvalResult(passed=False, score=0.0, reason="No tool calls found in response")

        if self.tool_name:
            # Check for specific tool
            for call in tool_calls:
                if call.get("name") == self.tool_name:
                    return EvalResult(
                        passed=True,
                        score=1.0,
                        reason=f"Tool '{self.tool_name}' was called",
                        details={"tool_call": call},
                    )

            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was not called",
                details={"tools_called": [c.get("name") for c in tool_calls]},
            )

        # Any tool call is acceptable
        return EvalResult(
            passed=True,
            score=1.0,
            reason=f"{len(tool_calls)} tool(s) called",
            details={"tool_calls": tool_calls},
        )


class ExecutionSuccessful(BaseEvaluator):
    """Check if tool execution was successful (no errors)."""

    @property
    def name(self) -> str:
        return "execution_successful"

    @property
    def description(self) -> str:
        return "Checks if tool execution completed without errors"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_results = context.get("tool_results", [])

        if not tool_results:
            return EvalResult(passed=False, score=0.0, reason="No tool execution results found")

        errors = []
        for result in tool_results:
            if result.is_error:
                errors.append(
                    {"tool": result.tool_call_id, "error": result.error_message or "Unknown error"}
                )

        if errors:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"{len(errors)} tool execution error(s) occurred",
                details={"errors": errors},
            )

        return EvalResult(
            passed=True,
            score=1.0,
            reason="All tool executions completed successfully",
            details={"successful_executions": len(tool_results)},
        )


class FinalAnswerContains(BaseEvaluator):
    """Check if the final answer contains expected content."""

    def __init__(self, expected_content: str | list[str], case_sensitive: bool = False):
        self.expected_content = (
            expected_content if isinstance(expected_content, list) else [expected_content]
        )
        self.case_sensitive = case_sensitive

    @property
    def name(self) -> str:
        return "final_answer_contains"

    @property
    def description(self) -> str:
        return f"Checks if final answer contains: {', '.join(self.expected_content)}"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
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
                details={"found": found},
            )
        elif score > 0:
            return EvalResult(
                passed=False,
                score=score,
                reason=f"Partial match: {len(found)}/{len(self.expected_content)} items found",
                details={"found": found, "not_found": not_found},
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No expected content found in response",
                details={"not_found": not_found},
            )


class AnswerContainsLink(BaseEvaluator):
    """Check if the answer contains expected links."""

    def __init__(self, expected_links: list[str] | None = None):
        self.expected_links = expected_links

    @property
    def name(self) -> str:
        return "answer_contains_link"

    @property
    def description(self) -> str:
        return "Checks if answer contains expected links"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
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
                    details={"links": found_links},
                )
            else:
                return EvalResult(passed=False, score=0.0, reason="No links found in response")

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
                details={"found": found_expected},
            )
        else:
            return EvalResult(
                passed=False,
                score=score,
                reason=f"Missing {len(missing)} expected link(s)",
                details={"found": found_expected, "missing": missing, "all_links": found_links},
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

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        duration = context.get("metadata", {}).get("duration_seconds", 0)

        if duration <= 0:
            return EvalResult(passed=False, score=0.0, reason="Duration information not available")

        if duration <= self.max_seconds:
            return EvalResult(
                passed=True,
                score=1.0
                - (duration / self.max_seconds) * 0.5,  # Higher score for faster execution
                reason=f"Completed in {duration:.2f}s (limit: {self.max_seconds}s)",
                details={"duration": duration},
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Exceeded time limit: {duration:.2f}s > {self.max_seconds}s",
                details={"duration": duration, "limit": self.max_seconds},
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
        return (
            f"Checks if token usage is reasonable (max: {self.max_tokens} tokens, ${self.max_cost})"
        )

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        metadata = context.get("metadata", {})
        tokens_used = metadata.get("total_tokens", 0)
        cost = metadata.get("cost", 0.0)

        if tokens_used <= 0:
            return EvalResult(
                passed=False, score=0.0, reason="Token usage information not available"
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
                details={"tokens_used": tokens_used, "cost": cost},
            )

        return EvalResult(
            passed=True,
            score=1.0 - (tokens_used / self.max_tokens) * 0.5,  # Higher score for fewer tokens
            reason=f"Token usage reasonable: {tokens_used} tokens, ${cost:.4f}",
            details={"tokens_used": tokens_used, "cost": cost},
        )


# Parameter validation evaluators


class ToolCalledWithParameter(BaseEvaluator):
    """Check if a tool was called with a specific parameter."""

    def __init__(self, tool_name: str, parameter_name: str, parameter_value: Any | None = None):
        """
        Check if tool was called with a specific parameter.

        Args:
            tool_name: Name of the tool to check
            parameter_name: Name of the parameter to check for
            parameter_value: Optional - specific value to check for. If None, just checks parameter exists
        """
        self.tool_name = tool_name
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value

    @property
    def name(self) -> str:
        if self.parameter_value is not None:
            return f"tool_called_with_param:{self.tool_name}.{self.parameter_name}={self.parameter_value}"
        return f"tool_called_with_param:{self.tool_name}.{self.parameter_name}"

    @property
    def description(self) -> str:
        if self.parameter_value is not None:
            return f"Checks if '{self.tool_name}' was called with {self.parameter_name}={self.parameter_value}"
        return f"Checks if '{self.tool_name}' was called with parameter '{self.parameter_name}'"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return EvalResult(passed=False, score=0.0, reason="No tool calls found in response")

        # Find tool call matching the tool name
        matching_calls = [call for call in tool_calls if call.get("name") == self.tool_name]

        if not matching_calls:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was not called",
                details={"tools_called": [c.get("name") for c in tool_calls]},
            )

        # Check if parameter exists in any matching call
        for call in matching_calls:
            arguments = call.get("arguments", {})

            if self.parameter_name in arguments:
                actual_value = arguments[self.parameter_name]

                # If we're checking for a specific value
                if self.parameter_value is not None:
                    if actual_value == self.parameter_value:
                        return EvalResult(
                            passed=True,
                            score=1.0,
                            reason=f"Tool '{self.tool_name}' called with {self.parameter_name}={actual_value}",
                            details={"tool_call": call, "parameter_value": actual_value},
                        )
                else:
                    # Just checking parameter exists
                    return EvalResult(
                        passed=True,
                        score=1.0,
                        reason=f"Tool '{self.tool_name}' called with parameter '{self.parameter_name}'",
                        details={"tool_call": call, "parameter_value": actual_value},
                    )

        # Parameter not found or value didn't match
        if self.parameter_value is not None:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was called but parameter '{self.parameter_name}' was not set to '{self.parameter_value}'",
                details={"tool_calls": matching_calls},
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was called but parameter '{self.parameter_name}' was not provided",
                details={"tool_calls": matching_calls},
            )


class ToolCalledWithParameters(BaseEvaluator):
    """Check if a tool was called with multiple specific parameters."""

    def __init__(self, tool_name: str, parameters: dict[str, Any], partial_match: bool = False):
        """
        Check if tool was called with specific parameters.

        Args:
            tool_name: Name of the tool to check
            parameters: Dictionary of parameter_name -> expected_value
            partial_match: If True, additional parameters are allowed. If False, must match exactly
        """
        self.tool_name = tool_name
        self.parameters = parameters
        self.partial_match = partial_match

    @property
    def name(self) -> str:
        mode = "partial" if self.partial_match else "exact"
        return f"tool_called_with_params:{self.tool_name}:{mode}"

    @property
    def description(self) -> str:
        mode = "at least" if self.partial_match else "exactly"
        params_str = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        return f"Checks if '{self.tool_name}' was called with {mode} parameters: {params_str}"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return EvalResult(passed=False, score=0.0, reason="No tool calls found in response")

        # Find tool call matching the tool name
        matching_calls = [call for call in tool_calls if call.get("name") == self.tool_name]

        if not matching_calls:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Tool '{self.tool_name}' was not called",
                details={"tools_called": [c.get("name") for c in tool_calls]},
            )

        # Check each matching call for parameter match
        for call in matching_calls:
            arguments = call.get("arguments", {})

            # Check if all required parameters match
            matches = []
            mismatches = []

            for param_name, expected_value in self.parameters.items():
                actual_value = arguments.get(param_name)

                if actual_value == expected_value:
                    matches.append(param_name)
                else:
                    mismatches.append(
                        {
                            "parameter": param_name,
                            "expected": expected_value,
                            "actual": actual_value,
                        }
                    )

            # If all parameters match
            if len(matches) == len(self.parameters):
                # For exact match, check no extra parameters
                if not self.partial_match:
                    extra_params = set(arguments.keys()) - set(self.parameters.keys())
                    if extra_params:
                        return EvalResult(
                            passed=False,
                            score=0.8,
                            reason=f"Tool called with correct parameters but has extra parameters: {extra_params}",
                            details={"tool_call": call, "extra_parameters": list(extra_params)},
                        )

                return EvalResult(
                    passed=True,
                    score=1.0,
                    reason=f"Tool '{self.tool_name}' called with matching parameters",
                    details={"tool_call": call, "matched_parameters": matches},
                )

        # No matching call found
        score = len(matches) / len(self.parameters) if self.parameters else 0.0
        return EvalResult(
            passed=False,
            score=score,
            reason=f"Tool '{self.tool_name}' called but parameters don't match",
            details={"tool_calls": matching_calls, "matched": matches, "mismatched": mismatches},
        )


class ParameterValueInRange(BaseEvaluator):
    """Check if a parameter value is within expected range."""

    def __init__(
        self,
        tool_name: str,
        parameter_name: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ):
        """
        Check if parameter value is in range.

        Args:
            tool_name: Name of the tool
            parameter_name: Name of the parameter
            min_value: Minimum acceptable value (inclusive)
            max_value: Maximum acceptable value (inclusive)
        """
        self.tool_name = tool_name
        self.parameter_name = parameter_name
        self.min_value = min_value
        self.max_value = max_value

    @property
    def name(self) -> str:
        range_str = f"{self.min_value or '-∞'}-{self.max_value or '∞'}"
        return f"param_in_range:{self.tool_name}.{self.parameter_name}:{range_str}"

    @property
    def description(self) -> str:
        range_str = f"[{self.min_value or '-∞'}, {self.max_value or '∞'}]"
        return f"Checks if {self.tool_name}.{self.parameter_name} is in range {range_str}"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        matching_calls = [call for call in tool_calls if call.get("name") == self.tool_name]

        if not matching_calls:
            return EvalResult(
                passed=False, score=0.0, reason=f"Tool '{self.tool_name}' was not called"
            )

        for call in matching_calls:
            arguments = call.get("arguments", {})

            if self.parameter_name not in arguments:
                continue

            value = arguments[self.parameter_name]

            try:
                numeric_value = float(value)

                in_range = True
                if self.min_value is not None and numeric_value < self.min_value:
                    in_range = False
                if self.max_value is not None and numeric_value > self.max_value:
                    in_range = False

                if in_range:
                    return EvalResult(
                        passed=True,
                        score=1.0,
                        reason=f"Parameter {self.parameter_name}={numeric_value} is in valid range",
                        details={"value": numeric_value},
                    )
                else:
                    return EvalResult(
                        passed=False,
                        score=0.0,
                        reason=f"Parameter {self.parameter_name}={numeric_value} is out of range",
                        details={
                            "value": numeric_value,
                            "min": self.min_value,
                            "max": self.max_value,
                        },
                    )

            except (ValueError, TypeError):
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason=f"Parameter {self.parameter_name} value '{value}' is not numeric",
                    details={"value": value},
                )

        return EvalResult(
            passed=False,
            score=0.0,
            reason=f"Parameter '{self.parameter_name}' not found in tool calls",
            details={"tool_calls": matching_calls},
        )


class ToolCallCount(BaseEvaluator):
    """Check the number of times a tool was called."""

    def __init__(
        self,
        tool_name: str | None = None,
        expected_count: int | None = None,
        min_count: int | None = None,
        max_count: int | None = None,
    ):
        """
        Check tool call count.

        Args:
            tool_name: Specific tool to count. If None, counts all tools
            expected_count: Exact number of calls expected
            min_count: Minimum number of calls
            max_count: Maximum number of calls
        """
        self.tool_name = tool_name
        self.expected_count = expected_count
        self.min_count = min_count
        self.max_count = max_count

    @property
    def name(self) -> str:
        tool = self.tool_name or "any_tool"
        if self.expected_count is not None:
            return f"tool_call_count:{tool}=={self.expected_count}"
        return f"tool_call_count:{tool}"

    @property
    def description(self) -> str:
        tool = self.tool_name or "any tool"
        if self.expected_count is not None:
            return f"Checks if '{tool}' was called exactly {self.expected_count} time(s)"
        ranges = []
        if self.min_count is not None:
            ranges.append(f"at least {self.min_count}")
        if self.max_count is not None:
            ranges.append(f"at most {self.max_count}")
        range_str = " and ".join(ranges) if ranges else "any number of"
        return f"Checks if '{tool}' was called {range_str} times"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if self.tool_name:
            count = sum(1 for call in tool_calls if call.get("name") == self.tool_name)
            tool_desc = f"'{self.tool_name}'"
        else:
            count = len(tool_calls)
            tool_desc = "tools"

        # Check expected count
        if self.expected_count is not None:
            if count == self.expected_count:
                return EvalResult(
                    passed=True,
                    score=1.0,
                    reason=f"{tool_desc} called exactly {count} time(s) as expected",
                    details={"count": count},
                )
            else:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason=f"{tool_desc} called {count} time(s), expected {self.expected_count}",
                    details={"count": count, "expected": self.expected_count},
                )

        # Check range
        passed = True
        issues = []

        if self.min_count is not None and count < self.min_count:
            passed = False
            issues.append(f"called {count} time(s), minimum {self.min_count}")

        if self.max_count is not None and count > self.max_count:
            passed = False
            issues.append(f"called {count} time(s), maximum {self.max_count}")

        if passed:
            return EvalResult(
                passed=True,
                score=1.0,
                reason=f"{tool_desc} called {count} time(s), within expected range",
                details={"count": count},
            )
        else:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="; ".join(issues),
                details={"count": count, "min": self.min_count, "max": self.max_count},
            )


class ToolCallSequence(BaseEvaluator):
    """Check that tools were called in a specific order."""

    def __init__(
        self,
        sequence: list[str],
        strict: bool = True,
        allow_intermediate: bool = False,
    ):
        """
        Check tool call sequence.

        Args:
            sequence: List of tool names that should be called in order
            strict: If True, sequence must match exactly (no extra tools).
                   If False, only checks that sequence appears in order.
            allow_intermediate: If True, allows other tools between sequence steps.
                              Only applies when strict=False.

        Examples:
            # Strict sequence - must be exactly these tools in this order
            ToolCallSequence(["list_datasets", "generate_chart"], strict=True)

            # Loose sequence - these tools must appear in order, but other tools allowed
            ToolCallSequence(["list_datasets", "generate_chart"], strict=False, allow_intermediate=True)
        """
        self.sequence = sequence
        self.strict = strict
        self.allow_intermediate = allow_intermediate

    @property
    def name(self) -> str:
        return f"tool_call_sequence:{' -> '.join(self.sequence)}"

    @property
    def description(self) -> str:
        if self.strict:
            return f"Checks that tools are called in exact sequence: {' -> '.join(self.sequence)}"
        elif self.allow_intermediate:
            return f"Checks that tools appear in order (other tools allowed): {' -> '.join(self.sequence)}"
        else:
            return f"Checks that only these tools are called in order: {' -> '.join(self.sequence)}"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No tool calls found in response",
            )

        actual_sequence = [call.get("name") for call in tool_calls]

        if self.strict:
            # Exact match required
            if actual_sequence == self.sequence:
                return EvalResult(
                    passed=True,
                    score=1.0,
                    reason=f"Tools called in exact sequence: {' -> '.join(actual_sequence)}",
                    details={"actual_sequence": actual_sequence, "expected_sequence": self.sequence},
                )
            else:
                return EvalResult(
                    passed=False,
                    score=0.0,
                    reason=f"Sequence mismatch. Expected: {' -> '.join(self.sequence)}, Got: {' -> '.join(actual_sequence)}",
                    details={"actual_sequence": actual_sequence, "expected_sequence": self.sequence},
                )

        # Non-strict mode: check if sequence appears in order
        sequence_idx = 0
        found_positions = []

        for i, tool_name in enumerate(actual_sequence):
            if sequence_idx < len(self.sequence) and tool_name == self.sequence[sequence_idx]:
                found_positions.append(i)
                sequence_idx += 1
            elif not self.allow_intermediate and tool_name not in self.sequence:
                # Found a tool not in our sequence and intermediates not allowed
                return EvalResult(
                    passed=False,
                    score=sequence_idx / len(self.sequence),
                    reason=f"Unexpected tool '{tool_name}' at position {i}. Only {self.sequence} allowed.",
                    details={
                        "actual_sequence": actual_sequence,
                        "expected_sequence": self.sequence,
                        "found_up_to_index": sequence_idx,
                        "unexpected_tool": tool_name,
                    },
                )

        # Check if we found all tools in the sequence
        if sequence_idx == len(self.sequence):
            return EvalResult(
                passed=True,
                score=1.0,
                reason=f"Required tools called in correct order: {' -> '.join([actual_sequence[i] for i in found_positions])}",
                details={
                    "actual_sequence": actual_sequence,
                    "expected_sequence": self.sequence,
                    "found_positions": found_positions,
                },
            )
        else:
            missing_tools = self.sequence[sequence_idx:]
            return EvalResult(
                passed=False,
                score=sequence_idx / len(self.sequence),
                reason=f"Incomplete sequence. Found {sequence_idx}/{len(self.sequence)} tools. Missing: {' -> '.join(missing_tools)}",
                details={
                    "actual_sequence": actual_sequence,
                    "expected_sequence": self.sequence,
                    "found_up_to_index": sequence_idx,
                    "missing_tools": missing_tools,
                },
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

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
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

                            match = re.search(r"chart[_\s]?id[:\s]+(\d+)", content, re.IGNORECASE)
                            if match:
                                chart_id = match.group(1)

        if chart_created:
            return EvalResult(
                passed=True,
                score=1.0,
                reason="Chart was successfully created",
                details={"chart_id": chart_id} if chart_id else None,
            )
        else:
            return EvalResult(passed=False, score=0.0, reason="No chart creation detected")


class SQLQueryValid(BaseEvaluator):
    """Check if generated SQL query is syntactically valid."""

    @property
    def name(self) -> str:
        return "sql_query_valid"

    @property
    def description(self) -> str:
        return "Checks if generated SQL query is syntactically valid"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        response = context.get("response", "")

        # Extract SQL from response (look for code blocks or SQL patterns)
        sql_pattern = r"```sql\n(.*?)\n```|SELECT\s+.*?FROM\s+.*?(?:;|\n|$)"
        sql_matches = re.findall(sql_pattern, response, re.DOTALL | re.IGNORECASE)

        if not sql_matches:
            return EvalResult(passed=False, score=0.0, reason="No SQL query found in response")

        # Basic SQL validation
        sql_query = sql_matches[0] if isinstance(sql_matches[0], str) else sql_matches[0][0]
        sql_query = sql_query.strip()

        # Check for basic SQL structure
        required_keywords = ["SELECT", "FROM"]
        has_required = all(keyword in sql_query.upper() for keyword in required_keywords)

        if has_required:
            return EvalResult(
                passed=True,
                score=1.0,
                reason="SQL query appears syntactically valid",
                details={"query": sql_query[:200]},  # First 200 chars
            )
        else:
            return EvalResult(
                passed=False,
                score=0.5,
                reason="SQL query may have syntax issues",
                details={"query": sql_query[:200]},
            )


# Composite evaluator for running multiple evaluations


class CompositeEvaluator(BaseEvaluator):
    """Run multiple evaluators and combine results."""

    def __init__(self, evaluators: list[BaseEvaluator], require_all: bool = False):
        self.evaluators = evaluators
        self.require_all = require_all

    @property
    def name(self) -> str:
        return "composite_evaluator"

    @property
    def description(self) -> str:
        mode = "all" if self.require_all else "any"
        return f"Composite evaluator requiring {mode} to pass"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        results = []
        total_score = 0.0

        for evaluator in self.evaluators:
            result = evaluator.evaluate(context)
            results.append(
                {
                    "evaluator": evaluator.name,
                    "passed": result.passed,
                    "score": result.score,
                    "reason": result.reason,
                }
            )
            total_score += result.score

        avg_score = total_score / len(self.evaluators) if self.evaluators else 0.0
        passed_count = sum(1 for r in results if r["passed"])

        if self.require_all:
            passed = passed_count == len(self.evaluators)
            reason = (
                "All evaluators passed"
                if passed
                else f"{passed_count}/{len(self.evaluators)} evaluators passed"
            )
        else:
            passed = passed_count > 0
            reason = f"{passed_count}/{len(self.evaluators)} evaluators passed"

        return EvalResult(
            passed=passed, score=avg_score, reason=reason, details={"results": results}
        )


# Factory function for creating evaluators


def create_evaluator(name: str, **kwargs) -> BaseEvaluator:
    """Factory function to create evaluators by name."""
    evaluators = {
        # Basic evaluators
        "was_mcp_tool_called": WasMCPToolCalled,
        "execution_successful": ExecutionSuccessful,
        "final_answer_contains": FinalAnswerContains,
        "answer_contains_link": AnswerContainsLink,
        "within_time_limit": WithinTimeLimit,
        "token_usage_reasonable": TokenUsageReasonable,
        # Parameter validation evaluators
        "tool_called_with_parameter": ToolCalledWithParameter,
        "tool_called_with_parameters": ToolCalledWithParameters,
        "parameter_value_in_range": ParameterValueInRange,
        "tool_call_count": ToolCallCount,
        "tool_call_sequence": ToolCallSequence,
        # Superset-specific evaluators
        "was_superset_chart_created": WasSupersetChartCreated,
        "sql_query_valid": SQLQueryValid,
    }

    if name not in evaluators:
        raise ValueError(f"Unknown evaluator: {name}")

    return evaluators[name](**kwargs)
