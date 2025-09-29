"""
Test runner for executing MCP test cases with LLMs.
"""

import asyncio
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
import json
import re
from datetime import datetime, timedelta

from src.mcp_client import MCPClient, MCPToolCall, MCPToolResult
from src.llm_integration import LLMProvider, create_llm_provider
from evals.base_evaluators import BaseEvaluator, EvalResult, create_evaluator


class RateLimitTracker:
    """Track token usage and manage rate limiting."""

    def __init__(self, tokens_per_minute_limit: int = 50000):
        self.tokens_per_minute_limit = tokens_per_minute_limit
        self.token_usage_history = []  # List of (timestamp, tokens) tuples

    def add_usage(self, tokens: int):
        """Record token usage with timestamp."""
        self.token_usage_history.append((datetime.now(), tokens))
        # Clean up old entries (older than 1 minute)
        cutoff = datetime.now() - timedelta(minutes=1)
        self.token_usage_history = [(ts, tokens) for ts, tokens in self.token_usage_history if ts > cutoff]

    def get_current_usage(self) -> int:
        """Get token usage in the last minute."""
        cutoff = datetime.now() - timedelta(minutes=1)
        return sum(tokens for ts, tokens in self.token_usage_history if ts > cutoff)

    def calculate_wait_time(self, next_request_tokens: int) -> float:
        """Calculate how long to wait before next request."""
        current_usage = self.get_current_usage()
        projected_usage = current_usage + next_request_tokens

        if projected_usage <= self.tokens_per_minute_limit:
            return 0  # No wait needed

        # Find oldest token usage in the last minute
        cutoff = datetime.now() - timedelta(minutes=1)
        recent_entries = [(ts, tokens) for ts, tokens in self.token_usage_history if ts > cutoff]

        if not recent_entries:
            return 0

        # Wait until oldest entry is > 1 minute old, plus a small buffer
        oldest_timestamp = min(ts for ts, _ in recent_entries)
        wait_until = oldest_timestamp + timedelta(minutes=1, seconds=5)  # 5 second buffer
        wait_time = (wait_until - datetime.now()).total_seconds()

        return max(0, wait_time)

    def is_rate_limit_error(self, error_message: str) -> bool:
        """Check if error is a rate limiting error."""
        return "rate_limit_error" in error_message or "429" in error_message


@dataclass
class TestCase:
    """Represents a single test case."""
    name: str
    prompt: str
    evaluators: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    expected_tools: Optional[List[str]] = None
    timeout: float = 30.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        """Create TestCase from dictionary."""
        return cls(
            name=data["name"],
            prompt=data["prompt"],
            evaluators=data.get("evaluators", []),
            metadata=data.get("metadata", {}),
            expected_tools=data.get("expected_tools"),
            timeout=data.get("timeout", 30.0)
        )


