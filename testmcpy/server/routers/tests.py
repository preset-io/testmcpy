"""Test file management and execution endpoints."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from testmcpy.config import get_config
from testmcpy.evals.base_evaluators import create_evaluator
from testmcpy.server.routers.generation_logs import save_generation_log
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


# NOTE: Generate endpoints must be defined BEFORE the catch-all /tests/{filename:path}
# routes to avoid 405 errors (path parameter matching takes precedence)


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
            prompt=analysis_prompt, tools=[], timeout=120.0
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

YAML FORMAT (follow this structure exactly):
```yaml
version: "1.0"
tests:
  - name: test_descriptive_name_here
    prompt: "Write a realistic user request here - e.g., 'Show me all charts in the system' or 'Get the data for chart ID 5'"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "{request.tool_name}"
```

CRITICAL REQUIREMENTS:
1. The "prompt" field MUST be a realistic natural language request that a user would actually type
2. DO NOT use placeholder text like "A natural language prompt" - write REAL prompts based on what this tool does
3. Each prompt should be different and test different aspects of the tool
4. Use the tool description to understand what prompts would trigger this tool
5. Examples of GOOD prompts: "List all available charts", "Get data for chart with ID 123", "Show me the sales dashboard"
6. Examples of BAD prompts: "A prompt that triggers this tool", "Test the tool", "Call the function"

IMPORTANT: Your response must be ONLY valid YAML starting with "version:" - no explanations, no summaries, no markdown.

version: "1.0"
tests:"""

        test_gen_result = await llm_provider.generate_with_tools(
            prompt=test_gen_prompt, tools=[], timeout=60.0
        )

        # Extract YAML from response
        yaml_content = test_gen_result.response

        # If response starts with tests (continuing from our prompt), prepend the header
        if yaml_content.strip().startswith("- name:") or yaml_content.strip().startswith(
            "  - name:"
        ):
            yaml_content = 'version: "1.0"\ntests:\n' + yaml_content

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


