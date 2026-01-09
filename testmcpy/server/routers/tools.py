"""Tool management and debugging endpoints."""

import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from testmcpy.config import get_config
from testmcpy.mcp_profiles import load_profile
from testmcpy.server.state import get_default_mcp_client, get_mcp_clients
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPClient

router = APIRouter(prefix="/api", tags=["tools"])

# Get config
config = get_config()


# Pydantic models
class FormatSchemaRequest(BaseModel):
    tool_schema: dict[str, Any] = Field(..., alias="schema")
    tool_name: str
    format: str  # e.g., "python_client", "javascript_client", "typescript_client"
    mcp_url: str | None = None  # For curl format with actual values
    auth_token: str | None = None  # For curl format with actual values
    profile: str | None = None  # MCP profile to get auth from (e.g., "sandbox:My Workspace")

    model_config = {"populate_by_name": True}


class OptimizeDocsRequest(BaseModel):
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    model: str | None = None
    provider: str | None = None


class OptimizeDocsResponse(BaseModel):
    analysis: dict[str, Any]
    suggestions: dict[str, Any]
    original: dict[str, Any]
    cost: float
    duration: float


class ToolCompareRequest(BaseModel):
    tool_name: str
    profile1: str  # Format: "profile_id:mcp_name"
    profile2: str  # Format: "profile_id:mcp_name"
    parameters: dict[str, Any] = {}
    iterations: int = 3


class ToolDebugRequest(BaseModel):
    parameters: dict[str, Any]
    profile: str | None = None


class ToolDebugResponse(BaseModel):
    success: bool
    response: dict[str, Any] | list[Any] | str | None
    steps: list[dict[str, Any]]
    total_time: float
    error: str | None = None


class SmokeTestRequest(BaseModel):
    """Request to run smoke tests."""

    profile_id: str | None = None
    mcp_url: str | None = None
    test_all_tools: bool = True
    max_tools_to_test: int = 10