@dataclass
class TestResult:
    """Result from running a test case."""
    test_name: str
    passed: bool
    score: float
    duration: float
    reason: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    response: Optional[str] = None
    evaluations: List[Dict[str, Any]] = field(default_factory=list)
    cost: float = 0.0
    token_usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class TestRunner:
    """Runs test cases against MCP service with LLM."""

    def __init__(
        self,
        model: str,
        provider: str = "ollama",
        mcp_url: str = "http://localhost:5008/mcp/",
        verbose: bool = False
    ):
        self.model = model
        self.provider = provider
        self.mcp_url = mcp_url
        self.verbose = verbose
        self.llm_provider: Optional[LLMProvider] = None
        self.rate_limiter = RateLimitTracker()
        self.mcp_client: Optional[MCPClient] = None

    async def initialize(self):
        """Initialize LLM provider and MCP client."""
        if not self.llm_provider:
            self.llm_provider = create_llm_provider(
                provider=self.provider,
                model=self.model
            )
            await self.llm_provider.initialize()

        if not self.mcp_client:
            self.mcp_client = MCPClient(self.mcp_url)
            await self.mcp_client.initialize()

    async def _call_llm_with_rate_limiting(self, prompt: str, tools: List[Dict], timeout: float, max_retries: int = 3):
        """Call LLM with intelligent rate limiting and retry logic."""
        # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = len(json.dumps(tools)) // 4 + len(prompt) // 4

        for attempt in range(max_retries):
            try:
                # Check if we need to wait for rate limiting
                wait_time = self.rate_limiter.calculate_wait_time(estimated_tokens)
                if wait_time > 0:
                    if self.verbose:
                        print(f"  Rate limit protection: waiting {wait_time:.1f}s (current usage: {self.rate_limiter.get_current_usage():,} tokens/min)")
                    await asyncio.sleep(wait_time)

                # Make the LLM call
                llm_result = await self.llm_provider.generate_with_tools(
                    prompt=prompt,
                    tools=tools,
                    timeout=timeout
                )

                # Record successful token usage
                if llm_result.token_usage and "total" in llm_result.token_usage:
                    actual_tokens = llm_result.token_usage["total"]
                    self.rate_limiter.add_usage(actual_tokens)
                else:
                    # Fallback to estimate
                    self.rate_limiter.add_usage(estimated_tokens)

                return llm_result

            except Exception as e:
                error_msg = str(e)
                if self.rate_limiter.is_rate_limit_error(error_msg):
                    if attempt < max_retries - 1:
                        wait_time = 60 + (attempt * 30)  # Progressive backoff: 60s, 90s, 120s
                        if self.verbose:
                            print(f"  Rate limit hit (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        if self.verbose:
                            print(f"  Rate limit exceeded after {max_retries} attempts")
                        raise
                else:
                    # Non-rate-limit error, don't retry
                    raise

        # Should never reach here
        raise Exception(f"Failed after {max_retries} attempts")

    async def run_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        start_time = time.time()

        try:
            # Ensure initialized
            await self.initialize()

            # Get available MCP tools
            mcp_tools = await self.mcp_client.list_tools()

            # Format tools for LLM
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema
                    }
                }
                for tool in mcp_tools
            ]

            if self.verbose:
                print(f"Running test: {test_case.name}")
                print(f"Prompt: {test_case.prompt}")
                print(f"Available tools: {len(formatted_tools)}")

            # Get LLM response with tool calls (with rate limiting)
            llm_result = await self._call_llm_with_rate_limiting(
                prompt=test_case.prompt,
                tools=formatted_tools,
                timeout=test_case.timeout
            )

            # Execute tool calls if any
            tool_results = []
            if llm_result.tool_calls:
                for tool_call in llm_result.tool_calls:
                    mcp_tool_call = MCPToolCall(
                        name=tool_call["name"],
                        arguments=tool_call.get("arguments", {})
                    )
                    result = await self.mcp_client.call_tool(mcp_tool_call)
                    tool_results.append(result)

            # Prepare context for evaluators
            context = {
                "prompt": test_case.prompt,
                "response": llm_result.response,
                "tool_calls": llm_result.tool_calls,
                "tool_results": tool_results,
                "metadata": {
                    "duration_seconds": time.time() - start_time,
                    "model": self.model,
                    "total_tokens": llm_result.token_usage.get("total", 0) if llm_result.token_usage else 0,
                    "cost": llm_result.cost
                }
            }

            # Run evaluators
            evaluations = []
            all_passed = True
            total_score = 0.0

            for eval_config in test_case.evaluators:
                evaluator = self._create_evaluator(eval_config)
                eval_result = evaluator.evaluate(context)

                evaluations.append({
                    "evaluator": evaluator.name,
                    "passed": eval_result.passed,
                    "score": eval_result.score,
                    "reason": eval_result.reason,
                    "details": eval_result.details
                })

                if self.verbose:
                    status = "PASS" if eval_result.passed else "FAIL"
                    print(f"  Evaluator {evaluator.name}: {status} (score: {eval_result.score:.2f})")
                    print(f"    Reason: {eval_result.reason}")
                    if eval_result.details:
                        print(f"    Details: {eval_result.details}")

                if not eval_result.passed:
                    all_passed = False
                total_score += eval_result.score

            if self.verbose:
                # Display LLM response
                print(f"  LLM Response:")
                response_lines = llm_result.response.split('\n')
                for line in response_lines:
                    print(f"    {line}")

                # Display tool calls if any
                if llm_result.tool_calls:
                    print(f"  Tool Calls: {len(llm_result.tool_calls)}")
                    for i, tool_call in enumerate(llm_result.tool_calls, 1):
                        print(f"    {i}. {tool_call.get('name', 'unknown')}({tool_call.get('arguments', {})})")

                # Display token usage and cost information
                tokens = llm_result.token_usage
                if tokens:
                    print(f"  Token Usage:")
                    if "prompt" in tokens:
                        print(f"    Input: {tokens['prompt']} tokens")
                    if "completion" in tokens:
                        print(f"    Output: {tokens['completion']} tokens")
                    if "total" in tokens:
                        print(f"    Total: {tokens['total']} tokens")

                if llm_result.cost > 0:
                    print(f"  Cost: ${llm_result.cost:.4f}")

            avg_score = total_score / len(test_case.evaluators) if test_case.evaluators else 0.0

            return TestResult(
                test_name=test_case.name,
                passed=all_passed,
                score=avg_score,
                duration=time.time() - start_time,
                reason="All evaluators passed" if all_passed else "Some evaluators failed",
                tool_calls=llm_result.tool_calls,
                tool_results=tool_results,
                response=llm_result.response,
                evaluations=evaluations,
                cost=llm_result.cost,
                token_usage=llm_result.token_usage
            )

        except Exception as e:
            return TestResult(
                test_name=test_case.name,
                passed=False,
                score=0.0,
                duration=time.time() - start_time,
                reason=f"Test failed with error: {str(e)}",
                error=str(e)
            )

    async def run_tests(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Run multiple test cases."""
        results = []

        try:
            await self.initialize()

            for i, test_case in enumerate(test_cases):
                result = await self.run_test(test_case)
                results.append(result)

                if self.verbose:
                    print(f"Test {test_case.name}: {'PASS' if result.passed else 'FAIL'} (score: {result.score:.2f})")

                # Intelligent rate limiting now handled per-request, no fixed delays needed

        finally:
            await self.cleanup()

        return results

    def _create_evaluator(self, eval_config: Dict[str, Any]) -> BaseEvaluator:
        """Create evaluator from configuration."""
        if isinstance(eval_config, str):
            # Simple evaluator name
            return create_evaluator(eval_config)

        # Evaluator with configuration
        name = eval_config.get("name")
        args = eval_config.get("args", {})
        return create_evaluator(name, **args)

    async def cleanup(self):
        """Clean up resources."""
        if self.llm_provider:
            await self.llm_provider.close()
        if self.mcp_client:
            await self.mcp_client.close()


# Batch test runner for running multiple test suites

class BatchTestRunner:
    """Run multiple test suites with different models."""

    def __init__(self, mcp_url: str = "http://localhost:5008/mcp/"):
        self.mcp_url = mcp_url
        self.results: Dict[str, List[TestResult]] = {}

    async def run_suite_with_models(
        self,
        test_cases: List[TestCase],
        models: List[Dict[str, str]]
    ) -> Dict[str, List[TestResult]]:
        """
        Run test suite with multiple models.

        Args:
            test_cases: List of test cases to run
            models: List of dicts with 'provider' and 'model' keys

        Returns:
            Dictionary mapping model names to test results
        """
        for model_config in models:
            provider = model_config["provider"]
            model = model_config["model"]
            model_key = f"{provider}:{model}"

            print(f"\nRunning tests with {model_key}")

            runner = TestRunner(
                model=model,
                provider=provider,
                mcp_url=self.mcp_url
            )

            results = await runner.run_tests(test_cases)
            self.results[model_key] = results

        return self.results

    def generate_comparison_report(self) -> Dict[str, Any]:
        """Generate comparison report across all models."""
        report = {
            "models": list(self.results.keys()),
            "test_count": len(next(iter(self.results.values()))) if self.results else 0,
            "model_summaries": {},
            "test_comparisons": {}
        }

        # Generate per-model summaries
        for model, results in self.results.items():
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            avg_score = sum(r.score for r in results) / total if total > 0 else 0
            avg_duration = sum(r.duration for r in results) / total if total > 0 else 0

            report["model_summaries"][model] = {
                "passed": passed,
                "failed": total - passed,
                "total": total,
                "success_rate": passed / total if total > 0 else 0,
                "avg_score": avg_score,
                "avg_duration": avg_duration
            }

        # Generate per-test comparisons
        if self.results:
            first_results = next(iter(self.results.values()))
            for i, test_result in enumerate(first_results):
                test_name = test_result.test_name
                report["test_comparisons"][test_name] = {}

                for model, results in self.results.items():
                    if i < len(results):
                        result = results[i]
                        report["test_comparisons"][test_name][model] = {
                            "passed": result.passed,
                            "score": result.score,
                            "duration": result.duration
                        }

        return report