@router.post("/tests/generate/stream")
async def generate_tests_stream(request: GenerateTestsRequest):
    """Generate tests for an MCP tool using LLM with streaming logs."""
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    async def generate():
        """Generator that yields SSE events with progress logs."""
        # Track logs and LLM calls for history
        log_messages = []
        llm_calls = []
        analysis = None
        yaml_content = None
        output_file = None
        test_count = 0
        total_cost = 0.0
        error_msg = None

        def send_log(message: str, log_type: str = "log"):
            """Format a log message as SSE event."""
            log_messages.append(message)
            data = json.dumps({"type": log_type, "message": message})
            return f"data: {data}\n\n"

        def send_result(result: dict):
            """Format final result as SSE event."""
            data = json.dumps({"type": "complete", "result": result})
            return f"data: {data}\n\n"

        def send_error(error: str):
            """Format error as SSE event."""
            log_messages.append(f"ERROR: {error}")
            data = json.dumps({"type": "error", "message": error})
            return f"data: {data}\n\n"

        try:
            yield send_log(f"🚀 Starting test generation for {request.tool_name}")
            yield send_log(f"📋 Coverage level: {request.coverage_level}")
            yield send_log(f"🤖 Using {provider}/{model}")

            # Initialize LLM provider
            yield send_log("🔧 Initializing LLM provider...")
            llm_provider = create_llm_provider(provider, model)
            await llm_provider.initialize()
            yield send_log("✓ LLM provider ready")

            # Step 1: Analyze tool
            yield send_log("📊 Step 1/2: Analyzing tool schema...")
            yield send_log(f"   Tool: {request.tool_name}")
            if request.tool_description:
                desc_preview = (
                    request.tool_description[:100] + "..."
                    if len(request.tool_description) > 100
                    else request.tool_description
                )
                yield send_log(f"   Description: {desc_preview}")

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

            yield send_log("   Sending analysis prompt to LLM...")
            analysis_start = datetime.now()
            analysis_result = await llm_provider.generate_with_tools(
                prompt=analysis_prompt, tools=[], timeout=120.0
            )
            analysis_duration = (datetime.now() - analysis_start).total_seconds()
            yield send_log(f"   ✓ Analysis complete (${analysis_result.cost:.4f})")

            # Record analysis LLM call
            token_usage = getattr(analysis_result, "token_usage", None) or {}
            llm_calls.append(
                {
                    "step": "analysis",
                    "prompt": analysis_prompt,
                    "response": analysis_result.response,
                    "cost": analysis_result.cost,
                    "tokens": token_usage.get("total", 0),
                    "duration": analysis_duration,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Parse analysis
            try:
                analysis_text = analysis_result.response
                json_match = re.search(r"\{[\s\S]*\}", analysis_text)
                if json_match:
                    analysis = json.loads(json_match.group())
                    yield send_log(
                        f"   Found {len(analysis.get('test_scenarios', []))} test scenarios"
                    )
                else:
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
                    yield send_log("   Using fallback analysis structure")
            except Exception as e:
                yield send_log(f"   ⚠ Parse warning: {str(e)[:50]}")
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

            # Step 2: Generate tests
            coverage_config = {
                "basic": {"count": 2, "include_edge_cases": False, "include_errors": False},
                "mid": {"count": 5, "include_edge_cases": True, "include_errors": True},
                "comprehensive": {
                    "count": 12,
                    "include_edge_cases": True,
                    "include_errors": True,
                },
            }
            config_for_level = coverage_config.get(request.coverage_level, coverage_config["basic"])

            yield send_log(f"📝 Step 2/2: Generating {config_for_level['count']} test cases...")

            test_gen_prompt = f"""You are generating test cases for an MCP tool. Generate {config_for_level["count"]} test cases in YAML format.

Tool Name: {request.tool_name}
Description: {request.tool_description}
Schema: {json.dumps(request.tool_schema, indent=2)}

Analysis: {json.dumps(analysis, indent=2)}

{"Include edge cases and error scenarios." if config_for_level["include_edge_cases"] else "Focus on common use cases."}
{f"Custom Instructions: {request.custom_instructions}" if request.custom_instructions else ""}

YAML FORMAT (follow this structure exactly):
```yaml
version: "1.0"
tests:
  - name: test_descriptive_name_here
    prompt: "Write a realistic user request here"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "{request.tool_name}"
```

CRITICAL REQUIREMENTS:
1. The "prompt" field MUST be a realistic natural language request that a user would actually type
2. DO NOT use placeholder text - write REAL prompts based on what this tool does
3. Each prompt should be different and test different aspects of the tool

IMPORTANT: Your response must be ONLY valid YAML starting with "version:" - no explanations.

version: "1.0"
tests:"""

            yield send_log("   Sending generation prompt to LLM...")
            gen_start = datetime.now()
            test_gen_result = await llm_provider.generate_with_tools(
                prompt=test_gen_prompt, tools=[], timeout=120.0
            )
            gen_duration = (datetime.now() - gen_start).total_seconds()
            yield send_log(f"   ✓ Generation complete (${test_gen_result.cost:.4f})")

            # Record generation LLM call
            gen_token_usage = getattr(test_gen_result, "token_usage", None) or {}
            llm_calls.append(
                {
                    "step": "generation",
                    "prompt": test_gen_prompt,
                    "response": test_gen_result.response,
                    "cost": test_gen_result.cost,
                    "tokens": gen_token_usage.get("total", 0),
                    "duration": gen_duration,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Process YAML
            yield send_log("🔍 Processing generated YAML...")
            yaml_content = test_gen_result.response

            if yaml_content.strip().startswith("- name:") or yaml_content.strip().startswith(
                "  - name:"
            ):
                yaml_content = 'version: "1.0"\ntests:\n' + yaml_content

            yaml_match = re.search(r"```(?:yaml)?\s*([\s\S]*?)\s*```", yaml_content)
            if yaml_match:
                yaml_content = yaml_match.group(1).strip()
            else:
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
                parsed_yaml = yaml.safe_load(yaml_content)
                test_count = len(parsed_yaml.get("tests", []))
                yield send_log(f"   ✓ Valid YAML with {test_count} tests")
            except Exception as e:
                error_msg = f"Generated invalid YAML: {str(e)}"
                # Save log even on error
                save_generation_log(
                    {
                        "metadata": {
                            "tool_name": request.tool_name,
                            "tool_description": request.tool_description,
                            "coverage_level": request.coverage_level,
                            "provider": provider,
                            "model": model,
                            "timestamp": datetime.now().isoformat(),
                            "success": False,
                            "test_count": 0,
                            "total_cost": sum(c.get("cost", 0) for c in llm_calls),
                            "error": error_msg,
                        },
                        "tool_schema": request.tool_schema,
                        "llm_calls": llm_calls,
                        "logs": log_messages,
                        "analysis": analysis,
                        "generated_yaml": yaml_content,
                    }
                )
                yield send_error(error_msg)
                return

            # Save file
            yield send_log("💾 Saving test file...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_tool_name = "".join(
                c if c.isalnum() or c in ("_", "-") else "_" for c in request.tool_name
            )

            tests_dir = Path.cwd() / "tests"
            tool_dir = tests_dir / safe_tool_name
            tool_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{request.coverage_level}_{timestamp}.yaml"
            file_path = tool_dir / filename
            relative_path = f"{safe_tool_name}/{filename}"
            output_file = relative_path

            with open(file_path, "w") as f:
                f.write(yaml_content)

            yield send_log(f"   ✓ Saved to {relative_path}")

            await llm_provider.close()

            total_cost = test_gen_result.cost + analysis_result.cost
            yield send_log(f"✅ Complete! Total cost: ${total_cost:.4f}")

            # Save generation log
            log_id = save_generation_log(
                {
                    "metadata": {
                        "tool_name": request.tool_name,
                        "tool_description": request.tool_description,
                        "coverage_level": request.coverage_level,
                        "provider": provider,
                        "model": model,
                        "timestamp": datetime.now().isoformat(),
                        "success": True,
                        "test_count": test_count,
                        "total_cost": total_cost,
                        "output_file": output_file,
                    },
                    "tool_schema": request.tool_schema,
                    "llm_calls": llm_calls,
                    "logs": log_messages,
                    "analysis": analysis,
                    "generated_yaml": yaml_content,
                }
            )
            yield send_log(f"📋 Log saved: {log_id}")

            # Send final result
            yield send_result(
                {
                    "success": True,
                    "filename": relative_path,
                    "path": str(file_path),
                    "analysis": analysis,
                    "test_count": test_count,
                    "cost": total_cost,
                    "log_id": log_id,
                }
            )

        except Exception as e:
            error_msg = str(e)
            # Save log even on error
            try:
                save_generation_log(
                    {
                        "metadata": {
                            "tool_name": request.tool_name,
                            "tool_description": request.tool_description,
                            "coverage_level": request.coverage_level,
                            "provider": provider,
                            "model": model,
                            "timestamp": datetime.now().isoformat(),
                            "success": False,
                            "test_count": 0,
                            "total_cost": sum(c.get("cost", 0) for c in llm_calls),
                            "error": error_msg,
                        },
                        "tool_schema": request.tool_schema,
                        "llm_calls": llm_calls,
                        "logs": log_messages,
                        "analysis": analysis,
                        "generated_yaml": yaml_content,
                    }
                )
            except Exception:
                pass  # Don't fail if log saving fails
            yield send_error(error_msg)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
            verbose=True,
            hide_tool_output=False,
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
            verbose=True,
            hide_tool_output=False,
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
            verbose=True,
            hide_tool_output=False,
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
async def run_tool_tests(
    tool_name: str,
    model: str | None = None,
    provider: str | None = None,
    profile: str | None = None,
):
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
        # Get MCP client - use profile or default
        mcp_client = None
        effective_profile = profile
        if not effective_profile:
            # Try to get default profile from config
            from testmcpy.server.helpers.mcp_config import load_mcp_yaml

            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")

        if effective_profile:
            mcp_client = await get_or_create_mcp_client(effective_profile)

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

            # Run tests with MCP client
            runner = TestRunner(
                model=model,
                provider=provider,
                mcp_url=config.get_mcp_url(),
                mcp_client=mcp_client,
                verbose=True,
                hide_tool_output=False,
            )

            await runner.initialize()
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
