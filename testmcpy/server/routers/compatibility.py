"""Compatibility matrix — test tools across multiple MCP servers."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from testmcpy.mcp_profiles import load_profile
from testmcpy.server.state import get_mcp_clients
from testmcpy.src.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["compatibility"])


class CompatibilityMatrixRequest(BaseModel):
    """Request to run a compatibility matrix test."""

    profiles: list[str]  # List of "profile_id:mcp_name" references
    tool_names: list[str]  # List of tool names to test


class ToolTestResult(BaseModel):
    """Result of testing a single tool on a single server."""

    status: str  # "pass", "fail", "missing", "error"
    has_tool: bool = False
    schema_match: bool | None = None
    call_success: bool | None = None
    error: str | None = None
    duration_ms: float = 0


@router.post("/compatibility/matrix")
async def compatibility_matrix(request: CompatibilityMatrixRequest):
    """Test tools across multiple MCP servers and compare results.

    For each (profile, tool) pair:
    1. Check if the tool exists on that server
    2. Compare the tool's schema across servers
    3. Attempt a minimal call (no-op / schema check only)

    Returns a matrix of results: servers as columns, tools as rows.
    """
    if len(request.profiles) < 2:
        raise HTTPException(status_code=400, detail="At least 2 profiles are required")
    if not request.tool_names:
        raise HTTPException(status_code=400, detail="At least 1 tool name is required")

    mcp_clients = get_mcp_clients()

    # Collect tool schemas from all profiles
    profile_tools: dict[str, dict[str, dict[str, Any]]] = {}  # profile -> {tool_name -> schema}
    profile_labels: dict[str, str] = {}  # profile -> display label

    for profile_ref in request.profiles:
        if ":" not in profile_ref:
            raise HTTPException(
                status_code=400,
                detail=f"Profile '{profile_ref}' must be in 'profile_id:mcp_name' format",
            )

        profile_id, mcp_name = profile_ref.split(":", 1)
        profile_labels[profile_ref] = f"{profile_id}/{mcp_name}"

        # Try cached client first
        client = mcp_clients.get(profile_ref)
        needs_close = False

        if not client:
            profile = load_profile(profile_id)
            if not profile:
                profile_tools[profile_ref] = {}
                continue

            mcp_config = next((m for m in profile.mcps if m.name == mcp_name), None)
            if not mcp_config:
                profile_tools[profile_ref] = {}
                continue

            client = MCPClient(base_url=mcp_config.mcp_url, auth=mcp_config.auth.to_dict())
            try:
                await client.initialize()
                needs_close = True
            except (MCPConnectionError, MCPTimeoutError, MCPError) as e:
                logger.warning("Failed to initialize client for %s: %s", profile_ref, e)
                profile_tools[profile_ref] = {"_error": str(e)}
                continue

        try:
            tools = await client.list_tools()
            tool_map = {}
            for t in tools:
                tool_map[t.name] = {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
            profile_tools[profile_ref] = tool_map
        except (MCPConnectionError, MCPTimeoutError, MCPError) as e:
            logger.warning("Failed to list tools for %s: %s", profile_ref, e)
            profile_tools[profile_ref] = {"_error": str(e)}
        finally:
            if needs_close:
                await client.close()

    # Build the matrix
    matrix: dict[str, dict[str, dict[str, Any]]] = {}  # tool_name -> {profile -> result}

    # Use the first profile as the reference for schema comparison
    reference_profile = request.profiles[0]
    reference_tools = profile_tools.get(reference_profile, {})

    for tool_name in request.tool_names:
        matrix[tool_name] = {}

        for profile_ref in request.profiles:
            server_tools = profile_tools.get(profile_ref, {})

            # Check for connection error
            if "_error" in server_tools:
                matrix[tool_name][profile_ref] = {
                    "status": "error",
                    "has_tool": False,
                    "error": server_tools["_error"],
                }
                continue

            # Check if tool exists
            if tool_name not in server_tools:
                matrix[tool_name][profile_ref] = {
                    "status": "missing",
                    "has_tool": False,
                }
                continue

            tool_schema = server_tools[tool_name]
            ref_schema = reference_tools.get(tool_name)

            # Compare schemas
            schema_match = True
            if ref_schema and profile_ref != reference_profile:
                # Compare input schemas
                old_props = (ref_schema.get("inputSchema") or {}).get("properties", {})
                new_props = (tool_schema.get("inputSchema") or {}).get("properties", {})
                if set(old_props.keys()) != set(new_props.keys()):
                    schema_match = False
                else:
                    for param_name in old_props:
                        if old_props[param_name].get("type") != new_props.get(param_name, {}).get(
                            "type"
                        ):
                            schema_match = False
                            break

            matrix[tool_name][profile_ref] = {
                "status": "pass" if schema_match else "fail",
                "has_tool": True,
                "schema_match": schema_match,
            }

    return {
        "profiles": request.profiles,
        "profile_labels": profile_labels,
        "tool_names": request.tool_names,
        "matrix": matrix,
        "reference_profile": reference_profile,
    }
