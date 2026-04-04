"""
Agent tools for the Test Execution Agent.

Each @tool-decorated function wraps existing testmcpy infrastructure,
making it available to the Claude Agent SDK orchestrator. The agent
uses these tools to orchestrate test execution, not to be the test subject.
"""

import json
import time
from pathlib import Path
from typing import Any

try:
    from claude_agent_sdk import tool
except ImportError:

    def tool(name, description, schema):  # type: ignore[misc]
        """Fallback decorator when claude_agent_sdk is not installed."""

        def decorator(func):
            func._tool_name = name
            func._tool_description = description
            func._tool_schema = schema
            return func

        return decorator


# Shared state for tools - set by orchestrator before agent runs
_tool_context: dict[str, Any] = {}


def set_tool_context(
    mcp_profile: str | None = None,
    mcp_url: str | None = None,
    auth_config: dict[str, Any] | None = None,
    storage_path: str | None = None,
) -> None:
    """Configure shared context for all agent tools.

    Called by the orchestrator before starting the agent run.
    """
    _tool_context["mcp_profile"] = mcp_profile
    _tool_context["mcp_url"] = mcp_url
    _tool_context["auth_config"] = auth_config
    _tool_context["storage_path"] = storage_path


def _get_mcp_url() -> str | None:
    """Resolve MCP URL from context (profile or direct URL)."""
    if _tool_context.get("mcp_url"):
        return _tool_context["mcp_url"]

    profile_id = _tool_context.get("mcp_profile")
    if profile_id:
        from testmcpy.config import Config

        cfg = Config(profile=profile_id)
        return cfg.get_mcp_url()

    return None


def _get_auth_config() -> dict[str, Any] | None:
    """Resolve auth config from context."""
    if _tool_context.get("auth_config"):
        return _tool_context["auth_config"]

    profile_id = _tool_context.get("mcp_profile")
    if profile_id:
        from testmcpy.config import Config

        cfg = Config(profile=profile_id)
        mcp_server = cfg.get_default_mcp_server()
        if mcp_server and mcp_server.auth:
            return mcp_server.auth.to_dict()

    return None


def _get_storage():
    """Get TestStorage instance."""
    from testmcpy.storage import TestStorage

    path = _tool_context.get("storage_path")
    return TestStorage(db_path=path) if path else TestStorage()


