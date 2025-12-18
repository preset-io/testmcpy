"""Authentication debugging and flow recording endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from testmcpy.auth_debugger import (
    AuthDebugger,
    debug_bearer_token,
    debug_jwt_flow,
    debug_oauth_flow,
)
from testmcpy.auth_flow_recorder import AuthFlowRecorder

router = APIRouter(prefix="/api", tags=["auth"])

# Global auth flow recorder instance
auth_flow_recorder = AuthFlowRecorder()


# Pydantic models
class DebugAuthRequest(BaseModel):
    auth_type: str  # "oauth", "jwt", "bearer"
    mcp_url: str | None = None  # MCP endpoint to test token against
    # OAuth fields
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    oauth_auto_discover: bool = False  # Use RFC 8414 auto-discovery for OAuth
    # JWT fields
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    insecure: bool = False  # Skip SSL verification
    # Bearer fields
    token: str | None = None


class DebugAuthResponse(BaseModel):
    success: bool
    auth_type: str
    steps: list[dict[str, Any]]
    total_time: float
    error: str | None = None


class AuthFlowListItem(BaseModel):
    filepath: str
    filename: str
    recording_id: str
    flow_name: str
    auth_type: str
    created_at: str
    duration: float
    success: bool | None
    step_count: int


class AuthFlowCompareRequest(BaseModel):
    filepath1: str
    filepath2: str


async def debug_auth(request: DebugAuthRequest, record: bool = False, flow_name: str | None = None):
    """Debug authentication flow with detailed step-by-step logging."""
    try:
        # Create debugger with optional recorder
        recorder = auth_flow_recorder if record else None
        debugger = AuthDebugger(enabled=True, recorder=recorder)

        # Start recording if enabled
        if record:
            recording_name = flow_name or f"{request.auth_type}_debug"
            debugger.start_flow_recording(
                flow_name=recording_name,
                auth_type=request.auth_type,
                protocol_version="OAuth 2.0" if request.auth_type == "oauth" else None,
            )

        error = None

        try:
            if request.auth_type == "oauth":
                if request.oauth_auto_discover:
                    # Use RFC 8414 auto-discovery
                    if not request.mcp_url:
                        raise HTTPException(
                            status_code=400,
                            detail="OAuth auto-discovery requires mcp_url",
                        )
                    from testmcpy.auth_debugger import debug_oauth_auto_discover_flow

                    # Auto-discovery returns metadata, not a token
                    # The actual token exchange requires client credentials
                    await debug_oauth_auto_discover_flow(
                        mcp_url=request.mcp_url,
                        debugger=debugger,
                        insecure=request.insecure,
                    )
                elif not all([request.client_id, request.client_secret, request.token_url]):
                    raise HTTPException(
                        status_code=400,
                        detail="OAuth requires client_id, client_secret, and token_url (or enable oauth_auto_discover)",
                    )
                else:
                    # Token is captured by debugger trace, not returned directly
                    await debug_oauth_flow(
                        client_id=request.client_id,
                        client_secret=request.client_secret,
                        token_url=request.token_url,
                        scopes=request.scopes,
                        debugger=debugger,
                    )
            elif request.auth_type == "jwt":
                if not all([request.api_url, request.api_token, request.api_secret]):
                    raise HTTPException(
                        status_code=400, detail="JWT requires api_url, api_token, and api_secret"
                    )
                # Token is captured by debugger trace, not returned directly
                await debug_jwt_flow(
                    api_url=request.api_url,
                    api_token=request.api_token,
                    api_secret=request.api_secret,
                    debugger=debugger,
                )
            elif request.auth_type == "bearer":
                if not request.token:
                    raise HTTPException(status_code=400, detail="Bearer auth requires token")
                # Token is captured by debugger trace, not returned directly
                await debug_bearer_token(
                    token=request.token, mcp_url=request.mcp_url, debugger=debugger
                )
            else:
                raise HTTPException(
                    status_code=400, detail=f"Unsupported auth type: {request.auth_type}"
                )

        except Exception as e:
            error = str(e)

        # Save recording if enabled
        if record:
            debugger.save_flow_recording(
                success=error is None and not debugger.has_failures(), error=error
            )

        trace = debugger.get_trace()

        return DebugAuthResponse(
            success=not debugger.has_failures() and error is None,
            auth_type=request.auth_type,
            steps=trace["steps"],
            total_time=trace["total_time"],
            error=error,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to debug auth: {str(e)}")


@router.post("/debug-auth", response_model=DebugAuthResponse)
async def debug_auth_endpoint(
    request: DebugAuthRequest,
    record: bool = Query(False, description="Record the auth flow for later replay"),
    flow_name: str | None = Query(None, description="Name for the recorded flow"),
):
    """API endpoint for debug_auth."""
    return await debug_auth(request, record, flow_name)


@router.post("/mcp/profiles/{profile_id}/debug-auth", response_model=DebugAuthResponse)
async def debug_profile_auth(profile_id: str):
    """Debug authentication for a specific MCP profile."""
    from testmcpy.mcp_profiles import get_profile_config

    try:
        profile_config = get_profile_config()

        if not profile_config.has_profiles():
            raise HTTPException(status_code=404, detail="No profiles configured")

        profile = profile_config.get_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        if not profile.mcps:
            raise HTTPException(
                status_code=400, detail=f"Profile '{profile_id}' has no MCP servers configured"
            )

        # Get auth from first MCP server
        auth = profile.mcps[0].auth
        if not auth or not auth.auth_type:
            raise HTTPException(
                status_code=400, detail=f"Profile '{profile_id}' has no authentication configured"
            )

        # Build request from resolved auth config
        auth_type = auth.auth_type.lower()

        if auth_type == "oauth":
            request = DebugAuthRequest(
                auth_type="oauth",
                client_id=auth.client_id,
                client_secret=auth.client_secret,
                token_url=auth.token_url,
                scopes=auth.scopes or [],
            )
        elif auth_type == "jwt":
            request = DebugAuthRequest(
                auth_type="jwt",
                api_url=auth.api_url,
                api_token=auth.api_token,
                api_secret=auth.api_secret,
            )
        elif auth_type == "bearer":
            request = DebugAuthRequest(auth_type="bearer", token=auth.token)
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported auth type in profile: {auth_type}"
            )

        return await debug_auth(request)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to debug profile auth: {str(e)}")


# Auth Flow Recording API endpoints


@router.get("/auth-flows", response_model=list[AuthFlowListItem])
async def list_auth_flows(
    auth_type: str | None = Query(None, description="Filter by auth type (oauth, jwt, bearer)"),
    limit: int | None = Query(None, description="Maximum number of recordings to return"),
):
    """List all saved authentication flow recordings."""
    try:
        recordings = auth_flow_recorder.list_recordings(auth_type=auth_type, limit=limit)
        return recordings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list auth flows: {str(e)}")


@router.get("/auth-flows/{filename}")
async def get_auth_flow(filename: str):
    """Get a specific authentication flow recording."""
    try:
        filepath = auth_flow_recorder.storage_dir / filename
        if not filepath.exists():
            raise HTTPException(
                status_code=404, detail=f"Auth flow recording '{filename}' not found"
            )

        recording = auth_flow_recorder.load_recording(filepath)
        return recording.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load auth flow: {str(e)}")


@router.delete("/auth-flows/{filename}")
async def delete_auth_flow(filename: str):
    """Delete an authentication flow recording."""
    try:
        filepath = auth_flow_recorder.storage_dir / filename
        if not filepath.exists():
            raise HTTPException(
                status_code=404, detail=f"Auth flow recording '{filename}' not found"
            )

        auth_flow_recorder.delete_recording(filepath)
        return {"message": f"Auth flow '{filename}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete auth flow: {str(e)}")


@router.post("/auth-flows/compare")
async def compare_auth_flows(request: AuthFlowCompareRequest):
    """Compare two authentication flow recordings."""
    try:
        # Load both recordings
        filepath1 = Path(request.filepath1)
        filepath2 = Path(request.filepath2)

        if not filepath1.exists():
            raise HTTPException(
                status_code=404, detail=f"Recording 1 not found: {request.filepath1}"
            )
        if not filepath2.exists():
            raise HTTPException(
                status_code=404, detail=f"Recording 2 not found: {request.filepath2}"
            )

        recording1 = auth_flow_recorder.load_recording(filepath1)
        recording2 = auth_flow_recorder.load_recording(filepath2)

        # Compare recordings
        comparison = auth_flow_recorder.compare_recordings(recording1, recording2)
        return comparison
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare auth flows: {str(e)}")


@router.post("/auth-flows/{filename}/export")
async def export_auth_flow(
    filename: str, sanitize: bool = Query(True, description="Remove sensitive data")
):
    """Export an authentication flow recording as JSON (optionally sanitized)."""
    try:
        filepath = auth_flow_recorder.storage_dir / filename
        if not filepath.exists():
            raise HTTPException(
                status_code=404, detail=f"Auth flow recording '{filename}' not found"
            )

        recording = auth_flow_recorder.load_recording(filepath)

        if sanitize:
            recording = auth_flow_recorder.sanitize_recording(recording)

        return recording.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export auth flow: {str(e)}")