@router.post("/format")
async def format_schema(request: FormatSchemaRequest):
    """Convert a JSON schema to various formats including client code examples."""
    try:
        from testmcpy.formatters import FORMATS

        format_config = FORMATS.get(request.format)
        if not format_config:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {request.format}. Available formats: {list(FORMATS.keys())}",
            )

        converter = format_config["convert"]
        mcp_clients = get_mcp_clients()

        # For curl and client formats, pass mcp_url and auth_token
        client_formats = ["curl", "python_client", "javascript_client", "typescript_client"]
        if request.format in client_formats:
            mcp_url = request.mcp_url
            auth_token = request.auth_token

            # If profile is provided, get the auth token from the cached MCP client
            if request.profile and not auth_token:
                # Profile format is "profileId:mcpName"
                if ":" in request.profile:
                    profile_id, mcp_name = request.profile.split(":", 1)
                    # Get the cached client
                    cache_key = request.profile
                    if cache_key in mcp_clients:
                        client = mcp_clients[cache_key]
                        # Get auth token from the client's BearerAuth
                        if client.auth and hasattr(client.auth, "token"):
                            auth_token = client.auth.token
                        # Also get MCP URL from client if not provided
                        if not mcp_url and client.base_url:
                            mcp_url = client.base_url

            # Fall back to config if no profile provided
            if not mcp_url:
                mcp_url = config.get_mcp_url()

            formatted = converter(
                request.tool_schema, request.tool_name, mcp_url=mcp_url, auth_token=auth_token
            )
        else:
            formatted = converter(request.tool_schema, request.tool_name)

        return {
            "success": True,
            "format": request.format,
            "code": formatted,
            "language": format_config["language"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/optimize-docs", response_model=OptimizeDocsResponse)
async def optimize_tool_docs(request: OptimizeDocsRequest) -> OptimizeDocsResponse:
    """
    Analyze tool documentation and suggest improvements.

    Uses an LLM to evaluate tool documentation against best practices
    for LLM tool calling and provides actionable suggestions.
    """
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    if not model or not provider:
        raise HTTPException(
            status_code=400,
            detail="Model and provider must be configured. Set DEFAULT_MODEL and DEFAULT_PROVIDER in config.",
        )

    try:
        # Initialize LLM provider (use Haiku for cost efficiency)
        llm_model = model
        if provider == "anthropic" and "haiku" not in model.lower():
            # Use Haiku for analysis to save costs
            llm_model = "claude-haiku-4-5"

        llm_provider = create_llm_provider(provider, llm_model)
        await llm_provider.initialize()

        # Format the input schema for better readability
        schema_str = json.dumps(request.input_schema, indent=2)

        # Build the analysis prompt with structured output
        analysis_prompt = f"""You are an expert at writing tool documentation for LLMs (Large Language Models) that use function/tool calling.

Your task: Analyze this MCP (Model Context Protocol) tool and suggest improvements to help LLMs call it correctly.

TOOL INFORMATION:
==================
Tool Name: {request.tool_name}

Current Description:
{request.description}

Input Schema:
{schema_str}

ANALYSIS FRAMEWORK:
===================
Evaluate the documentation against these criteria:

1. CLARITY (0-100): Is it immediately obvious what this tool does?
   - Does the first sentence clearly state the tool's purpose?
   - Would an LLM understand the exact action this tool performs?
   - Are technical terms explained or self-evident?

2. COMPLETENESS (0-100): Are all parameters well-documented?
   - Is each parameter's purpose clear from the schema?
   - Are types, constraints, and valid values specified?
   - Are required vs optional parameters obvious?

3. ACTIONABILITY (0-100): Would an LLM know when to use this?
   - Is it clear what scenarios this tool is appropriate for?
   - Are there indicators of when NOT to use this tool?
   - Are related/alternative tools mentioned?

4. EXAMPLES (0-100): Are there concrete usage examples?
   - Are there example parameter values?
   - Are there example use cases or scenarios?
   - Would an LLM be able to construct a valid call from the docs?

5. CONSTRAINTS (0-100): Are limitations clearly stated?
   - Are there any prerequisites mentioned?
   - Are error conditions described?
   - Are rate limits, size limits, or other constraints noted?

COMMON ISSUES TO DETECT:
========================
- Vague verbs: "manages", "handles", "processes" → be specific: "creates", "updates", "deletes"
- Missing context: no explanation of when to use vs alternatives
- Parameter confusion: unclear names without descriptions
- Type ambiguity: parameters without clear type/format info
- No examples: abstract descriptions without concrete usage
- Jargon overload: technical terms without explanation
- Ambiguous language: multiple possible interpretations
- Hidden constraints: undocumented limitations or requirements

YOUR TASK:
==========
You MUST call the 'submit_analysis' tool with ALL required fields. Do not omit any fields.

REQUIRED FIELDS (all must be provided):

1. clarity_score (number): Overall quality score 0-100

2. issues (array): List of specific problems - MUST include at least 2-3 issues even if docs seem good
   Each issue MUST have: category, severity, issue, current, suggestion
   Example issues to always look for:
   - Missing concrete parameter examples
   - Unclear when to use this vs alternatives
   - Technical jargon without explanation
   - Missing error conditions or constraints
   - Vague verbs like "manages", "handles", "processes"

3. improved_description (string): Complete 3-5 sentence rewrite that includes:
   - Clear statement of what tool does (1 sentence, use specific verbs not "manages/handles")
   - When to use it and key scenarios (1-2 sentences)
   - Brief parameter overview mentioning key parameters by name (1 sentence)
   - Key constraints or limitations (1 sentence)

4. improvements (array): At least 2-3 specific before/after examples
   Each improvement MUST have: issue, before, after, explanation

CRITICAL INSTRUCTIONS:
- You MUST provide ALL four fields with complete data
- Do NOT provide only clarity_score - this will fail validation
- Even if documentation seems good, find at least 2-3 ways to improve it for LLM consumption
- Be critical and thorough - no documentation is perfect

Call the submit_analysis tool NOW with complete data."""

        # Generate analysis - use a mock "tool" to get structured JSON output
        # This works better than asking for raw JSON in many LLMs
        analysis_tool = {
            "name": "submit_analysis",
            "description": "Submit the documentation analysis results",
            "input_schema": {
                "type": "object",
                "properties": {
                    "clarity_score": {
                        "type": "number",
                        "description": "Overall documentation quality score from 0-100",
                    },
                    "issues": {
                        "type": "array",
                        "description": "List of issues found in the documentation",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "clarity",
                                        "completeness",
                                        "actionability",
                                        "examples",
                                        "constraints",
                                    ],
                                    "description": "Issue category",
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Issue severity",
                                },
                                "issue": {
                                    "type": "string",
                                    "description": "Description of the issue",
                                },
                                "current": {
                                    "type": "string",
                                    "description": "The problematic text from current docs",
                                },
                                "suggestion": {
                                    "type": "string",
                                    "description": "How to fix this issue",
                                },
                            },
                            "required": ["category", "severity", "issue", "suggestion"],
                        },
                    },
                    "improved_description": {
                        "type": "string",
                        "description": "Complete rewritten description that addresses all issues",
                    },
                    "improvements": {
                        "type": "array",
                        "description": "Specific before/after improvements",
                        "items": {
                            "type": "object",
                            "properties": {
                                "issue": {"type": "string", "description": "Brief issue name"},
                                "before": {
                                    "type": "string",
                                    "description": "Current problematic text",
                                },
                                "after": {
                                    "type": "string",
                                    "description": "Improved replacement text",
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "Why this improvement helps LLMs",
                                },
                            },
                            "required": ["issue", "before", "after", "explanation"],
                        },
                    },
                },
                "required": ["clarity_score", "issues", "improved_description", "improvements"],
            },
        }

        result = await llm_provider.generate_with_tools(
            prompt=analysis_prompt, tools=[analysis_tool], timeout=60.0
        )

        # Parse the response - check if LLM used the tool
        try:
            analysis_data = None

            # Debug logging
            print("\n=== LLM Response Debug ===")
            print(f"Tool calls count: {len(result.tool_calls) if result.tool_calls else 0}")
            print(f"Response text length: {len(result.response)}")
            print(f"Response preview: {result.response[:200]}")

            # First, check if the LLM made a tool call
            if result.tool_calls and len(result.tool_calls) > 0:
                # LLM used the submit_analysis tool - perfect!
                print(f"Tool calls: {result.tool_calls}")
                tool_call = result.tool_calls[0]
                print(f"Tool call name: {tool_call.get('name')}")
                print(f"Tool call keys: {list(tool_call.keys())}")

                if tool_call.get("name") == "submit_analysis":
                    # Anthropic uses "arguments" key, some providers use "input"
                    analysis_data = tool_call.get("arguments") or tool_call.get("input", {})
                    print("✓ LLM used tool call for structured output")
                    print(f"  Arguments keys: {list(analysis_data.keys())}")
                    print(f"  Score: {analysis_data.get('clarity_score')}")
                    print(f"  Issues found: {len(analysis_data.get('issues', []))}")

                    # Validate that LLM provided all required fields
                    missing_fields = []
                    if not analysis_data.get("clarity_score"):
                        missing_fields.append("clarity_score")
                    if not analysis_data.get("issues") or len(analysis_data.get("issues", [])) == 0:
                        missing_fields.append("issues (must have at least 1 issue)")
                    if not analysis_data.get("improved_description"):
                        missing_fields.append("improved_description")
                    if (
                        not analysis_data.get("improvements")
                        or len(analysis_data.get("improvements", [])) == 0
                    ):
                        missing_fields.append("improvements (must have at least 1 improvement)")

                    if missing_fields:
                        error_msg = f"LLM provided incomplete data. Missing required fields: {', '.join(missing_fields)}"
                        print(f"✗ {error_msg}")
                        raise ValueError(error_msg)
                else:
                    print(f"✗ Unexpected tool call: {tool_call.get('name')}")

            # If no tool call, try to parse JSON from response text
            if not analysis_data:
                print("No tool call found, attempting to parse JSON from response text")
                response_text = result.response.strip()

                # Remove any markdown code blocks
                response_text = re.sub(r"```(?:json)?\s*", "", response_text)
                response_text = re.sub(r"```\s*$", "", response_text)

                # Try to find JSON object (handle nested braces properly)
                start_idx = response_text.find("{")
                if start_idx == -1:
                    raise ValueError("No JSON object found in response")

                # Count braces to find matching closing brace
                brace_count = 0
                end_idx = -1
                for i in range(start_idx, len(response_text)):
                    if response_text[i] == "{":
                        brace_count += 1
                    elif response_text[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

                if end_idx == -1:
                    raise ValueError("Unmatched braces in JSON response")

                json_str = response_text[start_idx:end_idx]
                analysis_data = json.loads(json_str)

            # Validate and fix required fields
            if "clarity_score" not in analysis_data or not isinstance(
                analysis_data["clarity_score"], (int, float)
            ):
                print("Warning: Missing or invalid clarity_score, using default 50")
                analysis_data["clarity_score"] = 50
            if "issues" not in analysis_data or not isinstance(analysis_data["issues"], list):
                print("Warning: Missing or invalid issues array")
                analysis_data["issues"] = []
            if (
                "improved_description" not in analysis_data
                or not analysis_data["improved_description"]
            ):
                print("Warning: Missing improved_description, using original")
                analysis_data["improved_description"] = request.description
            if "improvements" not in analysis_data or not isinstance(
                analysis_data["improvements"], list
            ):
                print("Warning: Missing improvements array")
                analysis_data["improvements"] = []

            # Ensure each issue has required fields
            for issue in analysis_data["issues"]:
                if "category" not in issue:
                    issue["category"] = "clarity"
                if "severity" not in issue:
                    issue["severity"] = "medium"
                if "issue" not in issue:
                    issue["issue"] = "Documentation issue"
                if "current" not in issue:
                    issue["current"] = ""
                if "suggestion" not in issue:
                    issue["suggestion"] = ""

        except Exception as e:
            # Fallback to basic response if parsing fails
            print(f"✗ Failed to parse LLM response: {e}")
            print(f"Response text (first 500 chars): {result.response[:500]}")
            print(f"Tool calls: {result.tool_calls}")
            analysis_data = {
                "clarity_score": 50,
                "issues": [
                    {
                        "category": "clarity",
                        "severity": "high",
                        "issue": "LLM response parsing failed - check server logs for details",
                        "current": request.description,
                        "suggestion": f"Error: {str(e)}",
                    }
                ],
                "improved_description": request.description,
                "improvements": [],
            }

        await llm_provider.close()

        # Build response
        return OptimizeDocsResponse(
            analysis={
                "score": analysis_data.get("clarity_score", 50),
                "clarity": "good"
                if analysis_data.get("clarity_score", 50) >= 75
                else ("fair" if analysis_data.get("clarity_score", 50) >= 50 else "poor"),
                "issues": analysis_data.get("issues", []),
            },
            suggestions={
                "improved_description": analysis_data.get(
                    "improved_description", request.description
                ),
                "improvements": analysis_data.get("improvements", []),
            },
            original={
                "tool_name": request.tool_name,
                "description": request.description,
                "input_schema": request.input_schema,
            },
            cost=result.cost,
            duration=result.duration,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to optimize documentation: {str(e)}")


@router.post("/tools/compare")
async def compare_tools(request: ToolCompareRequest):
    """
    Compare the same tool across two different MCP profiles/servers.

    This endpoint runs the specified tool multiple times on two different
    MCP servers and returns performance metrics and results for comparison.
    """
    # Parse profile IDs
    profile1_parts = request.profile1.split(":", 1)
    profile2_parts = request.profile2.split(":", 1)

    if len(profile1_parts) != 2 or len(profile2_parts) != 2:
        raise HTTPException(status_code=400, detail="Profile format must be 'profile_id:mcp_name'")

    profile1_id, mcp1_name = profile1_parts
    profile2_id, mcp2_name = profile2_parts

    # Load profiles
    try:
        profile1_data = load_profile(profile1_id)
        profile2_data = load_profile(profile2_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Profile not found: {str(e)}")

    if not profile1_data or not profile2_data:
        raise HTTPException(status_code=404, detail="One or both profiles not found")

    # Find MCP configs
    mcp1 = next((m for m in profile1_data.mcps if m.name == mcp1_name), None)
    mcp2 = next((m for m in profile2_data.mcps if m.name == mcp2_name), None)

    if not mcp1 or not mcp2:
        raise HTTPException(status_code=404, detail="MCP server not found in profile")

    # Helper function to run a single iteration
    async def run_iteration(mcp_config, iteration_num):
        result = {
            "iteration": iteration_num,
            "success": False,
            "result": None,
            "error": None,
            "duration_ms": 0,
        }

        client = None
        try:
            start_time = time.time()

            # Initialize client
            client = MCPClient(mcp_url=mcp_config.get_mcp_url(), auth=mcp_config.auth)
            await client.initialize()

            # Call the tool
            tool_result = await client.call_tool(
                name=request.tool_name, arguments=request.parameters
            )

            result["success"] = True
            result["result"] = tool_result
            result["duration_ms"] = (time.time() - start_time) * 1000

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["duration_ms"] = (time.time() - start_time) * 1000
        finally:
            if client:
                try:
                    await client.cleanup()
                except Exception:
                    pass

        return result

    # Run iterations for both profiles
    results1 = []
    results2 = []

    try:
        for i in range(request.iterations):
            # Run on profile 1
            result1 = await run_iteration(mcp1, i + 1)
            results1.append(result1)

            # Run on profile 2
            result2 = await run_iteration(mcp2, i + 1)
            results2.append(result2)

        # Calculate metrics
        avg_time1 = sum(r["duration_ms"] for r in results1) / len(results1)
        avg_time2 = sum(r["duration_ms"] for r in results2) / len(results2)
        success_rate1 = (sum(1 for r in results1 if r["success"]) / len(results1)) * 100
        success_rate2 = (sum(1 for r in results2 if r["success"]) / len(results2)) * 100

        return {
            "tool_name": request.tool_name,
            "profile1": f"{profile1_data.name} ({mcp1_name})",
            "profile2": f"{profile2_data.name} ({mcp2_name})",
            "parameters": request.parameters,
            "iterations": request.iterations,
            "results1": results1,
            "results2": results2,
            "metrics": {
                "avg_time1_ms": avg_time1,
                "avg_time2_ms": avg_time2,
                "success_rate1_pct": success_rate1,
                "success_rate2_pct": success_rate2,
                "faster_profile": 1 if avg_time1 < avg_time2 else 2,
                "time_difference_ms": abs(avg_time1 - avg_time2),
                "time_difference_pct": (abs(avg_time1 - avg_time2) / max(avg_time1, avg_time2))
                * 100,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/tools/{tool_name}/debug", response_model=ToolDebugResponse)
async def debug_tool(tool_name: str, request: ToolDebugRequest):
    """
    Debug a tool by calling it with parameters and returning detailed trace.

    This endpoint calls the specified tool with the provided parameters
    and returns the response along with execution timing information.
    """
    start_time = time.time()
    steps = []
    mcp_clients = get_mcp_clients()

    try:
        # Step 1: Prepare request
        steps.append(
            {
                "step": "Request Prepared",
                "timestamp": (time.time() - start_time) * 1000,
                "data": {
                    "tool_name": tool_name,
                    "parameters": request.parameters,
                    "profile": request.profile,
                },
            }
        )

        # Get MCP client for the specified profile
        client_key = request.profile or "default"
        client = mcp_clients.get(client_key)

        if not client:
            # Try to initialize client from profile
            if request.profile:
                try:
                    profile_data = load_profile(request.profile)
                    if profile_data and profile_data.mcps:
                        mcp_config = profile_data.mcps[0]
                        client = MCPClient(mcp_url=mcp_config.get_mcp_url(), auth=mcp_config.auth)
                        await client.initialize()
                        mcp_clients[client_key] = client
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to load profile '{request.profile}': {str(e)}",
                    )

        if not client:
            # Fall back to global default client
            mcp_client = get_default_mcp_client()
            if not mcp_client:
                raise HTTPException(
                    status_code=400,
                    detail="No MCP client configured. Please select a profile or configure a default MCP server.",
                )
            client = mcp_client

        # Step 2: Call tool
        try:
            response = await client.call_tool(tool_name, request.parameters)

            steps.append(
                {
                    "step": "MCP Processing Complete",
                    "timestamp": (time.time() - start_time) * 1000,
                    "data": {
                        "success": True,
                    },
                }
            )

            # Step 3: Response received
            steps.append(
                {
                    "step": "Response Received",
                    "timestamp": (time.time() - start_time) * 1000,
                    "data": {
                        "response_type": type(response).__name__,
                    },
                }
            )

            total_time = (time.time() - start_time) * 1000

            return ToolDebugResponse(
                success=True,
                response=response,
                steps=steps,
                total_time=total_time,
            )

        except Exception as tool_error:
            steps.append(
                {
                    "step": "Tool Call Failed",
                    "timestamp": (time.time() - start_time) * 1000,
                    "data": {
                        "error": str(tool_error),
                    },
                }
            )

            total_time = (time.time() - start_time) * 1000

            return ToolDebugResponse(
                success=False,
                response=None,
                steps=steps,
                total_time=total_time,
                error=str(tool_error),
            )

    except HTTPException:
        raise
    except Exception as e:
        total_time = (time.time() - start_time) * 1000

        return ToolDebugResponse(
            success=False,
            response=None,
            steps=steps,
            total_time=total_time,
            error=str(e),
        )


@router.post("/smoke-test")
async def run_smoke_test_endpoint(request: SmokeTestRequest):
    """Run smoke tests on an MCP server."""
    from testmcpy.server.routers.smoke_reports import save_smoke_report
    from testmcpy.smoke_test import run_smoke_test

    # Determine MCP URL and auth config
    profile_name = None
    if request.profile_id:
        profile = load_profile(request.profile_id)
        if not profile or not profile.mcps:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{request.profile_id}' not found or has no MCP servers",
            )

        mcp_server = profile.mcps[0]
        mcp_url = mcp_server.mcp_url
        auth_config = mcp_server.auth.to_dict() if mcp_server.auth else None
        profile_name = profile.name
    elif request.mcp_url:
        mcp_url = request.mcp_url
        auth_config = None
    else:
        raise HTTPException(status_code=400, detail="Either profile_id or mcp_url must be provided")

    # Run smoke tests
    report = await run_smoke_test(
        mcp_url=mcp_url,
        auth_config=auth_config,
        test_all_tools=request.test_all_tools,
        max_tools_to_test=request.max_tools_to_test,
    )

    # Convert to dict and add profile info
    report_dict = report.to_dict()
    report_dict["profile_id"] = request.profile_id
    report_dict["profile_name"] = profile_name

    # Save the report
    try:
        report_id = save_smoke_report(report_dict)
        report_dict["report_id"] = report_id
    except Exception as e:
        # Don't fail if saving fails, just log it
        print(f"Warning: Failed to save smoke test report: {e}")

    return report_dict