def _text_result(data: Any) -> dict[str, Any]:
    """Format a successful tool result."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}]}


def _error_result(message: str) -> dict[str, Any]:
    """Format an error tool result."""
    return {"content": [{"type": "text", "text": f"Error: {message}"}], "is_error": True}


# ---------------------------------------------------------------------------
# Tool 1: Load Test Suite
# ---------------------------------------------------------------------------


@tool(
    "load_test_suite",
    "Load and parse test cases from a YAML/JSON file or directory. "
    "Returns parsed test case definitions with their prompts and evaluators.",
    {
        "test_path": str,
    },
)
async def load_test_suite(args: dict[str, Any]) -> dict[str, Any]:
    """Load test cases from a file or directory path."""
    test_path = Path(args["test_path"])

    if not test_path.exists():
        return _error_result(f"Path not found: {test_path}")

    try:
        import yaml

        from testmcpy.src.test_runner import TestCase

        test_cases = []

        if test_path.is_file():
            with open(test_path) as f:
                if test_path.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)

            if data is None:
                return _error_result(f"Empty file: {test_path}")

            if "tests" in data:
                for test_data in data["tests"]:
                    test_cases.append(TestCase.from_dict(test_data))
            elif "prompt" in data:
                test_cases.append(TestCase.from_dict(data))
            else:
                return _error_result(f"No 'tests' or 'prompt' key found in {test_path}")

        elif test_path.is_dir():
            for pattern in ["*.yaml", "*.yml", "*.json"]:
                for file in test_path.rglob(pattern):
                    # Skip hidden directories
                    if any(part.startswith(".") for part in file.relative_to(test_path).parts):
                        continue
                    with open(file) as f:
                        if file.suffix == ".json":
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                        if data is None:
                            continue
                        if "tests" in data:
                            for test_data in data["tests"]:
                                test_cases.append(TestCase.from_dict(test_data))
                        elif "prompt" in data:
                            test_cases.append(TestCase.from_dict(data))
        else:
            return _error_result(f"Path is not a file or directory: {test_path}")

        result = {
            "test_count": len(test_cases),
            "source": str(test_path),
            "tests": [
                {
                    "name": tc.name,
                    "prompt": tc.prompt,
                    "is_multi_turn": tc.is_multi_turn,
                    "evaluators": list(tc.evaluators),
                    "timeout": tc.timeout,
                }
                for tc in test_cases
            ],
        }
        return _text_result(result)

    except (yaml.YAMLError, json.JSONDecodeError) as e:
        return _error_result(f"Failed to parse {test_path}: {e}")
    except KeyError as e:
        return _error_result(f"Missing required field in test file: {e}")


# ---------------------------------------------------------------------------
# Tool 2: Execute Test Case
# ---------------------------------------------------------------------------


@tool(
    "execute_test_case",
    "Run a single test case against a subject LLM via the MCP service. "
    "Specify the test name and prompt, plus the model and provider to test. "
    "Returns pass/fail, score, tool calls, evaluations, cost, and token usage.",
    {
        "test_name": str,
        "prompt": str,
        "model": str,
        "provider": str,
    },
)
async def execute_test_case(args: dict[str, Any]) -> dict[str, Any]:
    """Execute a single test case against a subject LLM."""
    from testmcpy.src.test_runner import TestCase, TestRunner

    mcp_url = _get_mcp_url()
    if not mcp_url:
        return _error_result("No MCP URL configured. Set mcp_profile or mcp_url in agent context.")

    # Build a minimal TestCase
    evaluators_raw = args.get("evaluators", [])
    test_case = TestCase(
        name=args["test_name"],
        prompt=args["prompt"],
        evaluators=evaluators_raw if evaluators_raw else [{"name": "execution_successful"}],
        timeout=args.get("timeout", 60.0),
    )

    auth_config = _get_auth_config()
    try:
        from testmcpy.src.mcp_client import MCPClient

        mcp_client = MCPClient(base_url=mcp_url, auth=auth_config)
        await mcp_client.initialize()

        runner = TestRunner(
            model=args["model"],
            provider=args["provider"],
            mcp_client=mcp_client,
        )
        await runner.initialize()

        start = time.time()
        result = await runner.run_test(test_case)
        duration = time.time() - start

        await runner.cleanup()
        await mcp_client.close()

        return _text_result(
            {
                "test_name": result.test_name,
                "passed": result.passed,
                "score": result.score,
                "duration": round(duration, 2),
                "reason": result.reason,
                "tool_calls": result.tool_calls,
                "evaluations": result.evaluations,
                "cost": result.cost,
                "token_usage": result.token_usage,
                "response": (result.response[:500] if result.response else None),
            }
        )
    except (
        ConnectionError,
        TimeoutError,
        OSError,
    ) as e:
        return _error_result(f"Connection/network error running test: {e}")
    except ValueError as e:
        return _error_result(f"Invalid test configuration: {e}")


# ---------------------------------------------------------------------------
# Tool 3: List MCP Tools
# ---------------------------------------------------------------------------


@tool(
    "list_mcp_tools",
    "Discover all tools available on the MCP service. "
    "Returns tool names, descriptions, and input schemas.",
    {},
)
async def list_mcp_tools(args: dict[str, Any]) -> dict[str, Any]:
    """List all tools available on the configured MCP service."""
    mcp_url = _get_mcp_url()
    if not mcp_url:
        return _error_result("No MCP URL configured. Set mcp_profile or mcp_url in agent context.")

    auth_config = _get_auth_config()
    try:
        from testmcpy.src.mcp_client import MCPClient

        client = MCPClient(base_url=mcp_url, auth=auth_config)
        await client.initialize()
        tools = await client.list_tools()
        await client.close()

        return _text_result(
            {
                "tool_count": len(tools),
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    }
                    for t in tools
                ],
            }
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        return _error_result(f"Failed to connect to MCP service: {e}")


# ---------------------------------------------------------------------------
# Tool 4: Compare Model Results
# ---------------------------------------------------------------------------


@tool(
    "compare_model_results",
    "Run the same test cases across multiple LLM models and compare results. "
    "Provide a test file path and a list of models (each with provider and model name). "
    "Returns a cross-model comparison report.",
    {
        "test_path": str,
        "models": str,
    },
)
async def compare_model_results(args: dict[str, Any]) -> dict[str, Any]:
    """Run tests across multiple models and generate comparison."""
    import yaml

    from testmcpy.src.test_runner import BatchTestRunner, TestCase

    test_path = Path(args["test_path"])
    if not test_path.exists():
        return _error_result(f"Test path not found: {test_path}")

    # Parse models - expects JSON string like: [{"provider":"anthropic","model":"claude-sonnet-4-5"}]
    try:
        models = json.loads(args["models"])
    except json.JSONDecodeError as e:
        return _error_result(
            f"Invalid models JSON: {e}. "
            'Expected format: [{"provider":"anthropic","model":"claude-sonnet-4-5"}]'
        )

    # Load test cases
    try:
        test_cases = []
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        if "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        elif "prompt" in data:
            test_cases.append(TestCase.from_dict(data))
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        return _error_result(f"Failed to parse test file: {e}")

    if not test_cases:
        return _error_result("No test cases found in file")

    mcp_url = _get_mcp_url()

    try:
        batch_runner = BatchTestRunner(mcp_url=mcp_url)
        await batch_runner.run_suite_with_models(test_cases, models)
        report = batch_runner.generate_comparison_report()
        return _text_result(report)
    except (ConnectionError, TimeoutError, OSError) as e:
        return _error_result(f"Error during model comparison: {e}")
    except ValueError as e:
        return _error_result(f"Invalid model configuration: {e}")


# ---------------------------------------------------------------------------
# Tool 5: Get Historical Results
# ---------------------------------------------------------------------------


@tool(
    "get_historical_results",
    "Retrieve historical test results for regression analysis. "
    "Can filter by test path, model, and time range. "
    "Supports getting trends, failing tests, and model comparisons.",
    {
        "query_type": str,
    },
)
async def get_historical_results(args: dict[str, Any]) -> dict[str, Any]:
    """Query historical test results from storage."""
    query_type = args["query_type"]
    storage = _get_storage()

    try:
        if query_type == "trends":
            data = storage.get_trends(
                test_path=args.get("test_path"),
                model=args.get("model"),
                days=args.get("days", 30),
            )
            return _text_result({"query": "trends", "data": data})

        elif query_type == "failing_tests":
            data = storage.get_failing_tests(
                days=args.get("days", 7),
                min_failures=args.get("min_failures", 2),
            )
            return _text_result({"query": "failing_tests", "data": data})

        elif query_type == "model_comparison":
            data = storage.get_model_comparison(days=args.get("days", 30))
            return _text_result({"query": "model_comparison", "data": data})

        elif query_type == "pass_rate":
            data = storage.get_pass_rate(
                test_path=args.get("test_path"),
                model=args.get("model"),
                days=args.get("days", 30),
            )
            return _text_result({"query": "pass_rate", "data": data})

        else:
            return _error_result(
                f"Unknown query_type: {query_type}. "
                "Valid options: trends, failing_tests, model_comparison, pass_rate"
            )
    except (KeyError, TypeError) as e:
        return _error_result(f"Invalid query parameters: {e}")


# ---------------------------------------------------------------------------
# Tool 6: Run Smoke Test
# ---------------------------------------------------------------------------


@tool(
    "run_smoke_test",
    "Run smoke tests on the MCP server to check basic health. "
    "Tests connection, tool discovery, and calling each tool with reasonable parameters.",
    {},
)
async def run_smoke_test_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Run smoke tests on the MCP server."""
    mcp_url = _get_mcp_url()
    if not mcp_url:
        return _error_result("No MCP URL configured. Set mcp_profile or mcp_url in agent context.")

    auth_config = _get_auth_config()
    try:
        from testmcpy.smoke_test import run_smoke_test

        report = await run_smoke_test(
            mcp_url=mcp_url,
            auth_config=auth_config,
            test_all_tools=args.get("test_all_tools", True),
            max_tools_to_test=args.get("max_tools", 10),
        )
        return _text_result(report.to_dict())
    except (ConnectionError, TimeoutError, OSError) as e:
        return _error_result(f"Smoke test failed - connection error: {e}")


