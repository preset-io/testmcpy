"""Test file management and execution endpoints."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from testmcpy.config import get_config
from testmcpy.evals.base_evaluators import create_evaluator
from testmcpy.server.state import get_or_create_mcp_client
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.test_runner import TestCase, TestRunner

router = APIRouter(prefix="/api", tags=["tests"])

# Get config
config = get_config()


# Pydantic models
class TestFileCreate(BaseModel):
    # Support both structured data and raw YAML content
    filename: str | None = None
    content: str | None = None
    # Structured test data fields
    name: str | None = None
    description: str | None = None
    test_cases: list[dict[str, Any]] | None = None


class TestFileUpdate(BaseModel):
    # Support both structured data and raw YAML content
    content: str | None = None
    # Structured test data fields
    name: str | None = None
    description: str | None = None
    test_cases: list[dict[str, Any]] | None = None


class TestRunRequest(BaseModel):
    test_path: str
    model: str | None = None
    provider: str | None = None
    profile: str | None = None  # MCP profile selection
    test_name: str | None = None  # Optional: run only a specific test by name
    stream: bool = False  # Enable streaming test output


class EvalRunRequest(BaseModel):
    prompt: str
    response: str
    tool_calls: list[dict[str, Any]] = []
    model: str | None = None
    provider: str | None = None


class GenerateTestsRequest(BaseModel):
    tool_name: str
    tool_description: str
    tool_schema: dict[str, Any]
    coverage_level: str  # "basic", "mid", "comprehensive"
    custom_instructions: str | None = None
    model: str | None = None
    provider: str | None = None


@router.get("/tests")
async def list_tests():
    """List all test files in the tests directory, including subdirectories."""
    tests_dir = Path.cwd() / "tests"
    if not tests_dir.exists():
        return {"folders": {}, "files": []}

    folders = {}  # folder_name -> list of files
    root_files = []  # files in root tests/ directory

    # Recursively search for YAML files
    for file in tests_dir.rglob("*.yaml"):
        try:
            with open(file) as f:
                content = f.read()
                data = yaml.safe_load(content)

                # Count tests
                test_count = len(data.get("tests", [])) if "tests" in data else 1

                # Get relative path from tests dir
                rel_path = file.relative_to(tests_dir)
                folder_name = str(rel_path.parent) if rel_path.parent != Path(".") else None

                file_info = {
                    "filename": file.name,
                    "relative_path": str(rel_path),
                    "path": str(file),
                    "test_count": test_count,
                    "size": file.stat().st_size,
                    "modified": file.stat().st_mtime,
                }

                if folder_name and folder_name != ".":
                    # File is in a subfolder
                    if folder_name not in folders:
                        folders[folder_name] = []
                    folders[folder_name].append(file_info)
                else:
                    # File is in root
                    root_files.append(file_info)

        except Exception as e:
            print(f"Error reading {file}: {e}")

    # Sort files within each folder by modified time
    for folder in folders:
        folders[folder] = sorted(folders[folder], key=lambda x: x["modified"], reverse=True)

    root_files = sorted(root_files, key=lambda x: x["modified"], reverse=True)

    return {"folders": folders, "files": root_files}


@router.get("/tests/{filename:path}")
async def get_test_file(filename: str):
    """Get content of a specific test file (supports paths like 'folder/file.yaml')."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        with open(file_path) as f:
            content = f.read()

        return {"filename": filename, "content": content, "path": str(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests")
async def create_test_file(request: TestFileCreate):
    """Create a new test file. Accepts either structured test data or raw YAML content."""
    tests_dir = Path.cwd() / "tests"
    tests_dir.mkdir(exist_ok=True)

    # Determine if this is structured data or raw content
    if request.name is not None and request.test_cases is not None:
        # Structured data: convert to YAML
        test_data = {
            "name": request.name,
            "description": request.description or "",
            "test_cases": request.test_cases,
        }
        content = yaml.dump(test_data, default_flow_style=False, sort_keys=False, indent=2)
        # Generate filename from name if not provided
        filename = request.filename or f"{request.name.lower().replace(' ', '_')}.yaml"
    elif request.content is not None and request.filename is not None:
        # Raw YAML content
        content = request.content
        filename = request.filename
    else:
        raise HTTPException(
            status_code=400,
            detail="Either provide (name, test_cases) for structured data or (filename, content) for raw YAML",
        )

    file_path = tests_dir / filename

    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")

    # Validate YAML
    try:
        yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, "w") as f:
            f.write(content)

        return {
            "message": "Test file created successfully",
            "filename": filename,
            "path": str(file_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tests/{filename:path}")
async def update_test_file(filename: str, request: TestFileUpdate):
    """Update an existing test file. Accepts either structured test data or raw YAML content."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    # Determine if this is structured data or raw content
    if request.name is not None and request.test_cases is not None:
        # Structured data: convert to YAML
        test_data = {
            "name": request.name,
            "description": request.description or "",
            "test_cases": request.test_cases,
        }
        content = yaml.dump(test_data, default_flow_style=False, sort_keys=False, indent=2)
    elif request.content is not None:
        # Raw YAML content
        content = request.content
    else:
        raise HTTPException(
            status_code=400,
            detail="Either provide (name, test_cases) for structured data or content for raw YAML",
        )

    # Validate YAML
    try:
        yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, "w") as f:
            f.write(content)

        return {
            "message": "Test file updated successfully",
            "filename": filename,
            "path": str(file_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tests/{filename:path}")
async def delete_test_file(filename: str):
    """Delete a test file (supports paths like 'folder/file.yaml')."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        file_path.unlink()
        return {"message": "Test file deleted successfully", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test execution


@router.post("/tests/run")
async def run_tests(request: TestRunRequest):
    """Run test cases from a file."""
    test_path = Path(request.test_path)

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test file not found")

    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Load test cases
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        test_cases = []
        if "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        else:
            test_cases.append(TestCase.from_dict(data))

        # Filter to specific test if test_name is provided
        if request.test_name:
            test_cases = [tc for tc in test_cases if tc.name == request.test_name]
            if not test_cases:
                raise HTTPException(
                    status_code=404,
                    detail=f"Test '{request.test_name}' not found in test file",
                )

        # Get MCP client for the selected profile
        mcp_client = None
        if request.profile:
            mcp_client = await get_or_create_mcp_client(request.profile)

        # Run tests
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.get_mcp_url(),
            mcp_client=mcp_client,
            verbose=False,
            hide_tool_output=True,
        )

        results = await runner.run_tests(test_cases)

        # Save results to storage for metrics tracking
        try:
            from testmcpy.storage import get_storage

            storage = get_storage()

            # Save test file version
            with open(test_path) as f:
                content = f.read()
            version = storage.save_version(str(test_path), content)

            # Save each result
            for r in results:
                storage.save_result(
                    test_path=str(test_path),
                    test_name=r.test_name,
                    passed=r.passed,
                    duration=r.duration,
                    cost=r.cost,
                    tokens_used=r.token_usage.get("total", 0) if r.token_usage else 0,
                    model=model,
                    provider=provider,
                    error=r.error,
                    evaluations=[
                        e.to_dict() if hasattr(e, "to_dict") else e for e in (r.evaluations or [])
                    ],
                    version_id=version.id,
                )
        except Exception as storage_err:
            # Don't fail the request if storage fails
            print(f"Warning: Failed to save results to storage: {storage_err}")

        # Format results
        return {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total_cost": sum(r.cost for r in results),
                "total_tokens": sum(
                    r.token_usage.get("total", 0) for r in results if r.token_usage
                ),
            },
            "results": [r.to_dict() for r in results],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests/{test_name}/run")
async def run_specific_test(test_name: str, request: TestRunRequest | None = None):
    """Run all test cases from a specific test file."""
    tests_dir = Path.cwd() / "tests"
    # Try with .yaml extension first
    test_path = tests_dir / f"{test_name}.yaml"
    if not test_path.exists():
        # Try without extension (if test_name already has extension)
        test_path = tests_dir / test_name

    if not test_path.exists():
        raise HTTPException(status_code=404, detail=f"Test file '{test_name}' not found")

    model = (request.model if request else None) or config.default_model
    provider = (request.provider if request else None) or config.default_provider

    try:
        # Load test cases
        with open(test_path) as f:
            data = yaml.safe_load(f)

        test_cases = []
        if "test_cases" in data:
            for test_data in data["test_cases"]:
                test_cases.append(TestCase.from_dict(test_data))
        elif "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        else:
            test_cases.append(TestCase.from_dict(data))

        # Run tests
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.get_mcp_url(),
            verbose=False,
            hide_tool_output=True,
        )

        results = await runner.run_tests(test_cases)

        # Format results
        return {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total_cost": sum(r.cost for r in results),
                "total_tokens": sum(
                    r.token_usage.get("total", 0) for r in results if r.token_usage
                ),
            },
            "results": [r.to_dict() for r in results],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests/{test_name}/cases/{case_index}/run")
async def run_specific_test_case(
    test_name: str, case_index: int, request: TestRunRequest | None = None
):
    """Run a specific test case from a test file."""
    tests_dir = Path.cwd() / "tests"
    # Try with .yaml extension first
    test_path = tests_dir / f"{test_name}.yaml"
    if not test_path.exists():
        # Try without extension (if test_name already has extension)
        test_path = tests_dir / test_name

    if not test_path.exists():
        raise HTTPException(status_code=404, detail=f"Test file '{test_name}' not found")

    model = (request.model if request else None) or config.default_model
    provider = (request.provider if request else None) or config.default_provider

    try:
        # Load test cases
        with open(test_path) as f:
            data = yaml.safe_load(f)

        if "test_cases" in data:
            test_case_data = data["test_cases"]
        elif "tests" in data:
            test_case_data = data["tests"]
        else:
            test_case_data = [data]

        if case_index < 0 or case_index >= len(test_case_data):
            raise HTTPException(
                status_code=404,
                detail=f"Test case index {case_index} not found. Valid indices: 0-{len(test_case_data) - 1}",
            )

        # Get the specific test case
        test_case = TestCase.from_dict(test_case_data[case_index])

        # Run test
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.get_mcp_url(),
            verbose=False,
            hide_tool_output=True,
        )

        results = await runner.run_tests([test_case])

        # Format result
        result = results[0] if results else None
        if not result:
            raise HTTPException(status_code=500, detail="Test execution failed")

        return {
            "passed": result.passed,
            "result": result.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests/run-tool/{tool_name}")
async def run_tool_tests(tool_name: str, model: str | None = None, provider: str | None = None):
    """Run all tests for a specific tool."""
    # Sanitize tool name for folder lookup
    safe_tool_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in tool_name)

    tests_dir = Path.cwd() / "tests" / safe_tool_name

    if not tests_dir.exists() or not tests_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"No test directory found for tool '{tool_name}' (looked for: {tests_dir})",
        )

    # Find all YAML test files in the tool directory
    test_files = list(tests_dir.glob("*.yaml"))

    if not test_files:
        raise HTTPException(
            status_code=404, detail=f"No test files found in directory: {tests_dir}"
        )

    model = model or config.default_model
    provider = provider or config.default_provider

    try:
        all_results = []
        total_summary = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
        }

        # Run each test file
        for test_file in test_files:
            with open(test_file) as f:
                data = yaml.safe_load(f)

            test_cases = []
            if "tests" in data:
                for test_data in data["tests"]:
                    test_cases.append(TestCase.from_dict(test_data))
            else:
                test_cases.append(TestCase.from_dict(data))

            # Run tests
            runner = TestRunner(
                model=model,
                provider=provider,
                mcp_url=config.get_mcp_url(),
                verbose=False,
                hide_tool_output=True,
            )

            results = await runner.run_tests(test_cases)

            # Aggregate results
            all_results.extend(results)
            total_summary["total"] += len(results)
            total_summary["passed"] += sum(1 for r in results if r.passed)
            total_summary["failed"] += sum(1 for r in results if not r.passed)
            total_summary["total_cost"] += sum(r.cost for r in results)
            total_summary["total_tokens"] += sum(
                r.token_usage.get("total", 0) for r in results if r.token_usage
            )

        return {
            "summary": total_summary,
            "results": [r.to_dict() for r in all_results],
            "files_tested": [str(f.name) for f in test_files],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Eval endpoints


@router.get("/reports")
async def get_reports():
    """Get list of test execution reports."""
    reports_dir = Path.cwd() / "reports"

    if not reports_dir.exists():
        return {"reports": []}

    try:
        reports = []
        for report_file in reports_dir.glob("*.json"):
            try:
                with open(report_file) as f:
                    report_data = json.load(f)
                    reports.append(
                        {
                            "filename": report_file.name,
                            "path": str(report_file),
                            "created": datetime.fromtimestamp(
                                report_file.stat().st_mtime
                            ).isoformat(),
                            "summary": report_data.get("summary", {}),
                            "test_name": report_data.get("test_name", ""),
                        }
                    )
            except Exception as e:
                print(f"Warning: Failed to read report {report_file}: {e}")
                continue

        # Sort by creation time, newest first
        reports.sort(key=lambda x: x["created"], reverse=True)

        return {"reports": reports}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")


@router.post("/eval/run")
async def run_eval(request: EvalRunRequest):
    """Run evaluators on a prompt/response pair from chat."""
    try:
        # Extract tool results from tool_calls (chat embeds results in tool_calls)
        from testmcpy.src.mcp_client import MCPToolResult

        print(f"[EVAL DEBUG] Received tool_calls: {request.tool_calls}")

        tool_results = []
        for tool_call in request.tool_calls:
            print(f"[EVAL DEBUG] Processing tool_call: {tool_call.get('name')}")
            print(f"[EVAL DEBUG] - has 'result' key: {'result' in tool_call}")
            print(f"[EVAL DEBUG] - result value: {tool_call.get('result')}")
            print(f"[EVAL DEBUG] - is_error: {tool_call.get('is_error', False)}")

            # Create MCPToolResult from embedded result data
            tool_results.append(
                MCPToolResult(
                    tool_call_id=tool_call.get("id", "unknown"),
                    content=tool_call.get("result"),
                    is_error=tool_call.get("is_error", False),
                    error_message=tool_call.get("error"),
                )
            )

        print(f"[EVAL DEBUG] Created {len(tool_results)} tool_results")

        # Create a context for evaluators
        context = {
            "prompt": request.prompt,
            "response": request.response,
            "tool_calls": request.tool_calls,
            "tool_results": tool_results,
            "metadata": {
                "model": request.model or config.default_model,
                "provider": request.provider or config.default_provider,
            },
        }

        # Build evaluators based on actual tool calls
        default_evaluators = [
            {"name": "execution_successful"},
        ]

        # If tool calls were made, add specific tool validation
        if request.tool_calls and len(request.tool_calls) > 0:
            first_tool = request.tool_calls[0]

            # Check specific tool was called
            default_evaluators.append(
                {"name": "was_mcp_tool_called", "args": {"tool_name": first_tool.get("name")}}
            )

            # Check tool call count
            default_evaluators.append(
                {"name": "tool_call_count", "args": {"expected_count": len(request.tool_calls)}}
            )

            # Validate parameters if present
            if first_tool.get("arguments") and len(first_tool.get("arguments")) > 0:
                default_evaluators.append(
                    {
                        "name": "tool_called_with_parameters",
                        "args": {
                            "tool_name": first_tool.get("name"),
                            "parameters": first_tool.get("arguments"),
                            "partial_match": True,
                        },
                    }
                )
        else:
            # No tools called - just check if any tool was called
            default_evaluators.append({"name": "was_mcp_tool_called"})

        # Run evaluators
        evaluations = []
        all_passed = True
        total_score = 0.0

        for eval_config in default_evaluators:
            try:
                evaluator = create_evaluator(eval_config["name"], **eval_config.get("args", {}))
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

                if not eval_result.passed:
                    all_passed = False
                total_score += eval_result.score
            except Exception as e:
                # If evaluator fails, mark it as failed but continue
                evaluations.append(
                    {
                        "evaluator": eval_config["name"],
                        "passed": False,
                        "score": 0.0,
                        "reason": f"Evaluator error: {str(e)}",
                        "details": None,
                    }
                )
                all_passed = False

        avg_score = total_score / len(default_evaluators) if default_evaluators else 0.0

        return {
            "passed": all_passed,
            "score": avg_score,
            "reason": "All evaluators passed" if all_passed else "Some evaluators failed",
            "evaluations": evaluations,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test generation endpoint


@router.post("/tests/generate")
async def generate_tests(request: GenerateTestsRequest):
    """Generate tests for an MCP tool using LLM."""
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Initialize LLM provider
        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        # Step 1: Analyze tool and suggest strategies
        analysis_prompt = f"""You are a test engineer analyzing an MCP tool to suggest test strategies.

Tool Name: {request.tool_name}
Description: {request.tool_description}
Schema: {json.dumps(request.tool_schema, indent=2)}

Analyze this tool and suggest:
1. What are the key scenarios to test? (e.g., valid inputs, edge cases, error conditions)
2. What parameters should be varied in tests?
3. What are potential failure modes?
4. What outputs should be validated?

Respond with a structured analysis in JSON format:
{{
  "test_scenarios": [
    {{"name": "scenario name", "description": "what to test", "priority": "high|medium|low"}}
  ],
  "key_parameters": ["param1", "param2"],
  "edge_cases": ["edge case 1", "edge case 2"],
  "validation_points": ["what to check in output"]
}}"""

        analysis_result = await llm_provider.generate_with_tools(
            prompt=analysis_prompt, tools=[], timeout=30.0
        )

        # Parse the analysis
        try:
            # Extract JSON from response
            analysis_text = analysis_result.response
            # Try to find JSON in the response
            json_match = re.search(r"\{[\s\S]*\}", analysis_text)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # Fallback to basic structure
                analysis = {
                    "test_scenarios": [
                        {
                            "name": "Basic functionality",
                            "description": "Test basic tool execution",
                            "priority": "high",
                        }
                    ],
                    "key_parameters": [],
                    "edge_cases": [],
                    "validation_points": ["Tool executes successfully"],
                }
        except Exception as e:
            print(f"Failed to parse analysis: {e}")
            analysis = {
                "test_scenarios": [
                    {
                        "name": "Basic functionality",
                        "description": "Test basic tool execution",
                        "priority": "high",
                    }
                ],
                "key_parameters": [],
                "edge_cases": [],
                "validation_points": ["Tool executes successfully"],
            }

        # Step 2: Generate tests based on coverage level
        coverage_config = {
            "basic": {"count": 2, "include_edge_cases": False, "include_errors": False},
            "mid": {"count": 5, "include_edge_cases": True, "include_errors": True},
            "comprehensive": {"count": 12, "include_edge_cases": True, "include_errors": True},
        }

        config_for_level = coverage_config.get(request.coverage_level, coverage_config["basic"])

        # Build the test generation prompt
        test_gen_prompt = f"""You are generating test cases for an MCP tool. Generate {config_for_level["count"]} test cases in YAML format.

Tool Name: {request.tool_name}
Description: {request.tool_description}
Schema: {json.dumps(request.tool_schema, indent=2)}

Analysis: {json.dumps(analysis, indent=2)}

{"Include edge cases and error scenarios." if config_for_level["include_edge_cases"] else "Focus on common use cases."}
{f"Custom Instructions: {request.custom_instructions}" if request.custom_instructions else ""}

Generate tests in this YAML format:
```yaml
version: "1.0"
tests:
  - name: test_basic_usage
    prompt: "A natural language prompt that would trigger this tool"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "{request.tool_name}"
      - name: tool_called_with_parameters
        args:
          tool_name: "{request.tool_name}"
          parameters:
            param1: "expected_value"
          partial_match: true
```

Important:
1. Each test should have a descriptive name (e.g., test_search_by_id, test_invalid_input)
2. The prompt should be natural language that would make the LLM call this tool
3. Include appropriate evaluators for each test
4. For parameter validation, only include the most important parameters
5. Make prompts realistic and varied

Generate {config_for_level["count"]} tests now in YAML format:"""

        test_gen_result = await llm_provider.generate_with_tools(
            prompt=test_gen_prompt, tools=[], timeout=60.0
        )

        # Extract YAML from response
        yaml_content = test_gen_result.response

        # Try to extract YAML from code blocks (handles various formats)
        yaml_match = re.search(r"```(?:yaml)?\s*([\s\S]*?)\s*```", yaml_content)
        if yaml_match:
            yaml_content = yaml_match.group(1).strip()
        else:
            # Fallback: strip leading/trailing markdown fences manually
            yaml_content = yaml_content.strip()
            if yaml_content.startswith("```yaml"):
                yaml_content = yaml_content[7:]
            elif yaml_content.startswith("```"):
                yaml_content = yaml_content[3:]
            if yaml_content.endswith("```"):
                yaml_content = yaml_content[:-3]
            yaml_content = yaml_content.strip()

        # Validate YAML
        try:
            yaml.safe_load(yaml_content)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Generated invalid YAML: {str(e)}\n\nGenerated content:\n{yaml_content}",
            )

        # Generate filename and folder structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize tool name for folder name (remove special chars)
        safe_tool_name = "".join(
            c if c.isalnum() or c in ("_", "-") else "_" for c in request.tool_name
        )

        # Create folder structure: tests/<tool_name>/
        tests_dir = Path.cwd() / "tests"
        tool_dir = tests_dir / safe_tool_name
        tool_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{request.coverage_level}_{timestamp}.yaml"
        file_path = tool_dir / filename
        relative_path = f"{safe_tool_name}/{filename}"

        with open(file_path, "w") as f:
            f.write(yaml_content)

        await llm_provider.close()

        return {
            "success": True,
            "filename": relative_path,
            "path": str(file_path),
            "analysis": analysis,
            "test_count": len(yaml.safe_load(yaml_content).get("tests", [])),
            "cost": test_gen_result.cost + analysis_result.cost,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
