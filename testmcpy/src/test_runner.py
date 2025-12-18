"""
Test runner for executing MCP test cases with LLMs.
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..evals.base_evaluators import BaseEvaluator, create_evaluator
from .llm_integration import LLMProvider, create_llm_provider
from .mcp_client import MCPClient, MCPToolCall


class RateLimitTracker:
    """Track token usage and manage rate limiting."""

    def __init__(self, tokens_per_minute_limit: int = 40000):  # More conservative limit
        self.tokens_per_minute_limit = tokens_per_minute_limit
        self.token_usage_history = []  # List of (timestamp, tokens) tuples

    def add_usage(self, tokens: int):
        """Record token usage with timestamp."""
        self.token_usage_history.append((datetime.now(), tokens))
        # Clean up old entries (older than 1 minute)
        cutoff = datetime.now() - timedelta(minutes=1)
        self.token_usage_history = [
            (ts, tokens) for ts, tokens in self.token_usage_history if ts > cutoff
        ]

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
class TestStep:
    """A single step in a multi-turn test."""

    prompt: str
    evaluators: list[dict[str, Any]] = field(default_factory=list)
    name: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestStep":
        """Create TestStep from dictionary."""
        return cls(
            prompt=data["prompt"],
            evaluators=data.get("evaluators", []),
            name=data.get("name"),
            timeout=data.get("timeout", 30.0),
        )


@dataclass
class TestCase:
    """Represents a single test case.

    For single-turn tests:
        - Use `prompt` and `evaluators` directly

    For multi-turn tests:
        - Use `steps` array with sequential prompts
        - Each step has its own evaluators
        - Context is carried between steps

    Example YAML (single-turn):
        name: test_list_charts
        prompt: "List all charts"
        evaluators:
          - name: was_mcp_tool_called
            args: {tool_name: "list_charts"}

    Example YAML (multi-turn):
        name: test_create_and_view
        steps:
          - prompt: "Create a bar chart showing sales"
            evaluators:
              - name: was_chart_created
          - prompt: "Now show me the chart data"
            evaluators:
              - name: response_includes
                args: {content: "data"}
    """

    name: str
    prompt: str
    evaluators: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    expected_tools: list[str] | None = None
    timeout: float = 30.0
    auth: dict[str, Any] | None = None
    steps: list[TestStep] | None = None  # For multi-turn tests

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        """Create TestCase from dictionary."""
        # Parse steps if present
        steps = None
        if "steps" in data:
            steps = [TestStep.from_dict(s) for s in data["steps"]]
            # For multi-turn, use first step's prompt as default
            prompt = data.get("prompt", steps[0].prompt if steps else "")
            evaluators = data.get("evaluators", steps[0].evaluators if steps else [])
        else:
            prompt = data["prompt"]
            evaluators = data.get("evaluators", [])

        return cls(
            name=data["name"],
            prompt=prompt,
            evaluators=evaluators,
            metadata=data.get("metadata", {}),
            expected_tools=data.get("expected_tools"),
            timeout=data.get("timeout", 30.0),
            auth=data.get("auth"),
            steps=steps,
        )

    @property
    def is_multi_turn(self) -> bool:
        """Check if this is a multi-turn test."""
        return self.steps is not None and len(self.steps) > 1


@dataclass
class StepResult:
    """Result from a single step in a multi-turn test."""

    step_index: int
    step_name: str | None
    prompt: str
    passed: bool
    response: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None


@dataclass
class TestResult:
    """Result from running a test case."""

    test_name: str
    passed: bool
    score: float
    duration: float
    reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    response: str | None = None
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    cost: float = 0.0
    token_usage: dict[str, int] | None = None
    error: str | None = None
    step_results: list[StepResult] | None = None  # For multi-turn tests
    auth_success: bool | None = None
    auth_token: str | None = None
    auth_error: str | None = None
    auth_error_message: str | None = None
    auth_flow_steps: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)  # Provider execution logs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class TestRunner:
    """Runs test cases against MCP service with LLM."""

    def __init__(
        self,
        model: str,
        provider: str = "ollama",
        mcp_url: str | None = None,
        mcp_client: MCPClient | None = None,
        verbose: bool = False,
        hide_tool_output: bool = False,
        log_callback=None,
    ):
        self.model = model
        self.provider = provider
        self.mcp_url = mcp_url
        self.verbose = verbose
        self.hide_tool_output = hide_tool_output
        self.llm_provider: LLMProvider | None = None
        self.rate_limiter = RateLimitTracker()
        self.mcp_client: MCPClient | None = mcp_client
        # Track if we own the client (created it ourselves) vs external
        self._owns_mcp_client = mcp_client is None
        # Optional callback for real-time log streaming
        self.log_callback = log_callback

    def _log(self, message: str, force: bool = False):
        """Log a message to console and optionally via callback."""
        if self.verbose or force:
            print(message)
        if self.log_callback:
            # Call the callback (might be async, so we handle both)
            import asyncio

            try:
                if asyncio.iscoroutinefunction(self.log_callback):
                    # Schedule async callback
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.log_callback(message))
                    else:
                        loop.run_until_complete(self.log_callback(message))
                else:
                    self.log_callback(message)
            except RuntimeError:
                # No event loop, skip callback
                pass

    async def initialize(self):
        """Initialize LLM provider and MCP client."""
        if not self.llm_provider:
            # Get auth config dict from mcp_client if available
            auth = None
            if self.mcp_client and hasattr(self.mcp_client, "auth_config"):
                auth = self.mcp_client.auth_config
            self.llm_provider = create_llm_provider(
                provider=self.provider,
                model=self.model,
                mcp_url=self.mcp_url,
                auth=auth,
                log_callback=self.log_callback,
            )
            await self.llm_provider.initialize()

        if not self.mcp_client:
            self.mcp_client = MCPClient(self.mcp_url)
            await self.mcp_client.initialize()

    async def _call_llm_with_rate_limiting(
        self, prompt: str, tools: list[dict], timeout: float, max_retries: int = 3, **kwargs
    ):
        """Call LLM with intelligent rate limiting and retry logic."""
        # Skip rate limiting for CLI providers (they use subscription, not API)
        is_cli_provider = self.provider in ("claude-cli", "claude-code", "codex-cli", "codex")

        if is_cli_provider:
            # For CLI providers, just make the call directly
            llm_result = await self.llm_provider.generate_with_tools(
                prompt=prompt, tools=tools, timeout=timeout, **kwargs
            )
            llm_result.wait_time = 0.0
            return llm_result

        # API rate limiting logic below
        # Conservative token estimation - we know cache tokens are ~46K from previous runs
        # Use fixed conservative estimates to avoid 429 errors
        estimated_request_tokens = len(prompt) // 3  # More conservative ratio
        estimated_cache_tokens = 46000  # Fixed based on actual observed cache usage
        estimated_tokens = estimated_request_tokens + estimated_cache_tokens

        if self.verbose:
            print(
                f"  Token estimation: {estimated_request_tokens} request + {estimated_cache_tokens} cache = {estimated_tokens} total"
            )

        total_wait_time = 0.0  # Track wait time separately

        for attempt in range(max_retries):
            try:
                # Check if we need to wait for rate limiting
                wait_time = self.rate_limiter.calculate_wait_time(estimated_tokens)
                if wait_time > 0:
                    if self.verbose:
                        print(
                            f"  Rate limit protection: waiting {wait_time:.1f}s (current usage: {self.rate_limiter.get_current_usage():,} tokens/min)"
                        )
                    await asyncio.sleep(wait_time)
                    total_wait_time += wait_time

                # Make the LLM call
                llm_result = await self.llm_provider.generate_with_tools(
                    prompt=prompt, tools=tools, timeout=timeout, **kwargs
                )

                # Record successful token usage - include cache tokens for rate limiting
                if llm_result.token_usage:
                    # For rate limiting, we need to count all tokens that count toward the rate limit
                    # This includes both charged tokens and cached tokens (even though cached are free)
                    rate_limit_tokens = 0
                    if "total" in llm_result.token_usage:
                        rate_limit_tokens += llm_result.token_usage["total"]
                    if "cache_read" in llm_result.token_usage:
                        rate_limit_tokens += llm_result.token_usage["cache_read"]

                    self.rate_limiter.add_usage(rate_limit_tokens)

                    if self.verbose:
                        charged = llm_result.token_usage.get("total", 0)
                        cached = llm_result.token_usage.get("cache_read", 0)
                        print(
                            f"  Rate limit tracking: {charged} charged + {cached} cached = {rate_limit_tokens} total tokens"
                        )
                else:
                    # Fallback to estimate
                    self.rate_limiter.add_usage(estimated_tokens)

                # Store wait time in the result for duration adjustment
                llm_result.wait_time = total_wait_time

                return llm_result

            except Exception as e:
                error_msg = str(e)
                if self.rate_limiter.is_rate_limit_error(error_msg):
                    if attempt < max_retries - 1:
                        retry_wait_time = 60 + (attempt * 30)  # Progressive backoff: 60s, 90s, 120s
                        if self.verbose:
                            print(
                                f"  Rate limit hit (attempt {attempt + 1}/{max_retries}). Waiting {retry_wait_time}s before retry..."
                            )
                        await asyncio.sleep(retry_wait_time)
                        total_wait_time += retry_wait_time
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

        # Track auth metadata
        auth_success = None
        auth_token = None
        auth_error = None
        auth_error_message = None
        auth_flow_steps = []

        try:
            # Ensure initialized
            await self.initialize()

            # If test has auth config, create a temporary MCP client with that auth
            test_mcp_client = self.mcp_client
            if test_case.auth:
                if self.verbose:
                    print(
                        f"  Using test-specific auth configuration: {test_case.auth.get('type', 'unknown')}"
                    )

                # Create a new MCP client with the test's auth config
                test_mcp_client = MCPClient(self.mcp_url, auth=test_case.auth)

                try:
                    # Initialize and capture auth info
                    await test_mcp_client.initialize()

                    # Auth succeeded if we got here
                    auth_success = True

                    # Try to get the token from the client's auth object
                    if test_mcp_client.auth and hasattr(test_mcp_client.auth, "token"):
                        auth_token = test_mcp_client.auth.token

                    # Get auth flow steps from the client's debugger if available
                    # Note: We'd need to modify MCPClient to expose its debugger
                    # For now, we'll infer steps from successful auth
                    auth_type = test_case.auth.get("type", "unknown")
                    if auth_type == "oauth":
                        auth_flow_steps = [
                            "request_prepared",
                            "token_endpoint_called",
                            "response_received",
                            "token_extracted",
                        ]
                    elif auth_type == "jwt":
                        auth_flow_steps = [
                            "request_prepared",
                            "jwt_endpoint_called",
                            "response_received",
                            "token_extracted",
                        ]
                    elif auth_type == "bearer":
                        auth_flow_steps = ["token_validated"]

                except Exception as auth_exc:
                    auth_success = False
                    auth_error = str(auth_exc)
                    auth_error_message = str(auth_exc)
                    if self.verbose:
                        print(f"  Authentication failed: {auth_error}")

            # Get available MCP tools
            mcp_tools = await test_mcp_client.list_tools()

            # Format tools for LLM
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in mcp_tools
            ]

            if self.verbose:
                self._log(f"Running test: {test_case.name}")
                self._log(f"Prompt: {test_case.prompt}")
                self._log(f"Available tools: {len(formatted_tools)}")
                self._log(f"Provider: {self.provider}, Model: {self.model}")
                self._log(f"MCP URL: {self.mcp_url}")

            # Determine timeout - CLI providers need more time
            # Use at least 120s for claude-cli and codex-cli
            effective_timeout = test_case.timeout
            if self.provider in ("claude-cli", "claude-code", "codex-cli", "codex"):
                effective_timeout = max(test_case.timeout, 120.0)
                if self.verbose and effective_timeout > test_case.timeout:
                    self._log(f"  Using extended timeout {effective_timeout}s for CLI provider")

            # Get LLM response with tool calls (with rate limiting)
            llm_result = await self._call_llm_with_rate_limiting(
                prompt=test_case.prompt, tools=formatted_tools, timeout=effective_timeout
            )

            # Show requested tool calls before executing them
            if self.verbose and not self.hide_tool_output and llm_result.tool_calls:
                self._log(f"  LLM requested {len(llm_result.tool_calls)} tool call(s):")
                for i, tool_call in enumerate(llm_result.tool_calls, 1):
                    name = tool_call.get("name", "unknown")
                    args = tool_call.get("arguments", {})
                    # Pretty print arguments as JSON
                    if args:
                        args_json = json.dumps(args, indent=6)
                        self._log(f"    {i}. {name}(")
                        self._log(f"      {args_json}")
                        self._log("    )")
                    else:
                        self._log(f"    {i}. {name}()")

            # Execute tool calls if any (skip if already executed by provider like Claude CLI)
            tool_results = []
            if llm_result.tool_results:
                # Use pre-executed results from providers like Claude CLI
                tool_results = llm_result.tool_results
                if self.verbose and not self.hide_tool_output:
                    self._log(
                        f"  Using {len(tool_results)} pre-executed tool results from provider"
                    )
            elif llm_result.tool_calls:
                if self.verbose and not self.hide_tool_output:
                    self._log("  Executing tool calls...")
                for tool_call in llm_result.tool_calls:
                    mcp_tool_call = MCPToolCall(
                        name=tool_call["name"], arguments=tool_call.get("arguments", {})
                    )
                    result = await test_mcp_client.call_tool(mcp_tool_call)
                    tool_results.append(result)

            # Prepare context for evaluators (include auth metadata)
            context = {
                "prompt": test_case.prompt,
                "response": llm_result.response,
                "tool_calls": llm_result.tool_calls,
                "tool_results": tool_results,
                "metadata": {
                    "duration_seconds": time.time() - start_time,
                    "model": self.model,
                    "total_tokens": llm_result.token_usage.get("total", 0)
                    if llm_result.token_usage
                    else 0,
                    "cost": llm_result.cost,
                    "auth_success": auth_success,
                    "auth_token": auth_token,
                    "auth_error": auth_error,
                    "auth_error_message": auth_error_message,
                    "auth_flow_steps": auth_flow_steps,
                },
            }

            # Run evaluators
            evaluations = []
            all_passed = True
            total_score = 0.0

            for eval_config in test_case.evaluators:
                evaluator = self._create_evaluator(eval_config)
                eval_result = evaluator.evaluate(context)

                evaluations.append(
                    {
                        "evaluator": evaluator.name,
                        "passed": eval_result.passed,
                        "score": eval_result.score,
                        "reason": eval_result.reason,
                        "details": eval_result.details,
                    }
                )

                if self.verbose:
                    status = "PASS" if eval_result.passed else "FAIL"
                    self._log(
                        f"  Evaluator {evaluator.name}: {status} (score: {eval_result.score:.2f})"
                    )
                    self._log(f"    Reason: {eval_result.reason}")
                    if eval_result.details:
                        self._log(f"    Details: {eval_result.details}")

                if not eval_result.passed:
                    all_passed = False
                total_score += eval_result.score

            if self.verbose and not self.hide_tool_output:
                # Display LLM response
                self._log("  LLM Response:")
                response_lines = llm_result.response.split("\n")
                for line in response_lines:
                    self._log(f"    {line}")

                # Display tool calls if any
                if llm_result.tool_calls:
                    self._log(f"  Tool Calls: {len(llm_result.tool_calls)}")
                    for i, tool_call in enumerate(llm_result.tool_calls, 1):
                        self._log(
                            f"    {i}. {tool_call.get('name', 'unknown')}({tool_call.get('arguments', {})})"
                        )

                # Display token usage and cost information
                tokens = llm_result.token_usage
                if tokens:
                    self._log("  Token Usage:")
                    if "prompt" in tokens:
                        self._log(f"    Input: {tokens['prompt']} tokens")
                    if "completion" in tokens:
                        self._log(f"    Output: {tokens['completion']} tokens")
                    if tokens.get("cache_creation", 0) > 0:
                        self._log(f"    Cache Creation: {tokens['cache_creation']} tokens")
                    if tokens.get("cache_read", 0) > 0:
                        self._log(f"    Cache Read: {tokens['cache_read']} tokens (FREE!)")
                    if "total" in tokens:
                        self._log(f"    Total: {tokens['total']} tokens")

                if llm_result.cost > 0:
                    self._log(f"  Cost: ${llm_result.cost:.4f}")

            avg_score = total_score / len(test_case.evaluators) if test_case.evaluators else 0.0

            # Calculate actual execution duration (excluding wait times)
            total_duration = time.time() - start_time
            wait_time = getattr(llm_result, "wait_time", 0.0)
            actual_duration = max(0.0, total_duration - wait_time)  # Ensure non-negative

            if self.verbose and wait_time > 0:
                self._log(
                    f"  Timing: {actual_duration:.2f}s execution + {wait_time:.2f}s wait = {total_duration:.2f}s total"
                )

            # Create detailed reason message
            if all_passed:
                reason = "All evaluators passed"
            else:
                failed_evals = [e for e in evaluations if not e["passed"]]
                failed_names = [e["evaluator"] for e in failed_evals]
                if len(failed_evals) == 1:
                    reason = f"Failed: {failed_names[0]}"
                else:
                    reason = f"Failed: {', '.join(failed_names)}"

            return TestResult(
                test_name=test_case.name,
                passed=all_passed,
                score=avg_score,
                duration=actual_duration,
                reason=reason,
                tool_calls=llm_result.tool_calls,
                tool_results=tool_results,
                response=llm_result.response,
                evaluations=evaluations,
                cost=llm_result.cost,
                token_usage=llm_result.token_usage,
                auth_success=auth_success,
                auth_token=auth_token,
                auth_error=auth_error,
                auth_error_message=auth_error_message,
                auth_flow_steps=auth_flow_steps,
                logs=llm_result.logs if hasattr(llm_result, "logs") else [],
            )

        except Exception as e:
            # Calculate duration excluding any wait times even for failed tests
            total_duration = time.time() - start_time
            # Try to get wait time from any partial LLM result, default to 0
            wait_time = 0.0
            logs = []
            if "llm_result" in locals():
                if hasattr(llm_result, "wait_time"):
                    wait_time = llm_result.wait_time
                if hasattr(llm_result, "logs"):
                    logs = llm_result.logs
            actual_duration = max(0.0, total_duration - wait_time)

            return TestResult(
                test_name=test_case.name,
                passed=False,
                score=0.0,
                duration=actual_duration,
                reason=f"Test failed with error: {str(e)}",
                error=str(e),
                auth_success=auth_success,
                auth_token=auth_token,
                auth_error=auth_error,
                auth_error_message=auth_error_message,
                auth_flow_steps=auth_flow_steps,
                logs=logs,
            )

        finally:
            # Clean up test-specific MCP client if one was created
            if (
                test_case.auth
                and "test_mcp_client" in locals()
                and test_mcp_client != self.mcp_client
            ):
                try:
                    await test_mcp_client.close()
                except Exception:
                    pass  # Ignore cleanup errors

    async def run_multi_turn_test(self, test_case: TestCase) -> TestResult:
        """Run a multi-turn test with sequential steps sharing context."""
        if not test_case.is_multi_turn:
            return await self.run_test(test_case)

        start_time = time.time()
        step_results: list[StepResult] = []
        all_tool_calls: list[dict] = []
        all_tool_results: list[dict] = []
        all_evaluations: list[dict] = []
        conversation_history: list[dict] = []  # Maintains context
        total_cost = 0.0
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}

        try:
            await self.initialize()

            # Get MCP tools once
            mcp_tools = await self.mcp_client.list_tools()
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in mcp_tools
            ]

            overall_passed = True

            for step_idx, step in enumerate(test_case.steps):
                step_start = time.time()
                step_name = step.name or f"step_{step_idx + 1}"

                if self.verbose:
                    print(f"  Step {step_idx + 1}/{len(test_case.steps)}: {step.prompt[:50]}...")

                # Determine timeout - CLI providers need more time
                effective_timeout = step.timeout
                if self.provider in ("claude-cli", "claude-code", "codex-cli", "codex"):
                    effective_timeout = max(step.timeout, 120.0)

                # Call LLM with conversation history
                llm_result = await self._call_llm_with_rate_limiting(
                    prompt=step.prompt,
                    tools=formatted_tools,
                    timeout=effective_timeout,
                    messages=conversation_history if conversation_history else None,
                )

                # Execute tool calls (skip if already executed by provider like Claude CLI)
                tool_results = []
                if llm_result.tool_results:
                    # Use pre-executed results from providers like Claude CLI
                    tool_results = llm_result.tool_results
                elif llm_result.tool_calls:
                    for tool_call in llm_result.tool_calls:
                        mcp_tool_call = MCPToolCall(
                            name=tool_call["name"],
                            arguments=tool_call.get("arguments", {}),
                        )
                        result = await self.mcp_client.call_tool(mcp_tool_call)
                        tool_results.append(result)

                # Update conversation history
                conversation_history.append({"role": "user", "content": step.prompt})
                if llm_result.response:
                    conversation_history.append(
                        {"role": "assistant", "content": llm_result.response}
                    )

                # Run evaluators for this step
                step_evaluations = []
                step_passed = True

                if step.evaluators:
                    from testmcpy.evals.base_evaluators import create_evaluator

                    context = {
                        "prompt": step.prompt,
                        "response": llm_result.response,
                        "tool_calls": llm_result.tool_calls,
                        "tool_results": tool_results,
                        "conversation_history": conversation_history,
                        "step_index": step_idx,
                    }

                    for eval_config in step.evaluators:
                        eval_name = eval_config.get("name") or eval_config.get("type")
                        eval_args = eval_config.get("args", {})
                        try:
                            evaluator = create_evaluator(eval_name, **eval_args)
                            eval_result = evaluator.evaluate(context)
                            step_evaluations.append(
                                {
                                    "evaluator": eval_name,
                                    "passed": eval_result.passed,
                                    "score": eval_result.score,
                                    "reason": eval_result.reason,
                                }
                            )
                            if not eval_result.passed:
                                step_passed = False
                        except Exception as e:
                            step_evaluations.append(
                                {
                                    "evaluator": eval_name,
                                    "passed": False,
                                    "score": 0.0,
                                    "reason": f"Evaluator error: {str(e)}",
                                }
                            )
                            step_passed = False

                # Track overall results
                if not step_passed:
                    overall_passed = False

                all_tool_calls.extend(llm_result.tool_calls)
                all_tool_results.extend(
                    [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in tool_results]
                )
                all_evaluations.extend(step_evaluations)
                total_cost += llm_result.cost
                if llm_result.token_usage:
                    for k in total_tokens:
                        total_tokens[k] += llm_result.token_usage.get(k, 0)

                step_results.append(
                    StepResult(
                        step_index=step_idx,
                        step_name=step_name,
                        prompt=step.prompt,
                        passed=step_passed,
                        response=llm_result.response,
                        tool_calls=llm_result.tool_calls,
                        evaluations=step_evaluations,
                        duration=time.time() - step_start,
                    )
                )

            # Calculate overall score
            total_evals = len(all_evaluations) if all_evaluations else 1
            passed_evals = sum(1 for e in all_evaluations if e.get("passed"))
            score = passed_evals / total_evals

            return TestResult(
                test_name=test_case.name,
                passed=overall_passed,
                score=score,
                duration=time.time() - start_time,
                reason=f"Multi-turn: {len(step_results)} steps, {passed_evals}/{total_evals} evaluations passed",
                tool_calls=all_tool_calls,
                tool_results=all_tool_results,
                response=step_results[-1].response if step_results else None,
                evaluations=all_evaluations,
                cost=total_cost,
                token_usage=total_tokens,
                step_results=step_results,
            )

        except Exception as e:
            return TestResult(
                test_name=test_case.name,
                passed=False,
                score=0.0,
                duration=time.time() - start_time,
                error=str(e),
                reason=f"Multi-turn test failed: {str(e)}",
                step_results=step_results,
            )

    async def run_tests(self, test_cases: list[TestCase]) -> list[TestResult]:
        """Run multiple test cases."""
        results = []

        try:
            await self.initialize()

            for i, test_case in enumerate(test_cases):
                # Try the test with retry logic for rate limit failures
                result = await self._run_test_with_retry(test_case)
                results.append(result)

                if self.verbose:
                    print(
                        f"Test {test_case.name}: {'PASS' if result.passed else 'FAIL'} (score: {result.score:.2f})"
                    )

                # Add minimum delay between tests to prevent rate limiting bursts
                # Skip delay for CLI providers (they use subscription, not API rate limits)
                if i < len(test_cases) - 1:  # Don't wait after the last test
                    if self.provider in ("claude-cli", "claude-code", "codex-cli", "codex"):
                        min_delay = 1  # Minimal delay for CLI providers
                    else:
                        min_delay = 15  # 15 seconds for API providers
                    if self.verbose and min_delay > 1:
                        print(
                            f"  Waiting {min_delay}s before next test to prevent rate limiting..."
                        )
                    await asyncio.sleep(min_delay)

        finally:
            await self.cleanup()

        return results

    async def _run_test_with_retry(
        self, test_case: TestCase, max_test_retries: int = 2
    ) -> TestResult:
        """Run a test with retry logic for rate limit failures."""
        for attempt in range(max_test_retries + 1):
            # Use multi-turn runner for multi-step tests
            if test_case.is_multi_turn:
                result = await self.run_multi_turn_test(test_case)
            else:
                result = await self.run_test(test_case)

            # Check if this was a rate limit failure
            is_rate_limit_failure = (
                not result.passed
                and result.error
                and self.rate_limiter.is_rate_limit_error(result.error)
            )

            # Also check if the response contains rate limit error
            is_rate_limit_response = (
                not result.passed
                and result.response
                and ("rate_limit" in result.response.lower() or "429" in result.response)
            )

            if (is_rate_limit_failure or is_rate_limit_response) and attempt < max_test_retries:
                retry_wait = 120 + (attempt * 60)  # 120s, 180s, etc.
                if self.verbose:
                    print(
                        f"  Test failed due to rate limiting (attempt {attempt + 1}/{max_test_retries + 1})"
                    )
                    print(f"  Waiting {retry_wait}s before retrying test...")
                await asyncio.sleep(retry_wait)
                continue
            else:
                # Test passed or non-rate-limit failure or out of retries
                return result

        return result

    def _create_evaluator(self, eval_config: dict[str, Any]) -> BaseEvaluator:
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
        # Only close MCP client if we created it (not externally provided)
        if self.mcp_client and self._owns_mcp_client:
            await self.mcp_client.close()


# Batch test runner for running multiple test suites


class BatchTestRunner:
    """Run multiple test suites with different models."""

    def __init__(self, mcp_url: str | None = None):
        self.mcp_url = mcp_url
        self.results: dict[str, list[TestResult]] = {}

    async def run_suite_with_models(
        self, test_cases: list[TestCase], models: list[dict[str, str]]
    ) -> dict[str, list[TestResult]]:
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

            runner = TestRunner(model=model, provider=provider, mcp_url=self.mcp_url)

            results = await runner.run_tests(test_cases)
            self.results[model_key] = results

        return self.results

    def generate_comparison_report(self) -> dict[str, Any]:
        """Generate comparison report across all models."""
        report = {
            "models": list(self.results.keys()),
            "test_count": len(next(iter(self.results.values()))) if self.results else 0,
            "model_summaries": {},
            "test_comparisons": {},
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
                "avg_duration": avg_duration,
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
                            "duration": result.duration,
                        }

        return report