# ---------------------------------------------------------------------------
# Tool 7: Store Results
# ---------------------------------------------------------------------------


@tool(
    "store_results",
    "Persist test results to storage for historical tracking. "
    "Provide the test path, test name, and result details.",
    {
        "test_path": str,
        "test_name": str,
        "passed": bool,
    },
)
async def store_results(args: dict[str, Any]) -> dict[str, Any]:
    """Store test results in the database."""
    storage = _get_storage()

    try:
        storage.save_result(
            test_path=args["test_path"],
            test_name=args["test_name"],
            passed=args["passed"],
            duration=args.get("duration", 0.0),
            cost=args.get("cost", 0.0),
            tokens_used=args.get("tokens_used", 0),
            model=args.get("model", ""),
            provider=args.get("provider", ""),
            error=args.get("error"),
            evaluations=json.dumps(args.get("evaluations", [])),
        )
        return _text_result(
            {
                "stored": True,
                "test_path": args["test_path"],
                "test_name": args["test_name"],
            }
        )
    except (KeyError, TypeError) as e:
        return _error_result(f"Invalid result data: {e}")


# ---------------------------------------------------------------------------
# Tool 8: Generate Test Suite
# ---------------------------------------------------------------------------


@tool(
    "generate_test_suite",
    "Auto-generate a YAML test suite by discovering MCP tools and creating "
    "test cases for each tool. Returns the path to the generated test files.",
    {
        "output_dir": str,
    },
)
async def generate_test_suite(args: dict[str, Any]) -> dict[str, Any]:
    """Generate test YAML files from MCP tool schemas."""
    mcp_url = _get_mcp_url()
    if not mcp_url:
        return _error_result("No MCP URL configured. Set mcp_profile or mcp_url in agent context.")

    output_dir = Path(args.get("output_dir", "tests/generated"))
    auth_config = _get_auth_config()

    try:
        from testmcpy.src.mcp_client import MCPClient

        client = MCPClient(base_url=mcp_url, auth=auth_config)
        await client.initialize()
        tools = await client.list_tools()
        await client.close()

        if not tools:
            return _error_result("No tools found on MCP service")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Import the generation helper from CLI
        from testmcpy.cli.commands.run import _generate_tool_test

        generated_files = []
        errors = []

        profile_id = _tool_context.get("mcp_profile")

        for t in tools:
            try:
                test_content = _generate_tool_test(
                    t,
                    mcp_url,
                    profile_id,
                    auth_config,
                    include_examples=True,
                    output_dir=output_dir,
                )
                safe_name = t.name.replace("/", "_").replace(":", "_")
                test_file = output_dir / f"test_{safe_name}.yaml"
                test_file.write_text(test_content)
                generated_files.append(str(test_file))
            except (ValueError, OSError) as e:
                errors.append(f"Failed to generate test for {t.name}: {e}")

        return _text_result(
            {
                "tools_discovered": len(tools),
                "tests_generated": len(generated_files),
                "output_dir": str(output_dir),
                "files": generated_files,
                "errors": errors if errors else None,
            }
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        return _error_result(f"Failed to connect to MCP service: {e}")


# ---------------------------------------------------------------------------
# Collect all tools for the orchestrator
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    load_test_suite,
    execute_test_case,
    list_mcp_tools,
    compare_model_results,
    get_historical_results,
    run_smoke_test_tool,
    store_results,
    generate_test_suite,
]
